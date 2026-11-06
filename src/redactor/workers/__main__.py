"""Internal entry point; the coordinator passes an inherited run-lock handle."""

import argparse
import os
import sys
from pathlib import Path

from redactor.schemas.worker import WorkerConfig
from redactor.utils.constants import EXIT_FAILURE, EXIT_SUCCESS
from redactor.utils.errors import ERROR_WORKER_FAILED
from redactor.workers.run import consume_tasks
from redactor.workers.runtime import consume_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_directory", type=Path)
    parser.add_argument("coordinator_pid", type=int)
    parser.add_argument("lock_descriptor", type=int)
    parser.add_argument("--resolution-task-id")
    parser.add_argument("--inference", action="store_true")
    parser.add_argument("--all-steps", action="store_true")
    parser.add_argument("--remote-enabled", action="store_true")
    config = WorkerConfig.model_validate(vars(parser.parse_args()))

    try:
        if config.resolution_task_id is None:
            consume_tasks(config.state_directory, config.coordinator_pid)
        else:
            consume_pipeline(config)
    except Exception:
        # This process boundary must not leak paths or input data in tracebacks.
        print(ERROR_WORKER_FAILED, file=sys.stderr)
        return EXIT_FAILURE
    finally:
        os.close(config.lock_descriptor)
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
