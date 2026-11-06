"""GLiNER token-level ONNX adapter for the pinned Edge and Small exports.

Preprocessing and start/end/inside decoding follow the upstream GLiNER contract.
This deliberately supports that export family only, with no silent truncation.
"""

import re
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.onnx import load_session, load_tokenizer
from redactor.schemas.entities import EntityType, NerAdapter, TextEntities, TextEntity
from redactor.schemas.models import GlinerConfiguration
from redactor.utils.constants import (
    GLINER_CONFIG,
    GLINER_INPUT_NAMES,
    GLINER_LABELS,
    GLINER_LOGIT_BOUND,
    GLINER_MAXIMUM_CANDIDATES,
    GLINER_MAXIMUM_TOKENS,
    GLINER_THRESHOLD,
    GLINER_WEIGHTS,
    GLINER_WORD_PATTERN,
    ONNX_FLOAT_TYPE,
    ONNX_INTEGER_TYPE,
    TOKENIZER_FILENAME,
)
from redactor.utils.errors import (
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)


def load_gliner(directory: Path) -> NerAdapter:
    try:
        configuration = GlinerConfiguration.model_validate_json(
            (directory / GLINER_CONFIG).read_bytes()
        )
    except (OSError, ValueError):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
    tokenizer = load_tokenizer(directory / TOKENIZER_FILENAME)
    entity_token = tokenizer.token_to_id(configuration.ent_token)
    separator_token = tokenizer.token_to_id(configuration.sep_token)
    if (
        entity_token is None
        or separator_token is None
        or entity_token == separator_token
    ):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    session = load_session(directory / GLINER_WEIGHTS)
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if (
        {item.name for item in inputs} != set(GLINER_INPUT_NAMES)
        or any(
            item.type != ONNX_INTEGER_TYPE or len(item.shape) != 2 for item in inputs
        )
        or len(outputs) != 1
        or outputs[0].type != ONNX_FLOAT_TYPE
        or len(outputs[0].shape) != 4
        or outputs[0].shape[-1] != 3
    ):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    prompt = [
        value
        for label, _ in GLINER_LABELS
        for value in (configuration.ent_token, label)
    ] + [configuration.sep_token]

    def recognize(text: str) -> tuple[TextEntity, ...]:
        words = list(re.finditer(GLINER_WORD_PATTERN, text))
        if not words:
            return ()
        encoding = tokenizer.encode(
            prompt + [word.group() for word in words], is_pretokenized=True
        )
        if len(encoding.ids) > configuration.max_len:
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
        if sum(value > 0 for value in mask) != len(words):
            raise ValueError(ERROR_LOCAL_INFERENCE)
        results = session.run(
            None,
            {
                "input_ids": np.array([encoding.ids], dtype=np.int64),
                "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
                "words_mask": np.array([mask], dtype=np.int64),
                "text_lengths": np.array([[len(words)]], dtype=np.int64),
            },
        )
        expected_shape = (1, len(words), len(GLINER_LABELS), 3)
        if len(results) != 1:
            raise ValueError(ERROR_LOCAL_INFERENCE)
        logits = results[0]
        if (
            not isinstance(logits, np.ndarray)
            or logits.shape != expected_shape
            or not np.issubdtype(logits.dtype, np.floating)
            or not np.isfinite(logits).all()
        ):
            raise ValueError(ERROR_LOCAL_INFERENCE)
        scores = 1 / (
            1 + np.exp(-np.clip(logits[0], -GLINER_LOGIT_BOUND, GLINER_LOGIT_BOUND))
        )
        return decode_tokens(text, words, scores)

    return recognize


def decode_tokens(
    text: str, words: list[re.Match[str]], scores: NDArray[np.float32]
) -> tuple[TextEntity, ...]:
    if (
        len(words) > GLINER_MAXIMUM_TOKENS
        or scores.shape != (len(words), len(GLINER_LABELS), 3)
        or not np.issubdtype(scores.dtype, np.floating)
        or not np.isfinite(scores).all()
        or np.any(scores < 0)
        or np.any(scores > 1)
    ):
        raise ValueError(ERROR_LOCAL_INFERENCE)
    threshold = GLINER_THRESHOLD
    candidates: list[tuple[float, int, int, str, str]] = []
    for start_value, label_value in np.argwhere(scores[:, :, 0] > threshold):
        start, label_index = int(start_value), int(label_value)
        label, entity_type = GLINER_LABELS[label_index]
        # Compute each interval's minimum once. Repeatedly scanning every span
        # would make dense model output cubic in the number of words.
        inside_scores = np.minimum.accumulate(scores[start:, label_index, 2])
        end_offsets = np.flatnonzero(
            (scores[start:, label_index, 1] > threshold) & (inside_scores >= threshold)
        )
        if len(candidates) + len(end_offsets) > GLINER_MAXIMUM_CANDIDATES:
            raise ValueError(ERROR_LOCAL_INFERENCE)
        for offset in map(int, end_offsets):
            end = start + offset
            score = float(
                min(
                    float(inside_scores[offset]),
                    scores[start, label_index, 0],
                    scores[end, label_index, 1],
                )
            )
            candidates.append(
                (score, words[start].start(), words[end].end(), entity_type, label)
            )
    accepted: list[TextEntity] = []
    for _, start, end, kind, label in sorted(
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
                label=label,
            )
        )
    return validate_entity_evidence(text, TextEntities(entities=tuple(accepted)))
