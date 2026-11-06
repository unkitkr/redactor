"""BIO token-classification adapter for the pinned OpenMed INT8 export."""

import json
from pathlib import Path
from typing import cast

import numpy as np

from redactor.evaluation.onnx import load_session, load_tokenizer
from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.entities import EntityType, NerAdapter, TextEntities, TextEntity
from redactor.utils.constants import EVALUATION_OPENMED_TYPES
from redactor.utils.errors import ERROR_LOCAL_INPUT


def load_openmed(directory: Path) -> NerAdapter:
    configuration = json.loads((directory / "config.json").read_text())
    labels = json.loads((directory / "id2label.json").read_text())
    tokenizer = load_tokenizer(directory / "tokenizer.json")
    session = load_session(directory / "model_int8.onnx")
    types = {
        label: kind for kind, values in EVALUATION_OPENMED_TYPES for label in values
    }

    def recognize(text: str) -> tuple[TextEntity, ...]:
        encoding = tokenizer.encode(text)
        if len(encoding.ids) > configuration["max_position_embeddings"]:
            raise ValueError(ERROR_LOCAL_INPUT)
        inputs = {
            "input_ids": np.array([encoding.ids], dtype=np.int64),
            "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([encoding.type_ids], dtype=np.int64),
        }
        logits = session.run(
            None, {item.name: inputs[item.name] for item in session.get_inputs()}
        )[0]
        tags = [labels[str(index)] for index in logits[0].argmax(axis=-1)]
        entities: list[TextEntity] = []
        previous_label = ""
        for tag, (start, end) in zip(tags, encoding.offsets, strict=True):
            label = tag[2:]
            kind = types.get(label)
            if start == end or kind is None:
                previous_label = ""
                continue
            continuing = tag.startswith("I-") and label == previous_label
            # The source labels first and last names separately. Coalesce only
            # adjacent person components, never across punctuation or other text.
            joining_name = (
                kind == "person" and entities and entities[-1].entity_type == kind
            )
            if (
                entities
                and (continuing or joining_name)
                and not text[entities[-1].end : start].strip()
            ):
                prior = entities.pop()
                start = prior.start
            entities.append(
                TextEntity(
                    start=start,
                    end=end,
                    text=text[start:end],
                    entity_type=cast(EntityType, kind),
                )
            )
            previous_label = label
        trimmed = []
        for entity in entities:
            start, end = entity.start, entity.end
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if start < end:
                trimmed.append(
                    entity.model_copy(
                        update={"start": start, "end": end, "text": text[start:end]}
                    )
                )
        return validate_entity_evidence(text, TextEntities(entities=tuple(trimmed)))

    return recognize
