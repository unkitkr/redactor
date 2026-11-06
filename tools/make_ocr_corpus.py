"""Build fixed OCR challenge images from synthetic cards and the supplied fixture."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from redactor.schemas.evaluation import OcrExample, OcrReference
from redactor.utils.constants import EVALUATION_OCR_DIRECTORY, EVALUATION_OCR_VARIANTS


def synthetic_card(
    lines: tuple[tuple[str, bool], ...],
) -> tuple[Image.Image, tuple[OcrReference, ...]]:
    image = Image.new("RGB", (1100, 500), "white")
    drawing = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=32)
    regions = []
    for index, (text, sensitive) in enumerate(lines):
        position = (60, 45 + index * 65)
        drawing.text(position, text, font=font, fill="black")
        regions.append(
            OcrReference(
                text=text,
                box=drawing.textbbox(position, text, font=font),
                sensitive=sensitive,
            )
        )
    return image, tuple(regions)


def rotate_box(
    region: OcrReference, width: int, height: int, degrees: float
) -> OcrReference:
    angle = math.radians(degrees)
    points = []
    for x in (region.box[0], region.box[2]):
        for y in (region.box[1], region.box[3]):
            centered_x, centered_y = x - width / 2, y - height / 2
            points.append(
                (
                    math.cos(angle) * centered_x
                    + math.sin(angle) * centered_y
                    + width / 2,
                    -math.sin(angle) * centered_x
                    + math.cos(angle) * centered_y
                    + height / 2,
                )
            )
    return region.model_copy(
        update={
            "box": (
                min(p[0] for p in points),
                min(p[1] for p in points),
                max(p[0] for p in points),
                max(p[1] for p in points),
            )
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path(EVALUATION_OCR_DIRECTORY)
    )
    parser.add_argument(
        "--wristband", type=Path, default=Path("input/wristband_photo.jpg")
    )
    arguments = parser.parse_args()
    arguments.directory.mkdir(parents=True, exist_ok=True)
    cards = (
        (
            ("Elena Marlow", True),
            ("MRN 00817364", True),
            ("DOB 07/19/1978", True),
            ("Dr. Anika Solberg", True),
            ("Metformin 500 mg", False),
            ("Glucose 104 mg/dL", False),
        ),
        (
            ("Zoë Duvall", True),
            ("ID QX-740298", True),
            ("Admit 2026-03-14", True),
            ("Dr. René Marchand", True),
            ("ALLERGY: PENICILLIN", False),
            ("BP 124/78 mmHg", False),
        ),
    )
    bases = [
        (f"synthetic-{i}", *synthetic_card(lines), "\n".join(line for line, _ in lines))
        for i, lines in enumerate(cards, 1)
    ]
    wristband_regions = tuple(
        OcrReference(text=text, box=box, sensitive=sensitive)
        for text, box, sensitive in (
            ("KOWALCZYK, BERNARD", (140, 171, 587, 197), True),
            ("0090574", (208, 220, 325, 241), True),
            ("06/04/1936", (416, 220, 565, 241), True),
            ("Dr. Desai", (140, 260, 257, 281), True),
            ("05/24/2026", (351, 260, 501, 281), True),
            ("ALLERGY: PENICILLIN", (140, 297, 409, 318), False),
        )
    )
    bases.append(
        (
            "wristband",
            Image.open(arguments.wristband).convert("RGB"),
            wristband_regions,
            (
                "KOWALCZYK, BERNARD\nMRN 0090574 DOB 06/04/1936 M\n"
                "Dr. Desai ADM 05/24/2026\nALLERGY: PENICILLIN"
            ),
        )
    )
    examples = []
    for name, original, regions, reference in bases:
        for variant in EVALUATION_OCR_VARIANTS:
            image = original.copy()
            adjusted = regions
            if variant == "rotated":
                image = image.rotate(
                    5, resample=Image.Resampling.BICUBIC, fillcolor="white"
                )
                adjusted = tuple(
                    rotate_box(region, image.width, image.height, 5)
                    for region in regions
                )
            elif variant == "blurred":
                image = image.filter(ImageFilter.GaussianBlur(1.5))
            elif variant == "low_contrast":
                image = ImageEnhance.Contrast(image).enhance(0.2)
            path = arguments.directory / f"{name}-{variant}.png"
            image.save(path)
            examples.append(
                OcrExample(
                    case_id=f"{name}-{variant}",
                    image=str(path),
                    reference_text=reference,
                    regions=adjusted,
                )
            )
    (arguments.directory / "manifest.json").write_text(
        json.dumps(
            [item.model_dump() for item in examples], ensure_ascii=False, indent=2
        )
        + "\n"
    )
    print(f"Created {len(examples)} labelled OCR images")


if __name__ == "__main__":
    main()
