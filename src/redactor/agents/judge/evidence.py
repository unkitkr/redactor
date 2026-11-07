"""Build the bounded, saved-output evidence summary submitted for judging."""

import base64
from collections.abc import Sequence

from pydantic import ValidationError

from redactor.schemas.judge import JudgeEvidence, JudgeEvidenceItem, JudgeImage
from redactor.schemas.verification import ResidualCheck
from redactor.utils.constants import (
    JUDGE_IMAGE_REFERENCE_PREFIX,
    JUDGE_MAXIMUM_EVIDENCE_BYTES,
    JUDGE_MAXIMUM_EVIDENCE_ITEMS,
    JUDGE_MAXIMUM_IMAGE_BYTES,
    JUDGE_MAXIMUM_IMAGES,
    JUDGE_MAXIMUM_ITEM_CHARACTERS,
    JUDGE_MAXIMUM_VERIFIED_SPANS,
    JUDGE_TEXT_REFERENCE_PREFIX,
)
from redactor.utils.errors import ERROR_JUDGE_EVIDENCE

SavedImage = tuple[bytes, tuple[int, int], str]


def build_judge_evidence(
    checks: Sequence[ResidualCheck],
    images: Sequence[SavedImage] = (),
) -> JudgeEvidence:
    """Bound the evidence and count every dropped entry instead of hiding it.

    Only saved-output text, locally verified spans and saved-output image
    frames enter the summary; original-input content never does. Span lists
    are capped, and a dropped span is treated as unverified by the judge,
    which can only add findings.
    """
    candidates = tuple(check for check in checks if check.text.strip())
    omitted_items = max(0, len(candidates) - JUDGE_MAXIMUM_EVIDENCE_ITEMS)
    items: list[JudgeEvidenceItem] = []
    evidence_bytes = 0
    for check in candidates[:JUDGE_MAXIMUM_EVIDENCE_ITEMS]:
        size = len(check.text.encode())
        if (
            len(check.text) > JUDGE_MAXIMUM_ITEM_CHARACTERS
            or evidence_bytes + size > JUDGE_MAXIMUM_EVIDENCE_BYTES
        ):
            omitted_items += 1
            continue
        evidence_bytes += size
        items.append(
            JudgeEvidenceItem(
                reference=f"{JUDGE_TEXT_REFERENCE_PREFIX}:{len(items)}",
                text=check.text,
                verified_spans=tuple(
                    sorted(check.allowed, key=lambda span: (span.start, span.end))
                )[:JUDGE_MAXIMUM_VERIFIED_SPANS],
            )
        )
    omitted_images = max(0, len(images) - JUDGE_MAXIMUM_IMAGES)
    encoded: list[JudgeImage] = []
    for content, frame_size, media_type in images[:JUDGE_MAXIMUM_IMAGES]:
        if len(content) > JUDGE_MAXIMUM_IMAGE_BYTES:
            omitted_images += 1
            continue
        try:
            encoded.append(
                JudgeImage(
                    reference=f"{JUDGE_IMAGE_REFERENCE_PREFIX}:{len(encoded)}",
                    media_type=media_type,
                    width=frame_size[0],
                    height=frame_size[1],
                    content_base64=base64.b64encode(content).decode("ascii"),
                )
            )
        except ValidationError:
            raise ValueError(ERROR_JUDGE_EVIDENCE) from None
    return JudgeEvidence(
        items=tuple(items),
        images=tuple(encoded),
        omitted_items=omitted_items,
        omitted_images=omitted_images,
    )
