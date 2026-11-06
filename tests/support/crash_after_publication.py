"""Install a verified artifact, then die before acknowledging publication."""

import os
import signal
import sys
from pathlib import Path

from redactor.persistence.client import claim_task, open_queue
from redactor.persistence.files.publication import publish_verified_artifact
from redactor.persistence.files.results import read_step_result
from redactor.schemas.verification import VerificationVerdict
from redactor.utils.constants import STEP_PUBLISH


def main() -> None:
    with open_queue(Path(sys.argv[1])) as connection:
        task = claim_task(connection, step=STEP_PUBLISH)
        assert task is not None
        verification_task_id = sys.argv[2]
        verdict = read_step_result(
            connection, verification_task_id, VerificationVerdict
        )
        publish_verified_artifact(
            connection, task, verification_task_id, verdict.context
        )
        os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()
