"""Turn termination signals into normal stack unwinding and child cleanup."""

import signal
from collections.abc import Generator
from contextlib import contextmanager
from types import FrameType

from redactor.utils.constants import SIGNAL_EXIT_BASE


@contextmanager
def handle_shutdown_signals() -> Generator[None, None, None]:
    """Install handlers only for the CLI lifetime, on the main thread."""
    shutdown_signals = (signal.SIGINT, signal.SIGTERM)
    previous = {signum: signal.getsignal(signum) for signum in shutdown_signals}

    def request_shutdown(signum: int, frame: FrameType | None) -> None:
        # Further signals must not interrupt bounded worker cleanup.
        for shutdown_signal in shutdown_signals:
            signal.signal(shutdown_signal, signal.SIG_IGN)
        raise SystemExit(SIGNAL_EXIT_BASE + signum)

    try:
        for signum in shutdown_signals:
            signal.signal(signum, request_shutdown)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
