"""Extract bounded image evidence for standalone and embedded native images."""

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.formats.images import pixel_digest, read_image_frames
from redactor.inference.adapters.barcodes import locate_barcodes
from redactor.inference.adapters.faces import load_face_detector
from redactor.policy.pixels import text_pixel_masks
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.pixels import PixelFrame
from redactor.utils.constants import (
    PIXEL_PNG_FORMAT,
    PIXEL_TEMPORARY_FILENAME,
    YUNET_DIRECTORY,
)


def analyze_image_content(
    source: Path,
    settings: PipelineSettings,
    detector: NerAdapter,
    ocr: OcrAdapter,
) -> tuple[tuple[PixelFrame, ...], dict[str, int]]:
    frames = read_image_frames(source, settings.resources)
    faces = load_face_detector(settings.local.model_directory / YUNET_DIRECTORY)
    assessed: list[PixelFrame] = []
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / PIXEL_TEMPORARY_FILENAME
        for frame in frames:
            frame.save(path, format=PIXEL_PNG_FORMAT)
            assessed.append(
                PixelFrame(
                    width=frame.width,
                    height=frame.height,
                    sha256=pixel_digest(frame),
                    regions=ocr(path),
                    masks=locate_barcodes(path) + faces(path),
                )
            )
    counts: Counter[str] = Counter()
    for index, evidence in enumerate(assessed):
        masks, findings = text_pixel_masks(
            evidence.regions, (evidence.width, evidence.height), detector
        )
        counts.update(findings)
        counts.update(mask.kind for mask in evidence.masks)
        assessed[index] = evidence.model_copy(update={"masks": evidence.masks + masks})
    return tuple(assessed), dict(counts)
