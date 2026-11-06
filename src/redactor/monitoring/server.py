"""A standard-library HTTP application without processing or model imports."""

import json
import re
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs
from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

from redactor.monitoring.benchmarks import read_benchmarks
from redactor.monitoring.resources import read_reference_image, read_static_asset
from redactor.persistence.queue.monitoring import read_queue_snapshot
from redactor.schemas.benchmarks import BenchmarkSnapshot
from redactor.utils.constants import (
    MONITOR_BENCHMARK_CACHE_SECONDS,
    MONITOR_BENCHMARK_ROUTE,
    MONITOR_CACHE_SECONDS,
    MONITOR_HTTP_HEADERS,
    MONITOR_JSON_CONTENT_TYPE,
    MONITOR_MAX_REQUEST_PATH,
    MONITOR_QUERY_LIMIT,
    MONITOR_QUEUE_ROUTE,
    MONITOR_RUN_PATTERN,
)


def create_application(
    state_directory: Path, benchmark_directory: Path, image_directory: Path
) -> WSGIApplication:
    """Caches belong to this application and retain only one snapshot per view."""

    @lru_cache(maxsize=1)
    def queue_json(run: str | None, interval: int) -> bytes:
        return read_queue_snapshot(state_directory, run).model_dump_json().encode()

    @lru_cache(maxsize=1)
    def benchmarks(interval: int) -> BenchmarkSnapshot:
        return read_benchmarks(benchmark_directory, image_directory)

    def route_request(route: str, query: str) -> tuple[bytes, str] | None:
        if route == MONITOR_QUEUE_ROUTE:
            parameters = parse_qs(
                query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=MONITOR_QUERY_LIMIT,
            )
            if set(parameters) - {"run"} or len(parameters.get("run", [])) > 1:
                raise ValueError
            run = parameters.get("run", [None])[0]
            if run is not None and re.fullmatch(MONITOR_RUN_PATTERN, run) is None:
                raise ValueError
            return (
                queue_json(run, int(monotonic() / MONITOR_CACHE_SECONDS)),
                MONITOR_JSON_CONTENT_TYPE,
            )
        if query:
            raise ValueError
        asset = read_static_asset(route)
        if asset is not None:
            return asset
        snapshot = benchmarks(int(monotonic() / MONITOR_BENCHMARK_CACHE_SECONDS))
        if route == MONITOR_BENCHMARK_ROUTE:
            return snapshot.model_dump_json().encode(), MONITOR_JSON_CONTENT_TYPE
        return read_reference_image(route, image_directory, snapshot)

    def application(environment: WSGIEnvironment, start: StartResponse) -> list[bytes]:
        status = HTTPStatus.OK
        resource = None
        route = environment.get("PATH_INFO", "")
        query = environment.get("QUERY_STRING", "")
        method = environment.get("REQUEST_METHOD", "")
        if method not in ("GET", "HEAD"):
            status = HTTPStatus.METHOD_NOT_ALLOWED
        elif len(route) + len(query) > MONITOR_MAX_REQUEST_PATH:
            status = HTTPStatus.REQUEST_URI_TOO_LONG
        else:
            try:
                resource = route_request(route, query)
                if resource is None:
                    status = HTTPStatus.NOT_FOUND
            except ValueError:
                status = HTTPStatus.BAD_REQUEST
            except Exception:
                # HTTP failures must not expose private filesystem or DB details.
                status = HTTPStatus.SERVICE_UNAVAILABLE
        payload, content_type = resource or (
            json.dumps({"error": status.phrase}).encode(),
            MONITOR_JSON_CONTENT_TYPE,
        )
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(payload))),
            *MONITOR_HTTP_HEADERS,
        ]
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            headers.append(("Allow", "GET, HEAD"))
        start(f"{status.value} {status.phrase}", headers)
        return [] if method == "HEAD" else [payload]

    return application
