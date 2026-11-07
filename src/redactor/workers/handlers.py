"""Compose the functional step handlers with one worker's dependencies."""

from functools import partial

import httpx

from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter, NerBatchAdapter
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.pipeline import StepHandler
from redactor.utils.constants import (
    STEP_ANALYZE,
    STEP_INSPECT,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_RESOLVE,
    STEP_REWRITE,
    STEP_VERIFY,
)
from redactor.workers.analyze import analyze_task
from redactor.workers.inspect import inspect_task
from redactor.workers.publish import publish_task
from redactor.workers.quarantine import quarantine_task
from redactor.workers.resolve import resolve_task
from redactor.workers.rewrite import rewrite_or_quarantine
from redactor.workers.verify import verify_task


def pipeline_handlers(
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
    *,
    model_transport: httpx.AsyncBaseTransport | None = None,
    local_ocr: OcrAdapter | None = None,
    verifier_ner: NerAdapter | None = None,
    verification_batch: NerBatchAdapter | None = None,
) -> dict[str, StepHandler]:
    return {
        STEP_INSPECT: partial(
            inspect_task,
            resources=settings.resources,
            mapping_key=mapping_key,
        ),
        STEP_ANALYZE: partial(
            analyze_task,
            settings=settings,
            mapping_key=mapping_key,
            local_ner=local_ner,
            local_ocr=local_ocr,
            transport=model_transport,
        ),
        STEP_RESOLVE: partial(resolve_task, mapping_key=mapping_key),
        STEP_REWRITE: partial(
            rewrite_or_quarantine,
            settings=settings,
            mapping_key=mapping_key,
            local_ner=local_ner,
            resolution_task_id=resolution_task_id,
        ),
        STEP_VERIFY: partial(
            verify_task,
            settings=settings,
            mapping_key=mapping_key,
            local_ner=verifier_ner or local_ner,
            verification_batch=verification_batch,
            resolution_task_id=resolution_task_id,
            transport=model_transport,
        ),
        STEP_PUBLISH: partial(
            publish_task,
            mapping_key=mapping_key,
            resolution_task_id=resolution_task_id,
        ),
        STEP_QUARANTINE: partial(quarantine_task, mapping_key=mapping_key),
    }
