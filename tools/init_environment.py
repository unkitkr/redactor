"""Create a private local environment file without replacing an existing key."""

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

from redactor.utils.constants import (
    ENVIRONMENT_FALSE,
    LOCAL_ENVIRONMENT_FILENAME,
    MAPPING_KEY_ENVIRONMENT,
    MODEL_ENABLED_ENVIRONMENT,
    PRIVATE_FILE_MODE,
    SECRET_KEY_BYTES,
    TEXT_ENCODING,
)


def create_environment(output: Path) -> bool:
    """Create the file exclusively; return False when its path already exists."""
    try:
        descriptor = os.open(
            output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE_MODE
        )
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding=TEXT_ENCODING, newline="\n") as stream:
        os.fchmod(stream.fileno(), PRIVATE_FILE_MODE)
        key = base64.b64encode(secrets.token_bytes(SECRET_KEY_BYTES)).decode("ascii")
        stream.write(
            f"{MAPPING_KEY_ENVIRONMENT}={key}\n"
            f"{MODEL_ENABLED_ENVIRONMENT}={ENVIRONMENT_FALSE[0]}\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(LOCAL_ENVIRONMENT_FILENAME),
        help="Environment file to create; an existing path is preserved.",
    )
    arguments = parser.parse_args()
    try:
        created = create_environment(arguments.output)
    except OSError as error:
        print(
            f"Could not create {arguments.output}: {error.strerror}.",
            file=sys.stderr,
        )
        return 1
    if created:
        print(f"Created {arguments.output}; retain it with your run state for replay.")
    else:
        print(f"Existing {arguments.output} preserved; keep its key for replay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
