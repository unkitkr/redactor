"""Apply accepted masks and save a fresh native image container."""

import sqlite3

from redactor.formats.images import (
    encode_image_frames,
    mask_image,
    pixel_digest,
    read_image_frames,
)
from redactor.persistence.files.artifacts import (
    create_temporary_file,
    inspect_artifact,
    seal_temporary_file,
)
from redactor.persistence.files.checkpoints import latest_checkpoint, save_checkpoint
from redactor.persistence.files.registration import prepare_successor
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.persistence import Checkpoint, Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import NATIVE_ADAPTER_VERSION, STEP_VERIFY
from redactor.utils.errors import ERROR_COVERAGE, ERROR_INPUT_CHANGED


def rewrite_image_task(
    connection: sqlite3.Connection,
    task: Task,
    analysis: FileAnalysis,
    resources: ResourceSettings,
) -> StepResult:
    original = inspect_artifact(task.input_path, persist=False)
    if original.sha256 != task.input_sha256 or original.size != task.input_size:
        raise ValueError(ERROR_INPUT_CHANGED)
    frames = read_image_frames(task.input_path, resources)
    if analysis.reason is not None or len(frames) != len(analysis.images):
        raise ValueError(ERROR_COVERAGE)
    for image, evidence in zip(frames, analysis.images, strict=True):
        if (
            image.size != (evidence.width, evidence.height)
            or pixel_digest(image) != evidence.sha256
        ):
            raise ValueError(ERROR_INPUT_CHANGED)
    rewritten = tuple(
        mask_image(frame, evidence.masks)
        for frame, evidence in zip(frames, analysis.images, strict=True)
    )
    output = create_temporary_file(connection, task)
    output.write_bytes(encode_image_frames(rewritten, analysis.file_type.upper()))
    if inspect_artifact(task.input_path, persist=False) != original:
        raise ValueError(ERROR_INPUT_CHANGED)
    artifact = seal_temporary_file(connection, task)
    previous = latest_checkpoint(connection, task.task_id)
    save_checkpoint(
        connection,
        task,
        Checkpoint(
            sequence=previous.sequence + 1 if previous else 1,
            task_id=task.task_id,
            artifact_path=output,
            input_offset=task.input_size,
            output_offset=artifact.size,
            record_count=len(frames),
            output_prefix_sha256=artifact.sha256,
            counts=analysis.counts,
            adapter_version=NATIVE_ADAPTER_VERSION,
        ),
    )
    return StepResult(
        artifact=artifact,
        successors=(prepare_successor(connection, task, STEP_VERIFY),),
    )
