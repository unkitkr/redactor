"""GLiNER token-level ONNX adapter for the pinned Edge and Small exports.

Preprocessing and start/end/inside decoding follow the upstream GLiNER contract.
This deliberately supports that export family only, with no silent truncation.
"""

import json
import re
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from redactor.evaluation.onnx import load_session, load_tokenizer
from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.entities import EntityType, NerAdapter, TextEntities, TextEntity
from redactor.utils.constants import (
    EVALUATION_GLINER_CONFIG,
    EVALUATION_GLINER_LABELS,
    EVALUATION_GLINER_THRESHOLD,
    EVALUATION_GLINER_WEIGHTS,
    EVALUATION_TOKENIZER,
    EVALUATION_WORD_PATTERN,
)
from redactor.utils.errors import ERROR_LOCAL_INPUT, ERROR_LOCAL_UNAVAILABLE


def load_gliner(directory: Path) -> NerAdapter:
    configuration = json.loads((directory / EVALUATION_GLINER_CONFIG).read_text())
    if configuration["span_mode"] != "token_level":
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    session = load_session(directory / EVALUATION_GLINER_WEIGHTS)
    tokenizer = load_tokenizer(directory / EVALUATION_TOKENIZER)
    prompt = [
        value
        for label, _ in EVALUATION_GLINER_LABELS
        for value in (configuration["ent_token"], label)
    ] + [configuration["sep_token"]]

    def recognize(text: str) -> tuple[TextEntity, ...]:
        words = list(re.finditer(EVALUATION_WORD_PATTERN, text))
        if not words:
            return ()
        encoding = tokenizer.encode(
            prompt + [word.group() for word in words], is_pretokenized=True
        )
        if len(encoding.ids) > configuration["max_len"]:
            raise ValueError(ERROR_LOCAL_INPUT)
        previous = None
        mask = []
        for word_id in encoding.word_ids:
            selected = (
                word_id is not None and word_id >= len(prompt) and word_id != previous
            )
            mask.append(
                word_id - len(prompt) + 1 if selected and word_id is not None else 0
            )
            previous = word_id
        logits = session.run(
            None,
            {
                "input_ids": np.array([encoding.ids], dtype=np.int64),
                "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
                "words_mask": np.array([mask], dtype=np.int64),
                "text_lengths": np.array([[len(words)]], dtype=np.int64),
            },
        )[0]
        expected_shape = (1, len(words), len(EVALUATION_GLINER_LABELS), 3)
        if logits.shape != expected_shape:
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
        scores = 1 / (1 + np.exp(-np.clip(logits[0], -80, 80)))
        return decode_tokens(text, words, scores)

    return recognize


def decode_tokens(
    text: str, words: list[re.Match[str]], scores: NDArray[np.float32]
) -> tuple[TextEntity, ...]:
    threshold = EVALUATION_GLINER_THRESHOLD
    candidates: list[tuple[float, int, int, str]] = []
    for start_value, label_value in np.argwhere(scores[:, :, 0] > threshold):
        start, label_index = int(start_value), int(label_value)
        entity_type = EVALUATION_GLINER_LABELS[label_index][1]
        ends = np.flatnonzero(scores[:, label_index, 1] > threshold)
        for end in map(int, ends):
            if end < start:
                continue
            inside = scores[start : end + 1, label_index, 2]
            score = float(
                min(
                    min(map(float, inside)),
                    scores[start, label_index, 0],
                    scores[end, label_index, 1],
                )
            )
            if score >= threshold:
                candidates.append(
                    (score, words[start].start(), words[end].end(), entity_type)
                )
    accepted: list[TextEntity] = []
    for _, start, end, kind in sorted(
        candidates, key=lambda item: item[0], reverse=True
    ):
        if any(start < item.end and item.start < end for item in accepted):
            continue
        accepted.append(
            TextEntity(
                start=start,
                end=end,
                text=text[start:end],
                entity_type=cast(EntityType, kind),
            )
        )
    return validate_entity_evidence(text, TextEntities(entities=tuple(accepted)))
