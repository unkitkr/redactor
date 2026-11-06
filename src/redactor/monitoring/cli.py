"""Run a local dashboard separately from worker execution."""

import argparse
import os
import sys
from pathlib import Path
from socket import socket
from socketserver import BaseServer
from typing import cast
from wsgiref.simple_server import WSGIRequestHandler, make_server

from redactor.monitoring.server import create_application
from redactor.utils.constants import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    MONITOR_BENCHMARK_DIRECTORY,
    MONITOR_HOST,
    MONITOR_IMAGE_DIRECTORY,
    MONITOR_PORT,
    MONITOR_READY_TOKEN,
    MONITOR_REQUEST_TIMEOUT_SECONDS,
    MONITOR_SERVER_POLL_SECONDS,
    STATE_DIRECTORY,
)
from redactor.utils.errors import ERROR_MONITOR_STARTUP


def main() -> int:
    parser = argparse.ArgumentParser(description="View queue state and benchmarks.")
    parser.add_argument("--state", type=Path, default=STATE_DIRECTORY)
    parser.add_argument("--benchmarks", type=Path, default=MONITOR_BENCHMARK_DIRECTORY)
    parser.add_argument("--images", type=Path, default=MONITOR_IMAGE_DIRECTORY)
    parser.add_argument("--host", default=MONITOR_HOST)
    parser.add_argument("--port", type=int, default=MONITOR_PORT)
    parser.add_argument("--ready-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    application = create_application(
        arguments.state, arguments.benchmarks, arguments.images
    )
    try:
        # socketserver invokes its handler as a callable; no custom class is needed.
        handler = cast(type[WSGIRequestHandler], handle_http_request)
        with make_server(
            arguments.host, arguments.port, application, handler_class=handler
        ) as server:
            if arguments.ready_fd is not None:
                try:
                    os.write(arguments.ready_fd, MONITOR_READY_TOKEN)
                finally:
                    os.close(arguments.ready_fd)
            print(
                f"Dashboard: http://{arguments.host}:{server.server_port}", flush=True
            )
            if arguments.parent_pid is None:
                server.serve_forever()
            else:
                server.timeout = MONITOR_SERVER_POLL_SECONDS
                while os.getppid() == arguments.parent_pid:
                    server.handle_request()
    except KeyboardInterrupt:
        return EXIT_SUCCESS
    except (OSError, ValueError, OverflowError):
        print(ERROR_MONITOR_STARTUP, file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_SUCCESS


def handle_http_request(
    request: socket, client_address: tuple[str, int], server: BaseServer
) -> WSGIRequestHandler:
    """An incomplete browser request cannot indefinitely retain an orphan server."""
    request.settimeout(MONITOR_REQUEST_TIMEOUT_SECONDS)
    return WSGIRequestHandler(request, client_address, server)
