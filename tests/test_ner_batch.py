"""Batch inference preserves grounded saved-text results and model phase isolation."""

import json
from pathlib import Path

import pytest

from redactor.inference.model_loader import load_local_ner_adapters, prepare_ner_batch
from redactor.inference.runtime import runtime_model_adapters
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.entities import TextEntity
from redactor.utils.constants import SPACY_BATCH_SIZE
from redactor.utils.errors import (
    ERROR_ENTITY_EVIDENCE,
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
)


def test_installed_spacy_batches_match_saved_inputs_and_reject_incomplete_results(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.jsonl"
    examples = (
        "Alice Stone was reviewed in London. Glucose 106 mg/dL.",
        "Contact: Renée Marin\nCall +44 20 7946 0958.",
        "Telephone: (206) 555-0101. Email: person@example.org.",
        "Age 90+. Metformin 500 mg BID. Follow up in 2 weeks.",
        "",
    )
    source.write_text(
        "\n".join(
            json.dumps(examples[index % len(examples)], ensure_ascii=False)
            for index in range(2 * SPACY_BATCH_SIZE + 1)
        ),
        encoding="utf-8",
    )
    texts = tuple(json.loads(line) for line in source.read_text().splitlines())
    settings = LocalSettings(ner_max_characters=512)
    single, batch = load_local_ner_adapters(settings)
    assert batch is not None
    expected = tuple(single(text) for text in texts)
    assert batch(texts) == expected
    assert batch(()) == ()
    assert batch(("",)) == ((),)
    assert batch(tuple(reversed(texts))) == tuple(reversed(expected))
    # Returned values survive all later vocabulary memory zones.
    assert expected[0][0].text == "Alice Stone"
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        batch(("x" * 513,))

    def partial(values: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        return tuple(() for _ in values[:-1])

    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        prepare_ner_batch(partial, settings)(texts)

    def ungrounded(values: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        return tuple(
            (TextEntity(start=0, end=10, text="Wrong Name", entity_type="person"),)
            for _ in values
        )

    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        prepare_ner_batch(ungrounded, settings)(texts[:1])

    def failed(values: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        raise RuntimeError(f"Backend detail: {values[0]}")

    with pytest.raises(ValueError) as failure:
        prepare_ner_batch(failed, settings)(texts[:1])
    assert failure.value.args == (ERROR_LOCAL_INFERENCE,)


def test_runtime_switches_between_real_detector_and_batched_independent_verifier() -> (
    None
):
    weights = Path(__file__).parents[1] / ".models/gliner-pii-edge-v1.0"
    if not (weights / "onnx/model_quint8.onnx").is_file():
        pytest.skip("Pinned GLiNER weights must be staged before integration testing")
    detector, _, verifier, verification_batch = runtime_model_adapters(
        LocalSettings(ner="gliner", ner_directory=weights), ResourceSettings()
    )
    texts = (
        "Alice Stone visited London.",
        "Call 206-555-0101 before 2026-04-05.",
    )
    detected = detector(texts[0])
    independent = verification_batch(texts)
    assert independent == tuple(verifier(text) for text in texts)
    assert detector(texts[0]) == detected
    assert verification_batch(texts) == independent
