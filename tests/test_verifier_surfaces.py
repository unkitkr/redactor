"""Saved-file checks cover headers and XML carriers omitted by ordinary readers."""

import sqlite3
import struct
from copy import deepcopy
from pathlib import Path
from xml.etree.ElementTree import SubElement, fromstring, tostring
from zipfile import ZipFile

import pytest

from redactor.coordinator.bootstrap import prepare_run
from redactor.formats.xlsx import read_xlsx, write_xlsx
from redactor.inference.model_loader import load_local_ner
from redactor.persistence.queue.tasks import claim_task
from redactor.schemas.configuration import PipelineSettings, ResourceSettings
from redactor.utils.constants import XLSX_NAMESPACE
from redactor.verification.archive import check_saved_archive
from redactor.verification.xlsx import check_xlsx_surfaces
from redactor.verification.xlsx_preservation import check_xlsx_preservation
from redactor.verification.xlsx_source import check_xlsx_source_surfaces
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.pipeline import execute_task


def test_identifying_csv_header_cannot_bypass_publication_checks(
    connection: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    safe = source / "safe.csv"
    unsafe = source / "unsafe.csv"
    safe.write_text("patient,mrn,comments\nNora Voss,0193,Reviewed.\n")
    unsafe.write_text("patient,mrn,private@example.test\nNora Voss,0193,Reviewed.\n")
    settings = PipelineSettings()
    key = bytes(range(32))
    run = prepare_run(connection, source, settings, key)
    handlers = pipeline_handlers(
        settings, key, load_local_ner(settings.local), run.resolution_task_id
    )
    while task := claim_task(connection):
        execute_task(connection, task, handlers)
    assert (tmp_path / "output/published/safe.csv").is_file()
    assert not (tmp_path / "output/published/unsafe.csv").exists()
    assert (
        tmp_path / "output/quarantine/unsafe.csv"
    ).read_bytes() == unsafe.read_bytes()


def test_xlsx_rejects_unassessed_cells_comments_and_processing_instructions(
    tmp_path: Path,
) -> None:
    clean = tmp_path / "clean.xlsx"
    write_xlsx(Path(__file__).parents[1] / "input/billing_export.csv", clean, {})
    resources = ResourceSettings()
    check_xlsx_surfaces(clean, read_xlsx(clean, resources))
    check_xlsx_source_surfaces(clean, read_xlsx(clean, resources))
    with ZipFile(clean) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    sheet = "xl/worksheets/sheet1.xml"
    tag = "{" + XLSX_NAMESPACE + "}"
    mutations: list[tuple[str, bytes]] = []
    for mode in (
        "outside-row",
        "duplicate-cell",
        "duplicate-row",
        "extra-value",
        "tail",
    ):
        root = fromstring(parts[sheet])
        data = root.find(tag + "sheetData")
        assert data is not None
        if mode == "outside-row":
            cell = SubElement(root, tag + "c", {"r": "Z99", "t": "inlineStr"})
            SubElement(SubElement(cell, tag + "is"), tag + "t").text = "Private person"
        elif mode == "duplicate-cell":
            data[1].append(deepcopy(data[1][0]))
        elif mode == "duplicate-row":
            data.append(deepcopy(data[1]))
        elif mode == "extra-value":
            SubElement(data[1][0], tag + "v").text = "Private person"
        else:
            data[1][0].tail = "Private person"
        mutations.append((sheet, tostring(root)))
    for payload in (
        parts["xl/styles.xml"] + b"<!--private outside root-->",
        parts["xl/styles.xml"] + b"<?private person?>",
        parts["xl/styles.xml"].replace(
            b"</styleSheet>", b"<!--private--></styleSheet>"
        ),
    ):
        assert payload != parts["xl/styles.xml"]
        mutations.append(("xl/styles.xml", payload))
    for index, (changed_part, payload) in enumerate(mutations):
        changed = tmp_path / f"unassessed-{index}.xlsx"
        with ZipFile(changed, "w") as archive:
            for name, original in parts.items():
                archive.writestr(name, payload if name == changed_part else original)
        with pytest.raises(ValueError):
            check_xlsx_surfaces(changed, read_xlsx(changed, resources))
        # Rewriting can remove these carriers. Inspect the source too, so their
        # clinical contents cannot silently disappear before verification.
        with pytest.raises(ValueError):
            check_xlsx_source_surfaces(changed, read_xlsx(changed, resources))


def test_saved_archive_rejects_bytes_outside_its_members(tmp_path: Path) -> None:
    clean = tmp_path / "clean.xlsx"
    write_xlsx(Path(__file__).parents[1] / "input/billing_export.csv", clean, {})
    check_saved_archive(clean)
    payload = clean.read_bytes()
    private = b"Private person\n"
    with ZipFile(clean) as archive:
        last = archive.infolist()[-1]
    directory = struct.unpack_from("<I", payload, len(payload) - 6)[0]
    gap = bytearray(payload[:directory] + private + payload[directory:])
    struct.pack_into("<I", gap, len(gap) - 6, directory + len(private))
    # Also claim the inserted bytes as part of the last compressed member.
    # ZIP's reader ignores the data after that member's deflate end marker.
    compressed_tail = gap.copy()
    struct.pack_into(
        "<I",
        compressed_tail,
        last.header_offset + 18,
        last.compress_size + len(private),
    )
    central_entry = payload.rfind(b"PK\x01\x02") + len(private)
    struct.pack_into(
        "<I", compressed_tail, central_entry + 20, last.compress_size + len(private)
    )
    for index, contaminated in enumerate(
        (private + payload, payload + private, gap, compressed_tail)
    ):
        changed = tmp_path / f"unaccounted-{index}.xlsx"
        changed.write_bytes(bytes(contaminated))
        # The usual ZIP reader still opens both containers successfully.
        with ZipFile(changed) as archive:
            assert archive.testzip() is None
        with pytest.raises(ValueError):
            check_saved_archive(changed)


def test_saved_workbook_preserves_unedited_layout_and_styles(tmp_path: Path) -> None:
    original = Path(__file__).parents[1] / "input/billing_export.csv"
    clean = tmp_path / "clean.xlsx"
    write_xlsx(original, clean, {})
    resources = ResourceSettings()
    document = read_xlsx(original, resources)
    check_xlsx_preservation(original, clean, document)
    with ZipFile(clean) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for index, part in enumerate(("xl/worksheets/sheet1.xml", "xl/styles.xml")):
        root = fromstring(parts[part])
        if part.endswith("sheet1.xml"):
            element = root.find(f"{{{XLSX_NAMESPACE}}}sheetFormatPr")
            assert element is not None
            element.set("defaultRowHeight", "21")
        else:
            element = root.find(f".//{{{XLSX_NAMESPACE}}}sz")
            assert element is not None
            element.set("val", "18")
        changed = tmp_path / f"altered-structure-{index}.xlsx"
        with ZipFile(changed, "w") as archive:
            for name, payload in parts.items():
                archive.writestr(name, tostring(root) if name == part else payload)
        # Both mutations are valid structural values; only comparing the source
        # proves that the writer preserved the unedited workbook structure.
        check_xlsx_surfaces(changed, read_xlsx(changed, resources))
        with pytest.raises(ValueError, match="clinical_content_changed"):
            check_xlsx_preservation(original, changed, document)
