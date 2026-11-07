"""Exercise model-free preparation across serialization and saved clinical text."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from redactor.inference.deterministic_text import make_text_preparer, prepare_text_phi
from redactor.inference.model_loader import load_local_ner
from redactor.inference.text import find_text_phi, finish_text_phi, make_text_finder
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import PreparedTextAssessment, TextEntity
from redactor.schemas.redaction import TextContext
from redactor.utils.errors import ERROR_COVERAGE, ERROR_ENTITY_EVIDENCE
from redactor.verification.text import verify_text_changes


def test_preparation_in_fresh_process_matches_serial_saved_text(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    prepared_file = tmp_path / "prepared.json"
    with source.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("text", "patient_name", "provider_name"))
        writer.writerows(
            (
                (
                    "Résumé reviewed with S. D’Avila.\n"
                    "Creatinine 1.20 mg/dL. Call 312-555-0193.",
                    "Siobhan D'Avila",
                    "",
                ),
                (
                    "Jose\u0301 Silva returned on 03/12/2026. A1c 8.4%.",
                    "José Silva",
                    "",
                ),
                (
                    "Dr. Mateo Kaur attended. Metformin 850 mg daily.",
                    "",
                    "Mateo Kaur",
                ),
                ("Alex Morgan", "Alex Morgan", "Alex Morgan"),
                ("Age 91 Metformin 850 mg daily", "", ""),
            )
        )
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import csv, json, sys\n"
            "from pathlib import Path\n"
            "from redactor.inference.deterministic_text import prepare_text_phi\n"
            "with Path(sys.argv[1]).open(newline='') as stream:\n"
            "    prepared = [prepare_text_phi(**row).model_dump(mode='json') "
            "for row in csv.DictReader(stream)]\n"
            "assert not {'spacy', 'onnxruntime', 'transformers'} & sys.modules.keys()\n"
            "Path(sys.argv[2]).write_text(json.dumps(prepared))\n",
            str(source),
            str(prepared_file),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    ner = load_local_ner(LocalSettings())
    output = tmp_path / "saved.csv"
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("text",))
        for number, value in enumerate(json.loads(prepared_file.read_text())):
            prepared = PreparedTextAssessment.model_validate(value)
            findings = finish_text_phi(prepared, ner)
            assert findings == find_text_phi(
                prepared.text,
                ner,
                patient_name=prepared.patient_name,
                provider_name=prepared.provider_name,
            )
            assert all(
                prepared.text[finding.start : finding.end] == finding.original
                for finding in findings
            )
            context = TextContext(
                context_key=f"record-{number}",
                patient_name=prepared.patient_name,
                provider_name=prepared.provider_name,
                maximum_date_shift_days=365,
            )
            edits = text_edits(findings, context, bytes(range(32)))
            saved = apply_text_edits(prepared.text, edits)
            verify_text_changes(
                prepared.text,
                saved,
                edits,
                ner,
                free_text=True,
                patient_name=prepared.patient_name,
                provider_name=prepared.provider_name,
            )
            writer.writerow((saved,))
            if "1.20" in saved:
                with pytest.raises(ValueError):
                    verify_text_changes(
                        prepared.text,
                        saved.replace("1.20", "1.21"),
                        edits,
                        ner,
                        free_text=True,
                        patient_name=prepared.patient_name,
                    )
    with output.open(newline="") as stream:
        saved_rows = tuple(row["text"] for row in csv.DictReader(stream))
    assert "Creatinine 1.20 mg/dL" in saved_rows[0]
    assert "A1c 8.4%" in saved_rows[1]
    assert "Metformin 850 mg daily" in saved_rows[2]
    assert saved_rows[3] != "Alex Morgan"
    assert saved_rows[4] == "Age 90+ Metformin 850 mg daily"


def test_complete_evidence_skips_model_but_unknown_residuals_keep_context(
    tmp_path: Path,
) -> None:
    source = tmp_path / "assessment.json"
    for original in (
        "",
        " \n\t",
        "Metformin 850 mg daily",
        "Age 91",
        "312-555-0193",
        "Siobhan D’Avila",
    ):
        prepared = prepare_text_phi(original, patient_name="Siobhan D'Avila")
        assert not prepared.unresolved
        source.write_text(prepared.model_dump_json())
        restored = PreparedTextAssessment.model_validate_json(source.read_text())
        assert finish_text_phi(restored, _unexpected_model) == prepared.findings

    observed: list[str] = []

    def recognize(text: str) -> tuple[TextEntity, ...]:
        observed.append(text)
        return ()

    for suffix in (";", " Leena", "🧬", " six"):
        prepared = prepare_text_phi("Metformin 850 mg daily" + suffix)
        source.write_text(prepared.model_dump_json())
        restored = PreparedTextAssessment.model_validate_json(source.read_text())
        assert restored.unresolved
        observed.clear()
        finish_text_phi(restored, recognize)
        assert observed == [prepared.text]


def test_saved_preparation_preserves_offsets_and_rejects_unhandled_predictions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    original = "☎ 312-555-0193. Reviewed with Zoë Moreau. Metformin 850 mg daily."
    source.write_text(prepare_text_phi(original).model_dump_json())
    prepared = PreparedTextAssessment.model_validate_json(source.read_text())

    def recognize_name(text: str) -> tuple[TextEntity, ...]:
        assert "312-555-0193" not in text
        assert "Metformin 850 mg daily" in text
        name = "Zoë Moreau"
        start = text.index(name)
        return (
            TextEntity(
                start=start, end=start + len(name), text=name, entity_type="person"
            ),
        )

    findings = finish_text_phi(prepared, recognize_name)
    assert tuple(finding.original for finding in findings) == (
        "312-555-0193",
        "Zoë Moreau",
    )
    assert findings[1].start == original.index("Zoë Moreau")

    def unsupported_time(text: str) -> tuple[TextEntity, ...]:
        start = text.index("six")
        return (TextEntity(start=start, end=start + 3, text="six", entity_type="time"),)

    source.write_text(prepare_text_phi("Metformin 850 mg daily; six").model_dump_json())
    with pytest.raises(ValueError, match=ERROR_COVERAGE):
        finish_text_phi(
            PreparedTextAssessment.model_validate_json(source.read_text()),
            unsupported_time,
        )

    def crossing_mask(text: str) -> tuple[TextEntity, ...]:
        return (TextEntity(start=0, end=len(text), text=text, entity_type="person"),)

    source.write_text(prepare_text_phi("312-555-0193 Leena").model_dump_json())
    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        finish_text_phi(
            PreparedTextAssessment.model_validate_json(source.read_text()),
            crossing_mask,
        )


def _unexpected_model(_text: str) -> tuple[TextEntity, ...]:
    raise AssertionError("Fully assessed text must not invoke a model")


def test_cached_preparation_saved_parity_preserves_each_record_role(
    tmp_path: Path,
) -> None:
    source = tmp_path / "contexts.csv"
    shared = "Alex Morgan. Glucose 106 mg/dL."
    rows = (
        (shared, "Alex Morgan", ""),
        (shared, "", "Alex Morgan"),
        (shared, "Alex Morgan", "Alex Morgan"),
        (shared, "Unrelated Person", ""),
        ("Age 91", "", ""),
        ("Call 206-555-0182", "", ""),
        ("Metformin 850 mg daily", "", ""),
        (shared, "Alex Morgan", ""),
        ("Siobhan D’Avila. " + "Glucose 106 mg/dL. " * 8, "Siobhan D'Avila", ""),
    )
    with source.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    prepare = make_text_preparer(maximum_entries=2, maximum_text_characters=64)
    ner = load_local_ner(LocalSettings())
    find = make_text_finder(ner, maximum_entries=2, maximum_text_characters=64)
    saved = tmp_path / "prepared.json"
    kinds = []
    with source.open(newline="") as stream:
        for number, (text, patient, provider) in enumerate(csv.reader(stream)):
            expected = prepare_text_phi(
                text, patient_name=patient, provider_name=provider
            )
            cached = prepare(text, patient, provider)
            saved.write_text(cached.model_dump_json())
            assert PreparedTextAssessment.model_validate_json(saved.read_text()) == (
                expected
            )
            assert find(text, patient, provider) == find_text_phi(
                text, ner, patient_name=patient, provider_name=provider
            )
            if number < 4:
                kinds.append(tuple(finding.kind for finding in cached.findings))
    assert kinds == [
        ("patient_name",),
        ("provider_name",),
        ("person_name",),
        (),
    ]
