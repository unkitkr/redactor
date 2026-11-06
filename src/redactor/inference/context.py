"""Ground model observations in a value with its native field label visible."""

from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.entities import NerAdapter, TextEntities, TextEntity
from redactor.schemas.native import NativeRecord
from redactor.utils.constants import NER_FIELD_LABEL_SEPARATOR
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE, ERROR_LOCAL_INPUT


def contextual_ner(
    adapter: NerAdapter, *, field_label: str, maximum_characters: int
) -> NerAdapter:
    """The composite input binds both the label and value to cached observations."""
    if not field_label:
        return adapter
    if field_label.splitlines() != [field_label] or not field_label.strip():
        raise ValueError(ERROR_ENTITY_EVIDENCE)
    prefix = field_label + NER_FIELD_LABEL_SEPARATOR
    return _bounded_context_ner(
        adapter, prefix=prefix, suffix="", maximum_characters=maximum_characters
    )


def record_ner(
    adapter: NerAdapter,
    record: NativeRecord,
    column_index: int,
    maximum_characters: int,
) -> NerAdapter:
    """Select context whose exact source ranges reproduce this native record."""
    if not 0 <= column_index < len(record.values) or (
        record.field_labels and len(record.field_labels) != len(record.values)
    ):
        raise ValueError(ERROR_ENTITY_EVIDENCE)
    context = record.text_context
    if context is None:
        return contextual_ner(
            adapter,
            field_label=record.field_labels[column_index]
            if record.field_labels
            else "",
            maximum_characters=maximum_characters,
        )
    if len(context.ranges) != len(record.values):
        raise ValueError(ERROR_ENTITY_EVIDENCE)
    previous = 0
    for value, span in zip(record.values, context.ranges, strict=True):
        if not (
            previous <= span.start <= span.end <= len(context.text)
            and context.text[span.start : span.end] == value
        ):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        previous = span.end
    target = context.ranges[column_index]
    return _bounded_context_ner(
        adapter,
        prefix=context.text[: target.start],
        suffix=context.text[target.end :],
        maximum_characters=maximum_characters,
    )


def _bounded_context_ner(
    adapter: NerAdapter, *, prefix: str, suffix: str, maximum_characters: int
) -> NerAdapter:
    if len(prefix) + len(suffix) > maximum_characters:
        raise ValueError(ERROR_LOCAL_INPUT)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        if len(prefix) + len(text) + len(suffix) > maximum_characters:
            raise ValueError(ERROR_LOCAL_INPUT)
        contextual = prefix + text + suffix
        target_end = len(prefix) + len(text)
        observed = validate_entity_evidence(
            contextual, TextEntities(entities=adapter(contextual))
        )
        selected: list[TextEntity] = []
        for entity in observed:
            if entity.end <= len(prefix) or entity.start >= target_end:
                continue
            if entity.start < len(prefix) or entity.end > target_end:
                raise ValueError(ERROR_ENTITY_EVIDENCE)
            selected.append(
                entity.model_copy(
                    update={
                        "start": entity.start - len(prefix),
                        "end": entity.end - len(prefix),
                    }
                )
            )
        return validate_entity_evidence(text, TextEntities(entities=tuple(selected)))

    return recognize
