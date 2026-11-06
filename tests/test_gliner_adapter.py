"""The model decoder preserves stable spans and rejects unsafe model output."""

import re

import numpy as np
import pytest

from redactor.inference.adapters.gliner import decode_tokens
from redactor.utils.constants import (
    GLINER_LABELS,
    GLINER_MAXIMUM_TOKENS,
    GLINER_WORD_PATTERN,
)
from redactor.utils.errors import ERROR_LOCAL_INFERENCE


def test_token_decoder_keeps_score_order_and_rejects_unsafe_output() -> None:
    text = "Alpha Beta Gamma"
    words = list(re.finditer(GLINER_WORD_PATTERN, text))
    scores = np.full((len(words), len(GLINER_LABELS), 3), 0.9, dtype=np.float32)
    entities = decode_tokens(text, words, scores)
    # Equal scores keep the original start, label, end ordering. Each earliest
    # singleton wins over the equally scored overlapping spans and labels.
    assert [(entity.text, entity.entity_type) for entity in entities] == [
        ("Alpha", "person"),
        ("Beta", "person"),
        ("Gamma", "person"),
    ]

    scores.fill(0)
    scores[0, 0, 0] = 0.9
    scores[1, 0, 1] = 0.8
    scores[:2, 0, 2] = 0.7
    assert [entity.text for entity in decode_tokens(text, words, scores)] == [
        "Alpha Beta"
    ]
    for invalid in (np.nan, np.inf, -0.1, 1.1):
        damaged = scores.copy()
        damaged[0, 0, 0] = invalid
        with pytest.raises(ValueError, match=ERROR_LOCAL_INFERENCE):
            decode_tokens(text, words, damaged)

    dense_text = " ".join("word" for _ in range(GLINER_MAXIMUM_TOKENS))
    dense_words = list(re.finditer(GLINER_WORD_PATTERN, dense_text))
    dense_scores = np.ones((len(dense_words), len(GLINER_LABELS), 3), dtype=np.float32)
    # Dense, finite outputs are also unsafe: reject the whole inference rather
    # than returning a truncated set of entities or allocating millions of spans.
    with pytest.raises(ValueError, match=ERROR_LOCAL_INFERENCE):
        decode_tokens(dense_text, dense_words, dense_scores)
