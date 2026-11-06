"""Public benchmark summaries, excluding source documents and model responses."""

from typing import Literal

from pydantic import BaseModel, NonNegativeInt


class BenchmarkMetric(BaseModel, frozen=True, extra="forbid"):
    """Percent values are fractions; character error rate may exceed one."""

    label: str
    value: int | float | str | None
    unit: Literal["percent", "seconds", "mib", "count", "text"]


class BenchmarkCase(BaseModel, frozen=True, extra="forbid"):
    case_id: str
    metrics: tuple[BenchmarkMetric, ...]


class BenchmarkReport(BaseModel, frozen=True, extra="forbid"):
    id: str
    source: str
    kind: Literal["text", "ocr", "throughput", "diagnostic"]
    model: str
    mode: str
    context: str
    platform: str
    verifier_version: str | None = None
    corpus_sha256: str | None = None
    case_count: NonNegativeInt | None = None
    scope: str
    metrics: tuple[BenchmarkMetric, ...] = ()
    cases: tuple[BenchmarkCase, ...] = ()


class BenchmarkImage(BaseModel, frozen=True, extra="forbid"):
    case_id: str
    url: str


class BenchmarkIssue(BaseModel, frozen=True, extra="forbid"):
    source: str
    reason: str


class BenchmarkSnapshot(BaseModel, frozen=True, extra="forbid"):
    status: Literal["ready", "missing", "unavailable"]
    reports: tuple[BenchmarkReport, ...] = ()
    images: tuple[BenchmarkImage, ...] = ()
    issues: tuple[BenchmarkIssue, ...] = ()
