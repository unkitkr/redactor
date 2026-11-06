"""Load a frozen run and one local model only in the inference worker."""

from contextlib import closing

from redactor.inference.model_loader import load_local_ner
from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import get_task
from redactor.persistence.runs.manifests import read_manifest
from redactor.schemas.entities import NerAdapter, TextEntity
from redactor.schemas.persistence import Artifact
from redactor.schemas.worker import WorkerConfig
from redactor.utils.configuration import key_fingerprint, read_mapping_key
from redactor.utils.constants import INFERENCE_STEPS
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE
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
    settings = manifest.settings.model_copy(
        update={
            "remote": manifest.settings.remote.model_copy(
                update={"enabled": config.remote_enabled}
            ),
        }
    )
    ner: NerAdapter = unavailable_ner
    if config.inference:
        try:
            ner = load_local_ner(settings.local)
        except ValueError:
            # Typed fields still work; any required inference fails closed.
            ner = unavailable_ner
    handlers = pipeline_handlers(settings, key, ner, config.resolution_task_id)
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
