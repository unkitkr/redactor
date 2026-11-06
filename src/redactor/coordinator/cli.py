"""Command-line arguments and PHI-safe startup failures."""

import argparse
import sys
from pathlib import Path

from redactor.coordinator.run import run_coordinator
from redactor.coordinator.signals import handle_shutdown_signals
from redactor.schemas.coordinator import CoordinatorConfig
from redactor.utils.constants import (
    DEFAULT_WORKER_COUNT,
    EXIT_FAILURE,
    EXIT_SUCCESS,
    INPUT_DIRECTORY,
    MONITOR_DEFAULT_ENABLED,
    MONITOR_PORT,
    STATE_DIRECTORY,
)
from redactor.utils.errors import COORDINATOR_FAILURE_CODES, ERROR_COORDINATOR_FAILED


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pseudonymize native files through durable, verified steps."
    )
    parser.add_argument(
        "--input", dest="input_directory", type=Path, default=INPUT_DIRECTORY
    )
    parser.add_argument(
        "--state", dest="state_directory", type=Path, default=STATE_DIRECTORY
    )
    parser.add_argument(
        "--workers", dest="worker_count", type=int, default=DEFAULT_WORKER_COUNT
    )
    parser.add_argument("--config", dest="configuration_path", type=Path)
    parser.add_argument("--diagnostic", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-dashboard",
        dest="dashboard_enabled",
        action="store_false",
        default=MONITOR_DEFAULT_ENABLED,
        help="Disable the optional local progress dashboard.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=MONITOR_PORT,
        help="Local progress dashboard port.",
    )
    arguments = parser.parse_args()

    try:
        config = CoordinatorConfig.model_validate(vars(arguments))
        with handle_shutdown_signals():
            run_coordinator(config)
    except Exception as error:
        code = next(
            (code for code in COORDINATOR_FAILURE_CODES if error.args == (code,)),
            ERROR_COORDINATOR_FAILED,
        )
        print(code, file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_SUCCESS
