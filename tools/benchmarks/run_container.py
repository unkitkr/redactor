"""Run one benchmark process with the assignment's CPU and memory limits."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from time import perf_counter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    root = Path.cwd().resolve()
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    )
    digest = hashlib.sha256()
    for directory in ("src", "tools"):
        for path in sorted((root / directory).rglob("*.py")):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    image = subprocess.check_output(
        ["docker", "image", "inspect", "redactor:evaluation", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    mounts = ("src", "tools", ".models", "benchmarks", "tmp/ocr-corpus")
    docker = [
        "docker",
        "run",
        "--name",
        arguments.name,
        "--cpus",
        "2",
        "--memory",
        "1g",
        "--memory-swap",
        "1g",
        "--network",
        "none",
        "--workdir",
        "/work",
        "--env",
        "PYTHONPATH=/work/src",
        "--env",
        f"REDACTOR_EVALUATION_REVISION={revision}",
        "--env",
        f"REDACTOR_EVALUATION_DIRTY={str(dirty).lower()}",
    ]
    for directory in mounts:
        docker.extend(
            [
                "--volume",
                f"{root / directory}:/work/{directory}"
                + ("" if directory == "benchmarks" else ":ro"),
            ]
        )
    started = perf_counter()
    result = subprocess.run([*docker, "redactor:evaluation", *command], check=False)
    wall_seconds = perf_counter() - started
    inspection = json.loads(
        subprocess.check_output(["docker", "inspect", arguments.name], text=True)
    )[0]
    report = {
        "image_id": image,
        "revision": revision,
        "dirty_tree": dirty,
        "python_source_sha256": digest.hexdigest(),
        "command": command,
        "cpus": 2,
        "memory_bytes": 1073741824,
        "memory_swap_bytes": 1073741824,
        "network": "none",
        "wall_seconds_including_container_start": wall_seconds,
        "exit_code": result.returncode,
        "oom_killed": inspection["State"]["OOMKilled"],
    }
    arguments.receipt.parent.mkdir(parents=True, exist_ok=True)
    arguments.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
