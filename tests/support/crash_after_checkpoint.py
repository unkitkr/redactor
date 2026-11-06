"""Leave a real committed record followed by an uncommitted suffix, then SIGKILL."""

import hashlib
import os
import signal
import sys
from pathlib import Path

from redactor.persistence.checkpoints import save_checkpoint
from redactor.persistence.client import claim_task, open_queue
from redactor.persistence.files import create_temporary_file
from redactor.schemas.persistence import Checkpoint


def main() -> None:
    with open_queue(Path(sys.argv[1])) as connection:
        task = claim_task(connection)
        assert task is not None
        working_path = create_temporary_file(connection, task)
        prefix = b'"first\nrecord",safe\r\n'
        working_path.write_bytes(prefix)
        save_checkpoint(
            connection,
            task,
            Checkpoint(
                sequence=1,
                task_id=task.task_id,
                artifact_path=working_path,
                input_offset=4,
                output_offset=len(prefix),
                record_count=1,
                output_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
                adapter_version="integration-v1",
                cursor={"record": 1},
            ),
        )
        with working_path.open("ab") as stream:
            stream.write(b'"unfinished')
            stream.flush()
            os.fsync(stream.fileno())
        os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()
