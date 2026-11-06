"""Exercise real OCR, durable image publication, and saved-pixel tampering."""

import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from redactor.coordinator.bootstrap import prepare_run
from redactor.inference.runtime import runtime_adapters
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.checkpoints import latest_checkpoint
from redactor.persistence.queue.tasks import claim_task, iter_tasks
from redactor.policy.pixels import region_text_findings, text_pixel_masks
from redactor.schemas.entities import NerAdapter, TextEntity
from redactor.schemas.ocr import OcrRegion, OcrWord
from redactor.utils.configuration import load_settings
from redactor.utils.constants import (
    ENTITY_ORGANIZATION,
    ENTITY_PERSON,
    FIELD_DATE,
    FIELD_PERSON_NAME,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_LOCAL_INFERENCE
from redactor.verification.images import verify_images
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.pipeline import execute_task


def test_images_publish_all_frames_and_reject_pixel_or_metadata_leaks(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    settings = load_settings(environment={"LLM_ENABLED": "0"})
    if (
        shutil.which("tesseract") is None
        or not (
            settings.local.model_directory / "yunet/face_detection_yunet_2026may.onnx"
        ).is_file()
    ):
        pytest.skip("Install pinned OCR and YuNet assets and Tesseract first")
    source = tmp_path / "input"
    source.mkdir()
    image = Image.new("RGB", (720, 280), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=32)
    draw.text((30, 30), "Patient Alice Stone", font=font, fill="black")
    draw.text((30, 180), "Pulse 72 bpm", font=font, fill="black")
    image.save(source / "card.png")
    image.save(source / "card.jpg", quality=100, subsampling=0)
    image.save(source / "frames.tiff", save_all=True, append_images=[image.copy()])
    originals = {path.name: path.read_bytes() for path in source.iterdir()}
    key = bytes(range(32))
    run = prepare_run(connection, source, settings, key)
    ner, ocr, verifier_ner = runtime_adapters(settings.local, settings.resources)
    handlers = pipeline_handlers(
        settings,
        key,
        ner,
        run.resolution_task_id,
        local_ocr=ocr,
        verifier_ner=verifier_ner,
    )
    while task := claim_task(connection):
        execute_task(connection, task, handlers)
    tasks = tuple(iter_tasks(connection))
    assert not any(task.step == "quarantine" for task in tasks), [
        (task.step, task.status, task.failure_code) for task in tasks
    ]
    published = [task for task in tasks if task.step == "publish"]
    assert len(published) == 3
    assert all(task.status == "succeeded" for task in tasks)
    for task in tasks:
        if task.step == "rewrite":
            checkpoint = latest_checkpoint(connection, task.task_id)
            assert checkpoint is not None
            assert checkpoint.counts == {
                "person_name": 2 if task.input_path.suffix == ".tiff" else 1
            }
    for task in published:
        assert task.output_path is not None
        with Image.open(task.output_path) as output:
            expected_frames = 2 if task.input_path.suffix == ".tiff" else 1
            assert getattr(output, "n_frames", 1) == expected_frames
            for number in range(expected_frames):
                output.seek(number)
                if task.input_path.suffix != ".jpg":
                    np.testing.assert_array_equal(
                        np.array(output)[160:], np.array(image)[160:]
                    )
        assert task.output_path.read_bytes() != originals[task.input_path.name]
    task = next(task for task in published if task.input_path.suffix == ".png")
    assert task.output_path is not None
    clean = task.output_path.read_bytes()
    for alteration in ("original", "clinical", "metadata", "trailing"):
        if alteration == "original":
            task.output_path.write_bytes(originals[task.input_path.name])
        elif alteration == "trailing":
            task.output_path.write_bytes(clean + b"Private extra bytes")
        else:
            task.output_path.write_bytes(clean)
            with Image.open(task.output_path) as saved:
                damaged = saved.copy()
            if alteration == "clinical":
                ImageDraw.Draw(damaged).rectangle((0, 160, 720, 280), fill="white")
                damaged.save(task.output_path)
            else:
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text("patient", "Alice Stone")
                damaged.save(task.output_path, pnginfo=metadata)
        with pytest.raises(ValueError):
            verify_images(
                connection,
                task,
                inspect_artifact(task.output_path, persist=False),
                settings=settings,
                mapping_key=key,
                local_ner=verifier_ner,
            )
    task.output_path.write_bytes(clean)
    assert {path.name: path.read_bytes() for path in source.iterdir()} == originals
    assert claim_task(connection) is None


def _word_region(text: str, top: float) -> OcrRegion:
    words = tuple(
        OcrWord(
            text=token,
            box=(20.0 + 90 * position, top, 80.0 + 90 * position, top + 30.0),
        )
        for position, token in enumerate(text.split(" "))
    )
    return OcrRegion(text=text, box=(10.0, top, 700.0, top + 30.0), words=words)


def _entities(
    text: str, observations: tuple[tuple[str, str, str], ...]
) -> tuple[TextEntity, ...]:
    return tuple(
        TextEntity(
            start=text.index(value),
            end=text.index(value) + len(value),
            text=value,
            entity_type=entity_type,
            label=label,
        )
        for value, entity_type, label in observations
        if value in text
    )


def _ambiguous_then_grounded(
    isolated: tuple[tuple[str, str, str], ...],
    contextual: tuple[tuple[str, str, str], ...],
) -> NerAdapter:
    """A controlled detector substitute at the model boundary."""

    def recognize(text: str) -> tuple[TextEntity, ...]:
        return _entities(text, contextual if "\n" in text else isolated)

    return recognize


@pytest.mark.parametrize(
    ("lines", "target", "expected"),
    [
        (("BETA GAMMA", "DELTA NINE"), 0, (0, 4)),
        (("ALPHA LINE ONE", "BETA GAMMA", "DELTA NINE"), 1, (15, 19)),
        (("ALPHA LINE ONE", "BETA GAMMA"), 1, (15, 19)),
    ],
)
def test_context_retry_projects_only_target_line_findings(
    lines: tuple[str, ...], target: int, expected: tuple[int, int]
) -> None:
    regions = tuple(
        _word_region(line, 40.0 + 60 * index) for index, line in enumerate(lines)
    )
    detector = _ambiguous_then_grounded(
        (("BETA", ENTITY_PERSON, "name"), ("GAMMA", ENTITY_ORGANIZATION, "facility")),
        (("ALPHA", ENTITY_PERSON, "name"), ("BETA", ENTITY_PERSON, "name")),
    )
    findings = region_text_findings(regions, detector)
    grounded = tuple(
        finding for finding in findings if finding.kind == FIELD_PERSON_NAME
    )
    assert [(finding.start, finding.end) for finding in grounded] == [expected]
    assert all(finding.original == "BETA" for finding in grounded)


def test_context_retry_rejects_crossing_and_ungrounded_observations() -> None:
    regions = (
        _word_region("ALPHA LINE", 40.0),
        _word_region("BETA GAMMA", 100.0),
    )
    crossing = _ambiguous_then_grounded(
        (("BETA", ENTITY_PERSON, "name"), ("GAMMA", ENTITY_ORGANIZATION, "facility")),
        (("NE\nBETA", ENTITY_PERSON, "name"), ("GAMMA", ENTITY_PERSON, "name")),
    )
    with pytest.raises(ValueError, match=ERROR_COVERAGE):
        region_text_findings(regions, crossing)
    ungrounded = _ambiguous_then_grounded(
        (("BETA", ENTITY_PERSON, "name"), ("GAMMA", ENTITY_ORGANIZATION, "facility")),
        (("ALPHA", ENTITY_PERSON, "name"),),
    )
    with pytest.raises(ValueError, match=ERROR_COVERAGE):
        region_text_findings(regions, ungrounded)


def test_context_retry_preserves_unrelated_model_failures() -> None:
    regions = (_word_region("BETA GAMMA", 40.0),)

    def unavailable(text: str) -> tuple[TextEntity, ...]:
        raise ValueError(ERROR_LOCAL_INFERENCE)

    with pytest.raises(ValueError, match=ERROR_LOCAL_INFERENCE):
        region_text_findings(regions, unavailable)


def test_capitalization_alone_never_extends_person_masks() -> None:
    regions = (_word_region("Alice Pulmonary Embolism", 40.0),)
    detector = _ambiguous_then_grounded(
        (("Alice", ENTITY_PERSON, "name"),), (("Alice", ENTITY_PERSON, "name"),)
    )
    masks, counts = text_pixel_masks(regions, (720, 120), detector)
    assert counts == {FIELD_PERSON_NAME: 1}
    assert len(masks) == 1
    assert masks[0].box[0] >= 10 and masks[0].box[2] <= 90


def test_person_findings_stay_separate_from_adjacent_values() -> None:
    regions = (_word_region("BETA GAMMA 01/02/1934", 40.0),)
    detector = _ambiguous_then_grounded(
        (("BETA", ENTITY_PERSON, "name"),), (("BETA", ENTITY_PERSON, "name"),)
    )
    findings = region_text_findings(regions, detector)
    assert sorted(finding.kind for finding in findings) == [
        FIELD_DATE,
        FIELD_PERSON_NAME,
    ]
    assert all(finding.original in ("BETA", "01/02/1934") for finding in findings)
    assert not any(finding.start < 5 and finding.end > 5 for finding in findings)
