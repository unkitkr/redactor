"""Relay TLS to one fixed endpoint from an isolated benchmark Docker network.

Give this separate container the model hostname as its isolated-network alias.
The pipeline resolves that name to the relay but still validates the endpoint's
TLS certificate. The relay joins an outbound network and forwards opaque bytes
only to the pre-resolved endpoint address. It never handles keys or plaintext.
"""

import argparse
import select
import socket
from concurrent.futures import ThreadPoolExecutor


def tunnel(client: socket.socket, address: str, idle_seconds: float) -> None:
    with client:
        client.settimeout(idle_seconds)
        try:
            with socket.create_connection((address, 443), timeout=idle_seconds) as peer:
                while readable := select.select([client, peer], [], [], idle_seconds)[
                    0
                ]:
                    for source in readable:
                        payload = source.recv(65536)
                        if not payload:
                            return
                        destination = peer if source is client else client
                        destination.sendall(payload)
        except OSError:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--idle-seconds", type=float, default=90)
    arguments = parser.parse_args()
    with (
        socket.create_server(("0.0.0.0", arguments.port)) as server,
        ThreadPoolExecutor(max_workers=4) as workers,
    ):
        while True:
            client, _ = server.accept()
            workers.submit(tunnel, client, arguments.address, arguments.idle_seconds)


if __name__ == "__main__":
    main()
