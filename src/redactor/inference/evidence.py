"""Reject invented text, invalid offsets and conflicting model spans."""

from redactor.schemas.entities import TextEntities, TextEntity
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE


def validate_entity_evidence(text: str, result: TextEntities) -> tuple[TextEntity, ...]:
    entities = tuple(
        sorted(result.entities, key=lambda entity: (entity.start, entity.end))
    )
    previous_end = 0
    for entity in entities:
        if (
            entity.start < previous_end
            or entity.end <= entity.start
            or entity.end > len(text)
            or text[entity.start : entity.end] != entity.text
            or not entity.text.strip()
        ):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        previous_end = entity.end
    return entities
