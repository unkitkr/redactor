"""Load explicitly supplied local ONNX weights without a training framework."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import onnxruntime
    from tokenizers import Tokenizer

from redactor.utils.constants import EVALUATION_ONNX_THREADS


def load_session(path: Path) -> "onnxruntime.InferenceSession":
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = EVALUATION_ONNX_THREADS
    options.inter_op_num_threads = EVALUATION_ONNX_THREADS
    options.enable_cpu_mem_arena = False
    return onnxruntime.InferenceSession(
        str(path), options, providers=["CPUExecutionProvider"]
    )


def load_tokenizer(path: Path) -> "Tokenizer":
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer
