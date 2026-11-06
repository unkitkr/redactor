"""Score OCR text recovery separately from complete-identifier localization."""

import re
from pathlib import Path
from time import perf_counter
from typing import cast

from redactor.schemas.evaluation import OcrAdapter, OcrExample, OcrRegion
from redactor.utils.constants import EVALUATION_OCR_COVERAGE
from redactor.utils.failures import failure_reason


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_character in enumerate(left, 1):
        current = [row]
        for column, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def intersection_area(left: OcrRegion, right: OcrRegion) -> float:
    x0, y0 = max(left.box[0], right.box[0]), max(left.box[1], right.box[1])
    x1, y1 = min(left.box[2], right.box[2]), min(left.box[3], right.box[3])
    return max(0, x1 - x0) * max(0, y1 - y0)


def evaluate_ocr(
    examples: tuple[OcrExample, ...], adapter: OcrAdapter
) -> dict[str, object]:
    cases = []
    for example in examples:
        started = perf_counter()
        error = None
        try:
            output = adapter(Path(example.image))
        except Exception as exception:
            output = ()
            error = failure_reason(exception)
        recovered = normalized(" ".join(item.text for item in output))
        truth = normalized(example.reference_text)
        sensitive = [item for item in example.regions if item.sensitive]
        clinical = [item for item in example.regions if not item.sensitive]
        localized = 0
        clinical_overmask = 0
        for reference in sensitive:
            # Only detections intersecting the true identifier contribute to its
            # text and coverage. An unrelated occurrence elsewhere cannot pass it.
            nearby = [item for item in output if intersection_area(item, reference) > 0]
            if normalized(reference.text) not in normalized(
                " ".join(item.text for item in nearby)
            ):
                continue
            if not nearby:
                continue
            enclosing = OcrRegion(
                text=reference.text,
                box=(
                    min(item.box[0] for item in nearby),
                    min(item.box[1] for item in nearby),
                    max(item.box[2] for item in nearby),
                    max(item.box[3] for item in nearby),
                ),
            )
            area = (reference.box[2] - reference.box[0]) * (
                reference.box[3] - reference.box[1]
            )
            localized += (
                intersection_area(enclosing, reference) / area
                >= EVALUATION_OCR_COVERAGE
            )
            clinical_overmask += any(
                intersection_area(enclosing, item) > 0 for item in clinical
            )
        cases.append(
            {
                "case_id": example.case_id,
                "seconds": perf_counter() - started,
                "reference_characters": len(truth),
                "character_edits": edit_distance(truth, recovered),
                "identifier_count": len(sensitive),
                "identifiers_recovered": sum(
                    normalized(item.text) in recovered for item in sensitive
                ),
                "identifiers_localized": localized,
                "clinical_count": len(clinical),
                "clinical_recovered": sum(
                    normalized(item.text) in recovered for item in clinical
                ),
                "identifier_boxes_overlapping_clinical": clinical_overmask,
                "error": error,
            }
        )
    fields = (
        "reference_characters",
        "character_edits",
        "identifier_count",
        "identifiers_recovered",
        "identifiers_localized",
        "clinical_count",
        "clinical_recovered",
        "identifier_boxes_overlapping_clinical",
    )
    totals = {field: sum(cast(int, item[field]) for item in cases) for field in fields}
    return {
        "cases": cases,
        "totals": totals,
        "character_error_rate": totals["character_edits"]
        / totals["reference_characters"],
    }
