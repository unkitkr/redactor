"""Compare our pinned ONNX decoder with the upstream GLiNER Python wrapper.

Run this in a separate development environment with gliner==0.2.30, torch==2.15.0,
transformers==5.22.1 and the regular evaluation dependencies. It is a correctness
check, not a memory-constrained production configuration.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from redactor.evaluation.gliner import load_gliner
from redactor.evaluation.text import evaluate_text_examples
from redactor.schemas.entities import TextEntity
from redactor.schemas.evaluation import TextExample
from redactor.utils.constants import EVALUATION_GLINER_LABELS, EVALUATION_TEXT_CORPUS


def compare(directory: Path, examples: tuple[TextExample, ...]) -> dict[str, object]:
    from gliner import GLiNER

    reference = GLiNER.from_pretrained(
        str(directory),
        load_onnx_model=True,
        onnx_model_file="onnx/model_quint8.onnx",
        local_files_only=True,
    )
    adapter = load_gliner(directory)
    observed = {example.text: example.case_id for example in examples}

    def record(text: str) -> tuple[TextEntity, ...]:
        observed.setdefault(
            text, "derived:" + hashlib.sha256(text.encode()).hexdigest()
        )
        return adapter(text)

    evaluate_text_examples(examples, record, combined=True)
    labels = [label for label, _ in EVALUATION_GLINER_LABELS]
    mapping = dict(EVALUATION_GLINER_LABELS)
    mismatches = []
    for text, case_id in observed.items():
        expected = reference.predict_entities(
            text, labels, threshold=0.3, flat_ner=True
        )
        actual = adapter(text)
        truth = sorted(
            (item["start"], item["end"], mapping[item["label"]]) for item in expected
        )
        predicted = sorted((item.start, item.end, item.entity_type) for item in actual)
        if truth != predicted:
            mismatches.append(
                {"case_id": case_id, "reference": truth, "adapter": predicted}
            )
    return {
        "model": str(directory),
        "reference_package": "gliner " + importlib.metadata.version("gliner"),
        "case_count_including_derived_inputs": len(observed),
        "matching_cases": len(observed) - len(mismatches),
        "mismatches": mismatches,
    }


def main() -> None:
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    torch.set_num_threads(1)
    examples = tuple(
        TextExample.model_validate(item)
        for item in json.loads(Path(EVALUATION_TEXT_CORPUS).read_text())
    )
    results = [
        compare(Path(".models") / f"gliner-pii-{variant}-v1.0", examples)
        for variant in ("edge", "small")
    ]
    arguments.output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))
    if any(item["mismatches"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
