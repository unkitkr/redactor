"""Locate barcode carriers without placing decoded identifying payloads in logs."""

from pathlib import Path

from PIL import Image

from redactor.schemas.pixels import PixelMask
from redactor.utils.constants import PIXEL_BARCODE
from redactor.utils.errors import ERROR_LOCAL_INFERENCE


def locate_barcodes(path: Path) -> tuple[PixelMask, ...]:
    import zxingcpp

    try:
        with Image.open(path) as image:
            results = zxingcpp.read_barcodes(image, return_errors=True)
            boxes: list[PixelMask] = []
            for result in results:
                position = result.position
                points = (
                    position.top_left,
                    position.top_right,
                    position.bottom_left,
                    position.bottom_right,
                )
                left, top = min(p.x for p in points), min(p.y for p in points)
                right, bottom = (
                    max(p.x for p in points) + 1,
                    max(p.y for p in points) + 1,
                )
                if not (
                    0 <= left < right <= image.width
                    and 0 <= top < bottom <= image.height
                ):
                    raise ValueError(ERROR_LOCAL_INFERENCE)
                # Even a located code with a checksum failure is identifying
                # content that must not survive a successful publication.
                boxes.append(
                    PixelMask(box=(left, top, right, bottom), kind=PIXEL_BARCODE)
                )
        return tuple(boxes)
    except Exception:
        raise ValueError(ERROR_LOCAL_INFERENCE) from None
