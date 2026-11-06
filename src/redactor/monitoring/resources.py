"""Serve packaged assets and explicitly listed benchmark images only."""

from importlib.resources import files
from pathlib import Path

from redactor.monitoring.files import read_bounded_file
from redactor.schemas.benchmarks import BenchmarkSnapshot
from redactor.utils.constants import (
    MONITOR_ASSET_PREFIX,
    MONITOR_IMAGE_CONTENT_TYPE,
    MONITOR_MAX_IMAGE_BYTES,
    MONITOR_STATIC_DIRECTORY,
    MONITOR_STATIC_FILES,
    PNG_SIGNATURE,
)


def read_static_asset(route: str) -> tuple[bytes, str] | None:
    for name, content_type in MONITOR_STATIC_FILES:
        if route == MONITOR_ASSET_PREFIX + name or (
            route == "/" and name == MONITOR_STATIC_FILES[0][0]
        ):
            resource = files("redactor.monitoring").joinpath(
                MONITOR_STATIC_DIRECTORY, name
            )
            return resource.read_bytes(), content_type
    return None


def read_reference_image(
    route: str, directory: Path, snapshot: BenchmarkSnapshot
) -> tuple[bytes, str] | None:
    """The public snapshot, never a request path, determines the filename."""
    image = next((image for image in snapshot.images if image.url == route), None)
    if image is None or directory.is_symlink():
        return None
    path = directory / f"{image.case_id}.png"
    if path.resolve().parent != directory.resolve():
        return None
    try:
        payload = read_bounded_file(path, MONITOR_MAX_IMAGE_BYTES)
    except (OSError, ValueError):
        return None
    if not payload.startswith(PNG_SIGNATURE):
        return None
    return payload, MONITOR_IMAGE_CONTENT_TYPE
