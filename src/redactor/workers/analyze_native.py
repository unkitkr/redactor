"""Analyze every exposed native surface before accepting its identity evidence."""

import sqlite3
from collections import Counter

from redactor.formats.embedded_images import (
    analyze_embedded_image,
    embedded_pixel_count,
)
from redactor.formats.native import read_native
from redactor.identity.native import native_evidence
from redactor.inference.context import record_ner
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.results import write_step_result
from redactor.persistence.identities.observations import (
    save_observation_batch,
    scan_progress,
)
from redactor.policy.tabular import cell_findings
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.identity import IdentityEvidence
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.pixels import EmbeddedImageEvidence
from redactor.utils.constants import (
    ENCRYPTION_HEADER,
    ENCRYPTION_NONCE_BYTES,
    ENCRYPTION_TAG_BYTES,
    MAX_MANIFEST_BYTES,
)
from redactor.utils.errors import (
    ERROR_COVERAGE,
    ERROR_INPUT_CHANGED,
    ERROR_RESOURCE_LIMIT,
)
from redactor.utils.failures import failure_reason


def analyze_native_task(
    connection: sqlite3.Connection,
    task: Task,
    inspection: FileInspection,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    detector: NerAdapter,
    local_ocr: OcrAdapter | None,
) -> StepResult:
    counts: Counter[str] = Counter()
    completed = 0
    reason = None
    images: list[EmbeddedImageEvidence] = []
    resources = settings.resources
    try:
        before = inspect_artifact(task.input_path, persist=False)
        if before.sha256 != task.input_sha256 or before.size != task.input_size:
            raise ValueError(ERROR_INPUT_CHANGED)
        document = read_native(task.input_path, inspection, resources)
        locations = tuple(image.location for image in document.images)
        if any(not location for location in locations) or len(set(locations)) != len(
            locations
        ):
            raise ValueError(ERROR_COVERAGE)
        patient_names = {
            record.evidence.patient.name
            for record in document.records
            if record.evidence
            and record.evidence.patient
            and record.evidence.patient.name
        }
        provider_names = {
            record.evidence.provider.name
            for record in document.records
            if record.evidence
            and record.evidence.provider
            and record.evidence.provider.name
        }
        patient_name = next(iter(patient_names)) if len(patient_names) == 1 else ""
        provider_name = next(iter(provider_names)) if len(provider_names) == 1 else ""
        pixels = 0
        for image in document.images:
            if local_ocr is None:
                raise ValueError(ERROR_COVERAGE)
            pixels += embedded_pixel_count(image, resources.max_image_pixels - pixels)
            assessment = analyze_embedded_image(
                image,
                settings,
                detector,
                local_ocr,
                patient_name=patient_name,
                provider_name=provider_name,
            )
            if pixels > resources.max_image_pixels:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            images.append(assessment)
            counts.update(assessment.counts)
        facts: dict[str, IdentityEvidence] = {}
        for number, record in enumerate(document.records, start=1):
            evidence = native_evidence(record, task.input_sha256, number)
            for fact in (evidence.patient, evidence.provider):
                if fact is not None:
                    facts[fact.model_dump_json()] = fact
            for column in record.policies:
                scoped_detector = record_ner(
                    detector, record, column.index, settings.local.ner_max_characters
                )
                found = cell_findings(
                    record.values[column.index],
                    column,
                    scoped_detector,
                    patient_name=evidence.patient.name if evidence.patient else "",
                    provider_name=evidence.provider.name if evidence.provider else "",
                )
                counts.update(finding.kind for finding in found)
            completed = number
        if inspect_artifact(task.input_path, persist=False) != before:
            raise ValueError(ERROR_INPUT_CHANGED)
        summary = FileAnalysis(
            file_type=inspection.file_type,
            record_count=completed,
            counts=dict(counts),
            embedded_images=tuple(images),
        )
        if (
            len(summary.model_dump_json().encode())
            + len(ENCRYPTION_HEADER)
            + ENCRYPTION_NONCE_BYTES
            + ENCRYPTION_TAG_BYTES
        ) > MAX_MANIFEST_BYTES:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        previous = scan_progress(connection, task.task_id)
        save_observation_batch(
            connection,
            task,
            tuple(facts.values()),
            mapping_key,
            sequence=previous.sequence if previous else 1,
            input_offset=task.input_size,
            record_count=completed,
            counts=dict(counts),
        )
    except Exception as error:
        reason = failure_reason(error)
    return StepResult(
        artifact=write_step_result(
            connection,
            task,
            FileAnalysis(
                file_type=inspection.file_type,
                reason=reason,
                record_count=completed,
                counts=dict(counts),
                embedded_images=tuple(images) if reason is None else (),
            ),
            encryption_key=mapping_key,
        )
    )
