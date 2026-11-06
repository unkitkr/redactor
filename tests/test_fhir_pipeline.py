"""Exercise native FHIR identity references, exact scalars and hidden attachments."""

import base64
import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from redactor.formats.fhir import read_fhir
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.redaction import TextEdit
from redactor.verification.fhir import check_fhir_structure
from redactor.verification.text import verify_text_changes


def test_fhir_pipeline_references_narrative_attachment_and_tampering(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    original = source / "bundle.json"
    embedded = base64.b64encode(b'{"phone":"415-555-0152","value":1.23000}').decode()
    original.write_text(
        '{"resourceType":"Bundle","id":"bundle-1","type":"collection",'
        '"entry":[{"fullUrl":"urn:uuid:patient-1","resource":{'
        '"resourceType":"Patient","id":"patient-1",'
        '"identifier":[{"system":"urn:oid:1.2.3","type":{"text":"MRN"},"value":"74208"}],'
        '"name":[{"given":["Amina","J"],"family":"Keller"}],'
        '"birthDate":"1972-03-04","gender":"female",'
        '"text":{"status":"generated","div":"<div xmlns=\\"http://www.w3.org/1999/xhtml\\">'
        '<p>Ami<b>na Kel</b>ler attended.</p></div>"}}},'
        '{"fullUrl":"urn:uuid:provider-1","resource":{'
        '"resourceType":"Practitioner","id":"provider-1",'
        '"name":[{"given":["Terry"],"family":"Jones"}],'
        '"identifier":[{"system":"http://hl7.org/fhir/sid/us-npi","value":"1234567893"}]}},'
        '{"fullUrl":"urn:uuid:observation-1","resource":{'
        '"resourceType":"Observation","id":"observation-1","status":"final",'
        '"subject":{"reference":"Patient/patient-1","display":"Amina Keller"},'
        '"performer":[{"reference":"Practitioner/provider-1","display":"Terry Jones"}],'
        '"effectiveDateTime":"2024-03-12T10:20:00-05:00",'
        '"valueQuantity":{"value":1.23000000000000000000000001e-4,"unit":"mg/dL"},'
        '"code":{"coding":[{"system":"http://loinc.org","code":"2160-0",'
        '"display":"Creatinine [Mass/volume] in Serum or Plasma"}]},'
        '"contained":[{"resourceType":"Specimen","id":"specimen-1",'
        '"accessionIdentifier":{"value":"ACC-74208"}}],'
        '"specimen":{"reference":"#specimen-1"}}},'
        '{"fullUrl":"urn:uuid:doc-1","resource":{'
        '"resourceType":"DocumentReference","id":"doc-1","status":"current",'
        '"subject":{"reference":"urn:uuid:patient-1"},'
        '"content":[{"attachment":{"contentType":"application/json",'
        f'"data":"{embedded}"}}}}]}}}}]}}'
    )
    (source / "older.json").write_text(
        '{"resourceType":"Bundle","type":"collection","entry":[{"resource":{'
        '"resourceType":"Patient","id":"older-patient","name":[{"given":["Nadia"],'
        '"family":"Velez"}],"birthDate":"1900-01-01"}},{"resource":{'
        '"resourceType":"Encounter","id":"older-encounter",'
        '"subject":{"reference":"Patient/older-patient"},'
        '"period":{"start":"2024-03-12"}}}]}'
    )
    settings = tmp_path / "settings.toml"
    settings.write_text('[local]\nner = "spacy"\n')
    environment = dict(
        os.environ,
        REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
        LLM_ENABLED="0",
    )
    snapshots = []
    for name in ("first", "first", "second"):
        run = tmp_path / name
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "redactor",
                "--input",
                str(source),
                "--state",
                str(run / ".redactor"),
                "--config",
                str(settings),
                "--no-dashboard",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((run / "output/report.json").read_text())
        assert report["published"] == 2 and report["quarantined"] == 0, report
        snapshots.append((run / "output/published/bundle.json").read_bytes())
    assert snapshots[0] == snapshots[1] == snapshots[2]
    saved = tmp_path / "first/output/published/bundle.json"
    raw = saved.read_text()
    assert "1.23000000000000000000000001e-4" in raw
    assert all(name not in raw for name in ("Amina", "Keller", "Terry", "Jones"))
    data = json.loads(raw)
    patient, provider, observation, document = [
        entry["resource"] for entry in data["entry"]
    ]
    assert observation["subject"]["reference"] == "Patient/" + patient["id"]
    assert observation["performer"][0]["reference"] == "Practitioner/" + provider["id"]
    assert (
        observation["specimen"]["reference"] == "#" + observation["contained"][0]["id"]
    )
    assert document["subject"]["reference"] == data["entry"][0]["fullUrl"]
    decoded = base64.b64decode(document["content"][0]["attachment"]["data"]).decode()
    assert "415-555-0152" not in decoded and "1.23000" in decoded
    resources = ResourceSettings()
    extracted = read_fhir(original, resources)
    check_fhir_structure(original, saved, extracted, resources)
    for number, mutated in enumerate(
        (
            raw.replace("1.23000000000000000000000001e-4", "1.2"),
            raw.replace('"code":"2160-0"', '"code":"2160-1"'),
            raw.replace('"reference":"Patient/', '"reference":"Practitioner/'),
        )
    ):
        damaged = tmp_path / f"damaged-{number}.json"
        damaged.write_text(mutated)
        with pytest.raises(ValueError):
            check_fhir_structure(original, damaged, extracted, resources)
    older_saved = tmp_path / "first/output/published/older.json"
    older_data = json.loads(older_saved.read_text())
    older_patient = older_data["entry"][0]["resource"]
    assert "birthDate" not in older_patient
    extensions = older_patient["_birthDate"]["extension"]
    assert extensions[0]["valueCode"] == "masked"
    assert extensions[1]["valueString"] == "90+"
    assert len(extensions[2]["valueDate"]) == 4
    assert "1900-01-01" not in older_saved.read_text()
    older_original = source / "older.json"
    older_extracted = read_fhir(older_original, resources)
    check_fhir_structure(older_original, older_saved, older_extracted, resources)
    logical = read_fhir(older_saved, resources, extract_evidence=False)
    logical_bound = next(
        record.values[0]
        for record in logical.records
        if record.policies[0].kind == "birth_date"
    )
    assert logical_bound == "on or before " + extensions[2]["valueDate"]
    for field, value in (
        ("valueCode", "unknown"),
        ("valueString", "89+"),
        ("valueDate", "1900-01-01"),
    ):
        corrupted = older_saved.read_text().replace(
            json.dumps(field)
            + ": "
            + json.dumps(
                next(extension[field] for extension in extensions if field in extension)
            ),
            json.dumps(field) + ": " + json.dumps(value),
        )
        damaged = tmp_path / "damaged-bound.json"
        damaged.write_text(corrupted)
        with pytest.raises(ValueError):
            check_fhir_structure(older_original, damaged, older_extracted, resources)

    altered_year = str(int(extensions[2]["valueDate"]) - 1)
    extensions[2]["valueDate"] = altered_year
    damaged = tmp_path / "wrong-bound-year.json"
    damaged.write_text(json.dumps(older_data))
    altered_document = read_fhir(damaged, resources, extract_evidence=False)
    altered_bound = next(
        record.values[0]
        for record in altered_document.records
        if record.policies[0].kind == "birth_date"
    )
    with pytest.raises(ValueError):
        verify_text_changes(
            "1900-01-01",
            altered_bound,
            (
                TextEdit(
                    start=0,
                    end=10,
                    original="1900-01-01",
                    kind="birth_date",
                    replacement=logical_bound,
                ),
            ),
            lambda _text: (),
            free_text=False,
        )

    unsafe = tmp_path / "unsafe.json"
    for replacement in (
        raw.replace('"type":"collection"', '"unknownSecret":"hidden"'),
        raw.replace(
            '"contentType":"application/json"',
            '"contentType":"application/octet-stream"',
        ),
    ):
        unsafe.write_text(replacement)
        with pytest.raises(ValueError):
            read_fhir(unsafe, resources)

    for image_format, content_type in (
        ("PNG", "image/png"),
        ("JPEG", "image/jpeg"),
        ("TIFF", "image/tiff"),
    ):
        image_bytes = BytesIO()
        Image.new("RGB", (12, 12)).save(image_bytes, format=image_format)
        attachment = document["content"][0]["attachment"]
        attachment["contentType"] = content_type
        attachment["data"] = base64.b64encode(image_bytes.getvalue()).decode()
        unsafe.write_text(json.dumps(data))
        assert len(read_fhir(unsafe, resources).images) == 1
        attachment["contentType"] = (
            "image/jpeg" if image_format != "JPEG" else "image/png"
        )
        unsafe.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            read_fhir(unsafe, resources)


def test_typed_medication_dose_forms_preserve_only_complete_clinical_values(
    tmp_path: Path,
) -> None:
    from redactor.formats.fhir import write_fhir
    from redactor.formats.tabular_fields import validate_clinical_field

    source, output = tmp_path / "medications.json", tmp_path / "saved.json"
    valid = (
        "metformin 500 mg Oral Tablet",
        "amoxicillin 250 mg Oral Capsule",
        "hydrocortisone 10 mg Topical Cream",
        "albuterol 2.5 mg Inhalation Solution",
    )
    invalid = (
        "Amina Keller metformin 500 mg Oral Tablet",
        "metformin 500 mg Oral Tablet for Amina Keller",
        "metformin 500 mg Amina Keller Oral Tablet",
        "metformin 500 mg mystery formulation",
    )
    source.write_text(
        json.dumps(
            {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "MedicationRequest",
                            "id": f"medication-{index}",
                            "status": "active",
                            "intent": "order",
                            "medicationCodeableConcept": {
                                "coding": [
                                    {
                                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                        "code": "12345",
                                        "display": value,
                                    }
                                ]
                            },
                        }
                    }
                    for index, value in enumerate((*valid, *invalid))
                ],
            }
        )
    )
    resources = ResourceSettings()
    document = read_fhir(source, resources)
    displays = [
        record for record in document.records if record.locations[0][-1] == "display"
    ]
    assert len(displays) == len(valid) + len(invalid)
    for index, record in enumerate(displays):
        assert record.policies[0].kind == ("clinical" if index < len(valid) else "text")
    write_fhir(source, output, {}, {}, resources)
    check_fhir_structure(source, output, document, resources)
    assert [record.values for record in read_fhir(output, resources).records] == [
        record.values for record in document.records
    ]
    for value in invalid:
        with pytest.raises(ValueError):
            validate_clinical_field(value, "medication_display")
