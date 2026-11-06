"""OCR uses bounded real images and rejects missing or malformed observations."""

import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from redactor.inference.model_loader import load_local_ocr
from redactor.inference.ocr_loader import bounded_ocr
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.ocr import OcrRegion
from redactor.utils.errors import (
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)


def create_image(path: Path) -> Path:
    image = Image.new("RGB", (600, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (20, 20),
        "Patient Alice Stone\nPulse 72 bpm",
        fill="black",
        font=ImageFont.load_default(size=32),
    )
    image.save(path)
    return path


def test_common_ocr_boundary_bounds_images_and_rejects_invalid_regions(
    tmp_path: Path,
) -> None:
    image = create_image(tmp_path / "image.png")
    calls = 0
    observations: tuple[OcrRegion, ...] = (
        OcrRegion(text="Pulse", box=(20, 60, 150, 100)),
    )

    def backend(_: Path) -> tuple[OcrRegion, ...]:
        nonlocal calls
        calls += 1
        return observations

    adapter = bounded_ocr(backend, ResourceSettings())
    assert adapter(image) == observations
    assert calls == 1
    for limits in (
        ResourceSettings(max_image_pixels=10),
        ResourceSettings(max_native_file_bytes=10),
    ):
        with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
            bounded_ocr(backend, limits)(image)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        adapter(broken)
    animation = tmp_path / "multiple.tiff"
    with Image.open(image) as frame:
        frame.save(animation, save_all=True, append_images=[frame.copy()])
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        adapter(animation)
    thin = tmp_path / "thin.png"
    Image.new("RGB", (2000, 1), "white").save(thin)
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        adapter(thin)
    assert calls == 1

    for invalid in (
        (),
        (OcrRegion(text=" ", box=(0, 0, 10, 10)),),
        (OcrRegion(text="word", box=(0, 0, 900, 10)),),
        (OcrRegion(text="word", box=(10, 0, 0, 10)),),
        (OcrRegion.model_construct(text="word", box=(0, 0, float("nan"), 10)),),
    ):
        observations = invalid
        with pytest.raises(ValueError, match=ERROR_LOCAL_INFERENCE):
            adapter(image)

    def changing_backend(path: Path) -> tuple[OcrRegion, ...]:
        Image.new("RGB", (600, 160), "black").save(path)
        return (OcrRegion(text="word", box=(0, 0, 10, 10)),)

    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        bounded_ocr(changing_backend, ResourceSettings())(image)
    for backend_name in ("tesseract", "ppocr"):
        with pytest.raises(ValueError, match=ERROR_LOCAL_UNAVAILABLE):
            load_local_ocr(
                LocalSettings(
                    ocr=backend_name,
                    ocr_directory=tmp_path / "missing-model",
                ),
                ResourceSettings(),
            )


def test_tesseract_subprocess_errors_timeout_and_invalid_tsv_are_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from redactor.inference.adapters import tesseract

    image = create_image(tmp_path / "image.png")
    directory = tmp_path / "model"
    directory.mkdir()
    (directory / "eng.traineddata").write_bytes(b"external boundary fixture")
    executable = tmp_path / "tesseract"
    mode = tmp_path / "mode.txt"
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
        "width\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t20\t20\t100\t40\t99\tPatient\n"
        "5\t1\t2\t1\t1\t1\t80\t70\t400\t70\t95\t \n"
    )
    blank_only_tsv = "".join(tsv.splitlines(keepends=True)[::2])
    executable.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys, time\n"
        f"mode = pathlib.Path({json.dumps(str(mode))}).read_text()\n"
        "if mode == 'timeout': time.sleep(5)\n"
        "if mode == 'failure':\n"
        "    print('sensitive backend diagnostic', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        f"content = {tsv!r} if mode == 'valid' else 'malformed TSV'\n"
        f"if mode == 'blankonly': content = {blank_only_tsv!r}\n"
        "pathlib.Path(sys.argv[2]).with_suffix('.tsv').write_text(content)\n"
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    adapter = load_local_ocr(
        LocalSettings(ocr="tesseract", ocr_directory=directory), ResourceSettings()
    )
    mode.write_text("valid")
    assert [region.text for region in adapter(image)] == ["Patient"]
    for value in ("malformed", "blankonly", "failure", "timeout"):
        mode.write_text(value)
        if value == "timeout":
            monkeypatch.setattr(tesseract, "OCR_TIMEOUT_SECONDS", 0.02)
        with pytest.raises(ValueError, match=f"^{ERROR_LOCAL_INFERENCE}$"):
            adapter(image)


def test_installed_ppocr_uses_local_weights_and_rejects_partial_stage_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = Path(".models/ppocr-v5").resolve()
    if not (directory / "en_PP-OCRv5_rec_mobile.onnx").is_file():
        pytest.skip("Local PP-OCR weights are not installed")
    import rapidocr
    from rapidocr.utils.download_file import DownloadFile
    from rapidocr.utils.output import RapidOCROutput

    downloads = 0

    def no_download(_: object) -> None:
        nonlocal downloads
        downloads += 1
        raise AssertionError("OCR must use installed assets only")

    monkeypatch.setattr(DownloadFile, "run", no_download)
    image = create_image(tmp_path / "image.png")
    settings = LocalSettings(ocr="ppocr", ocr_directory=directory)
    adapter = load_local_ocr(settings, ResourceSettings())
    recognized = " ".join(region.text for region in adapter(image))
    assert re.search(r"\b72\b", recognized)
    assert "Patient" in recognized
    assert downloads == 0

    localized = load_local_ocr(settings, ResourceSettings(), word_boxes=True)(image)
    words = [word for line in localized for word in line.words]
    assert any(word.text == "Alice" for word in words)
    assert any(word.text == "72" for word in words)
    name = next(word for word in words if word.text == "Alice")
    pulse = next(word for word in words if word.text == "72")
    # OCR boxes may overlap at their margins; the pixel verifier must check
    # clinical intersections before applying a mask, rather than assume none.
    assert name.box[1] + name.box[3] < pulse.box[1] + pulse.box[3]
    assert "".join("".join(line.text.split()) for line in localized) == "".join(
        "".join(word.text.split()) for word in words
    )
    assert downloads == 0

    damaged = tmp_path / "missing-dictionary"
    damaged.mkdir()
    for source in directory.glob("*.onnx"):
        target = damaged / source.name
        if source.name == "en_PP-OCRv5_rec_mobile.onnx":
            content = source.read_bytes()
            assert content.count(b"\n\tcharacter") == 1
            target.write_bytes(content.replace(b"\n\tcharacter", b"\n\tcharacteX"))
        else:
            target.symlink_to(source)
    with pytest.raises(ValueError, match=ERROR_LOCAL_UNAVAILABLE):
        load_local_ocr(
            settings.model_copy(update={"ocr_directory": damaged}), ResourceSettings()
        )
    assert downloads == 0

    result: object = RapidOCROutput()

    def controlled_engine(**arguments: object) -> Callable[[str], object]:
        parameters = arguments["params"]
        assert isinstance(parameters, dict)
        assert parameters["Rec.lang_type"] == rapidocr.LangRec.EN
        assert Path(parameters["Rec.model_path"]).name == "en_PP-OCRv5_rec_mobile.onnx"
        return lambda _path: result

    monkeypatch.setattr(rapidocr, "RapidOCR", controlled_engine)
    # The default "eng" above and explicit "en" select the same English export.
    # Reuse the controlled boundary for the latter instead of another real engine.
    controlled = load_local_ocr(
        settings.model_copy(update={"ocr_language": "en"}), ResourceSettings()
    )
    for invalid_result in (
        RapidOCROutput(),
        RapidOCROutput(txts=("word",)),
        RapidOCROutput(
            txts=("word",),
            boxes=np.full((1, 4, 2), np.nan),
            scores=(1.0,),
        ),
        RapidOCROutput(
            txts=("word",),
            boxes=np.ones((2, 4, 2)),
            scores=(1.0,),
        ),
    ):
        result = invalid_result
        with pytest.raises(ValueError, match=f"^{ERROR_LOCAL_INFERENCE}$"):
            controlled(image)


def test_installed_tesseract_reads_a_real_image_when_available(tmp_path: Path) -> None:
    directory = Path(".models/tessdata")
    if (
        shutil.which("tesseract") is None
        or not (directory / "eng.traineddata").is_file()
    ):
        pytest.skip("Tesseract and local English weights are not installed")
    image = create_image(tmp_path / "image.png")
    adapter = load_local_ocr(
        LocalSettings(ocr="tesseract", ocr_directory=directory), ResourceSettings()
    )
    assert "72" in " ".join(region.text for region in adapter(image))


def test_saved_ocr_label_cues_leave_following_values_assessed(tmp_path: Path) -> None:
    from redactor.inference.model_loader import load_local_ner
    from redactor.policy.pixels import located_words, scan_image_text
    from redactor.schemas.ocr import OcrResponse

    path = tmp_path / "ocr.json"
    path.write_text(
        OcrResponse(
            regions=tuple(
                OcrRegion(text=label, box=(0, index * 20, 100, index * 20 + 15))
                for index, label in enumerate(("MRN", "DOB", "NPI", "SSN"))
            )
        ).model_dump_json()
    )
    records = OcrResponse.model_validate_json(path.read_text())
    ner = load_local_ner(LocalSettings())
    text, _ = located_words(records.regions)
    scan_image_text(text, (), ner)
    for value in (
        "DOB 1934-05-16",
        "MRN: 9012345",
        "SSN: 123-45-6789",
        "NPI: 1234567893",
        "DOB Amina Keller",
    ):
        with pytest.raises(ValueError):
            scan_image_text(value, (), ner)
