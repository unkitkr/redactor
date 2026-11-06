"""Exercise real OCR, durable image publication, and saved-pixel tampering."""

import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from redactor.coordinator.bootstrap import prepare_run
from redactor.inference.runtime import local_adapters
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.checkpoints import latest_checkpoint
from redactor.persistence.queue.tasks import claim_task, iter_tasks
from redactor.utils.configuration import load_settings
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
    ner, ocr = local_adapters(settings.local, settings.resources)
    handlers = pipeline_handlers(
        settings, key, ner, run.resolution_task_id, local_ocr=ocr
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
                local_ner=ner,
            )
    task.output_path.write_bytes(clean)
    assert {path.name: path.read_bytes() for path in source.iterdir()} == originals
    assert claim_task(connection) is None
