"""Thin startup sequence; workers own individual task execution."""

from contextlib import closing

from redactor.coordinator.inventory import register_inputs, validate_directories
from redactor.coordinator.ownership import own_run
from redactor.coordinator.processes import run_workers
from redactor.persistence.database import open_database
from redactor.persistence.models.budget import recover_model_attempts
from redactor.persistence.queue.tasks import recover_interrupted
from redactor.schemas.coordinator import CoordinatorConfig


def run_coordinator(config: CoordinatorConfig) -> None:
    input_directory = config.input_directory.resolve()
    state_directory = config.state_directory.resolve()
    validate_directories(input_directory, state_directory)

    with own_run(state_directory) as lock_descriptor:
        with closing(open_database(state_directory)) as connection:
            recover_interrupted(connection)
            recover_model_attempts(connection)
            register_inputs(connection, input_directory)

        run_workers(state_directory, config.worker_count, lock_descriptor)
