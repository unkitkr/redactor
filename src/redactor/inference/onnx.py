"""Load explicitly supplied local ONNX weights without a training framework."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import onnxruntime
    from tokenizers import Tokenizer

from redactor.utils.constants import ONNX_CPU_PROVIDER, ONNX_THREADS
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE


def load_session(path: Path) -> "onnxruntime.InferenceSession":
    if not path.is_file():
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    try:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = ONNX_THREADS
        options.inter_op_num_threads = ONNX_THREADS
        options.enable_cpu_mem_arena = False
        return onnxruntime.InferenceSession(
            str(path), options, providers=[ONNX_CPU_PROVIDER]
        )
    except Exception:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None


def load_tokenizer(path: Path) -> "Tokenizer":
    if not path.is_file():
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(path))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        return tokenizer
    except Exception:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
