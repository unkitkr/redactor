"""Test subprocess: die after committing evidence and the complete CSV cursor."""

import os
import signal
import sys
from datetime import date
from pathlib import Path

from redactor.formats.csv import inspect_csv, iter_csv_records
from redactor.persistence.client import claim_task, open_queue
from redactor.persistence.identities.observations import save_observation_batch
from redactor.schemas.identity import IdentityEvidence
from redactor.utils.constants import DEFAULT_RECORD_BYTES

with open_queue(Path(sys.argv[1])) as connection:
    task = claim_task(connection)
    assert task is not None
    layout = inspect_csv(task.input_path, DEFAULT_RECORD_BYTES)
    row = next(iter_csv_records(task.input_path, layout, DEFAULT_RECORD_BYTES))
    name, identifier, birth, reference = row.values
    save_observation_batch(
        connection,
        task,
        (
            IdentityEvidence(
                role="patient",
                name=name,
                identifier=identifier,
                identifier_namespace="mrn",
                birth_date=date.fromisoformat(birth),
                reference_date=date.fromisoformat(reference),
                context_key="record-1",
            ),
        ),
        bytes(range(32)),
        sequence=1,
        input_offset=row.end_offset,
        record_count=row.number,
    )
    os.kill(os.getpid(), signal.SIGKILL)
