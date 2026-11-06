"""The actual setup command creates a private key once and preserves it on reuse."""

import base64
import stat
import subprocess
import sys
from pathlib import Path

from redactor.utils.constants import (
    LOCAL_ENVIRONMENT_FILENAME,
    MAPPING_KEY_ENVIRONMENT,
    MODEL_ENABLED_ENVIRONMENT,
    PRIVATE_FILE_MODE,
    SECRET_KEY_BYTES,
)


def test_environment_script_creates_private_file_and_preserves_existing_key(
    tmp_path: Path,
) -> None:
    script = Path(__file__).parents[1] / "tools" / "init_environment.py"
    output = tmp_path / LOCAL_ENVIRONMENT_FILENAME
    first = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    original = output.read_bytes()
    values = dict(line.split("=", 1) for line in original.decode().splitlines())
    assert set(values) == {MAPPING_KEY_ENVIRONMENT, MODEL_ENABLED_ENVIRONMENT}
    encoded_key = values[MAPPING_KEY_ENVIRONMENT]
    assert len(base64.b64decode(encoded_key, validate=True)) == SECRET_KEY_BYTES
    assert values[MODEL_ENABLED_ENVIRONMENT] == "0"
    assert stat.S_IMODE(output.stat().st_mode) == PRIVATE_FILE_MODE
    second = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert output.read_bytes() == original
    assert stat.S_IMODE(output.stat().st_mode) == PRIVATE_FILE_MODE
    assert "preserved" in second.stdout
    assert (
        encoded_key not in first.stdout + first.stderr + second.stdout + second.stderr
    )
