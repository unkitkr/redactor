"""Edit joined text across XML runs while retaining the original run structure."""

from difflib import SequenceMatcher
from xml.etree.ElementTree import Element

from redactor.utils.errors import ERROR_STRUCTURE


def replace_run_text(root: Element, tag: str, replacement: str) -> None:
    nodes = tuple(root.iter(tag))
    if not nodes:
        if replacement:
            raise ValueError(ERROR_STRUCTURE)
        return
    original = "".join(node.text or "" for node in nodes)
    boundaries = []
    offset = 0
    for node in nodes:
        end = offset + len(node.text or "")
        boundaries.append((offset, end))
        offset = end
    written = ["" for _ in nodes]
    for operation, start, stop, new_start, new_stop in SequenceMatcher(
        None, original, replacement, autojunk=False
    ).get_opcodes():
        if operation == "equal":
            for index, (left, right) in enumerate(boundaries):
                written[index] += original[max(start, left) : min(stop, right)]
        elif operation in ("replace", "insert"):
            index = next(
                (index for index, (_, right) in enumerate(boundaries) if start < right),
                len(nodes) - 1,
            )
            written[index] += replacement[new_start:new_stop]
    if "".join(written) != replacement:
        raise ValueError(ERROR_STRUCTURE)
    for node, value in zip(nodes, written, strict=True):
        node.text = value
