"""Run the pinned YuNet detector on bounded overlapping full-resolution tiles."""

import hashlib
import math
from pathlib import Path

import numpy as np
from PIL import Image

from redactor.schemas.pixels import PixelDetector, PixelMask
from redactor.utils.constants import (
    PIXEL_FACE,
    YUNET_FILENAME,
    YUNET_MAXIMUM_CANDIDATES,
    YUNET_NMS_THRESHOLD,
    YUNET_SCORE_THRESHOLD,
    YUNET_SHA256,
    YUNET_TILE_OVERLAP,
    YUNET_TILE_SIZE,
)
from redactor.utils.errors import ERROR_LOCAL_INFERENCE, ERROR_LOCAL_UNAVAILABLE


def load_face_detector(directory: Path) -> PixelDetector:
    import cv2

    path = directory / YUNET_FILENAME
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != YUNET_SHA256
    ):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    detector = cv2.FaceDetectorYN.create(
        str(path),
        "",
        (YUNET_TILE_SIZE, YUNET_TILE_SIZE),
        YUNET_SCORE_THRESHOLD,
        YUNET_NMS_THRESHOLD,
        YUNET_MAXIMUM_CANDIDATES,
    )

    def locate(path: Path) -> tuple[PixelMask, ...]:
        try:
            found: set[tuple[int, int, int, int]] = set()
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                stride = YUNET_TILE_SIZE - YUNET_TILE_OVERLAP
                for top in range(0, rgb.height, stride):
                    for left in range(0, rgb.width, stride):
                        right = min(left + YUNET_TILE_SIZE, rgb.width)
                        bottom = min(top + YUNET_TILE_SIZE, rgb.height)
                        tile = np.asarray(rgb.crop((left, top, right, bottom)))[
                            :, :, ::-1
                        ].copy()
                        detector.setInputSize((right - left, bottom - top))
                        _, faces = detector.detect(tile)
                        if faces is None:
                            continue
                        if (
                            faces.ndim != 2
                            or faces.shape[1] != 15
                            or not np.isfinite(faces).all()
                        ):
                            raise ValueError(ERROR_LOCAL_INFERENCE)
                        for face in faces:
                            x, y, width, height = map(float, face[:4])
                            box = (
                                max(0, left + math.floor(x)),
                                max(0, top + math.floor(y)),
                                min(rgb.width, left + math.ceil(x + width)),
                                min(rgb.height, top + math.ceil(y + height)),
                            )
                            if box[0] >= box[2] or box[1] >= box[3]:
                                raise ValueError(ERROR_LOCAL_INFERENCE)
                            found.add(box)
                            if len(found) > YUNET_MAXIMUM_CANDIDATES:
                                raise ValueError(ERROR_LOCAL_INFERENCE)
            return tuple(PixelMask(box=box, kind=PIXEL_FACE) for box in sorted(found))
        except Exception:
            raise ValueError(ERROR_LOCAL_INFERENCE) from None

    return locate
