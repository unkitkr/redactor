"""Thin startup sequence; workers own individual task execution."""

from contextlib import closing

from redactor.coordinator.bootstrap import prepare_run
from redactor.coordinator.inventory import register_inputs, validate_directories
from redactor.coordinator.monitoring import dashboard_process
from redactor.coordinator.ownership import own_run
from redactor.coordinator.processes import run_workers
from redactor.coordinator.reconcile import reconcile_run
from redactor.persistence.database import open_database
from redactor.persistence.models.budget import recover_model_attempts
from redactor.persistence.queue.tasks import recover_interrupted
from redactor.persistence.runs.outputs import bind_output_directory
from redactor.schemas.coordinator import CoordinatorConfig
from redactor.utils.configuration import load_settings, read_mapping_key


def run_coordinator(config: CoordinatorConfig) -> None:
    input_directory = config.input_directory.resolve()
    state_directory = config.state_directory.resolve()
    validate_directories(input_directory, state_directory)

    with (
        own_run(state_directory) as lock_descriptor,
        dashboard_process(
            state_directory, config.dashboard_port, enabled=config.dashboard_enabled
        ),
    ):
        with closing(open_database(state_directory)) as connection:
            recover_interrupted(connection)
            recover_model_attempts(connection)
            if config.diagnostic:
                register_inputs(connection, input_directory)
                run_workers(state_directory, config.worker_count, lock_descriptor)
                return
            settings = load_settings(config.configuration_path)
            key = read_mapping_key()
            run = prepare_run(connection, input_directory, settings, key)
            bind_output_directory(connection, run.manifest)
            run_workers(
                state_directory,
                config.worker_count,
                lock_descriptor,
                resolution_task_id=run.resolution_task_id,
                remote_enabled=settings.remote.enabled,
            )
            reconcile_run(connection, run, key)
