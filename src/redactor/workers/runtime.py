"""Load a frozen run and one local model only in the inference worker."""

from contextlib import closing

from redactor.inference.fingerprint import runtime_fingerprint
from redactor.inference.runtime import runtime_adapters
from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import get_task
from redactor.persistence.runs.manifests import read_manifest
from redactor.schemas.entities import NerAdapter, TextEntity
from redactor.schemas.persistence import Artifact
from redactor.schemas.worker import WorkerConfig
from redactor.utils.configuration import key_fingerprint, read_mapping_key
from redactor.utils.constants import INFERENCE_STEPS
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE, ERROR_RUN_CONTEXT
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.run import consume_tasks


def unavailable_ner(text: str) -> tuple[TextEntity, ...]:
    raise ValueError(ERROR_LOCAL_UNAVAILABLE)


def consume_pipeline(config: WorkerConfig) -> None:
    assert config.resolution_task_id is not None
    key = read_mapping_key()
    with closing(open_database(config.state_directory)) as connection:
        task = get_task(connection, config.resolution_task_id)
        artifact = Artifact(
            path=task.input_path, sha256=task.input_sha256, size=task.input_size
        )
        manifest = read_manifest(artifact, key_fingerprint(key))
    if runtime_fingerprint(manifest.settings.local) != manifest.runtime_fingerprint:
        raise ValueError(ERROR_RUN_CONTEXT)
    settings = manifest.settings.model_copy(
        update={
            "remote": manifest.settings.remote.model_copy(
                update={"enabled": config.remote_enabled}
            ),
        }
    )
    ner: NerAdapter = unavailable_ner
    ocr = None
    verifier_ner = None
    if config.inference:
        ner, ocr, verifier_ner = runtime_adapters(settings.local, settings.resources)
    handlers = pipeline_handlers(
        settings,
        key,
        ner,
        config.resolution_task_id,
        local_ocr=ocr,
        verifier_ner=verifier_ner,
    )
    steps = tuple(
        step
        for step in handlers
        if config.all_steps or (step in INFERENCE_STEPS) == config.inference
    )
    consume_tasks(
        config.state_directory,
        config.coordinator_pid,
        processing_version=artifact.sha256,
        handlers=handlers,
        eligible_steps=steps,
    )
