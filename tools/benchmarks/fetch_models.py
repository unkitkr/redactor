"""Fetch pinned evaluation artifacts before entering the offline runtime container."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def matches(path: Path, digest: str) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("benchmarks/model-artifacts.json")
    )
    arguments = parser.parse_args()
    for artifact in json.loads(arguments.manifest.read_text()):
        path = Path(artifact["path"])
        if path.is_absolute() or ".." in path.parts or path.parts[0] != ".models":
            raise ValueError("Model artifact must stay inside .models")
        if matches(path, artifact["sha256"]):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".part")
        try:
            with (
                urllib.request.urlopen(artifact["url"], timeout=120) as response,
                temporary.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if temporary.stat().st_size != artifact["bytes"] or not matches(
                temporary, artifact["sha256"]
            ):
                raise ValueError("Model artifact does not match its pinned checksum")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        print(path, flush=True)


if __name__ == "__main__":
    main()
