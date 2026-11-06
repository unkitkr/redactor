"""Leave a potentially billed model request outstanding at SIGKILL."""

import os
import signal
import sys
from contextlib import closing
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.model_budget import reserve_attempt
from redactor.persistence.queue import claim_task
from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.provider import ModelReservation

if __name__ == "__main__":
    with closing(open_database(Path(sys.argv[1]))) as connection:
        claimed = claim_task(connection)
        assert claimed is not None
        reservation = reserve_attempt(
            connection, claimed, "request-a", 700, 1000, RemoteSettings()
        )
        assert isinstance(reservation, ModelReservation)
        os.kill(os.getpid(), signal.SIGKILL)
