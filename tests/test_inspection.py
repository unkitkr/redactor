"""Real parser and durable-step checks, including hostile container boundaries."""

import sqlite3
from functools import partial
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from redactor.coordinator.bootstrap import prepare_run
from redactor.formats.inspection import inspect_file
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    get_task,
    recover_interrupted,
)
from redactor.schemas.configuration import PipelineSettings, ResourceSettings
from redactor.schemas.formats import FileInspection
from redactor.utils.constants import (
    DOCX_MAIN_PART,
    DOCX_MAIN_TYPE,
    DOCX_ROOT_TAG,
    OOXML_CONTENT_NAMESPACE,
    OOXML_CONTENT_TYPES,
    OOXML_OFFICE_DOCUMENT_RELATIONSHIP,
    OOXML_PACKAGE_RELATIONSHIPS,
    OOXML_RELATIONSHIP_NAMESPACE,
    STEP_ANALYZE,
    STEP_INSPECT,
    STEP_RESOLVE,
)
from redactor.utils.errors import (
    ERROR_CONTAINER,
    ERROR_INPUT_CHANGED,
    ERROR_RESOURCE_LIMIT,
    ERROR_STRUCTURE,
)
from redactor.workers.inspect import inspect_task
from redactor.workers.pipeline import execute_task


def test_inspection_is_durable_and_rejection_does_not_block_analysis(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    good = input_directory / "records.bin"
    good.write_bytes(b'person,mrn\n"Synthetic Example",12345\n')
    broken = input_directory / "broken.docx"
    broken.write_bytes(b"PK\x03\x04truncated-private-content")
    settings = PipelineSettings()
    key = bytes(range(32))
    run = prepare_run(connection, input_directory, settings, key)
    handler = partial(inspect_task, resources=settings.resources, mapping_key=key)
    seen = {}
    for _ in range(2):
        task = claim_task(connection, step=STEP_INSPECT)
        assert task is not None
        execute_task(connection, task, {STEP_INSPECT: handler})
        outcome = read_step_result(
            connection, task.task_id, FileInspection, encryption_key=key
        )
        seen[task.input_path.name] = outcome
        accepted = get_task(connection, task.task_id)
        assert accepted.result_path is not None
        assert b"person" not in accepted.result_path.read_bytes()
        recover_interrupted(connection)
        assert get_task(connection, task.task_id).attempt_count == 1
        analysis = claim_task(connection, step=STEP_ANALYZE)
        assert analysis is not None
        assert (
            analysis.task_id
            == prepare_successor(connection, task, STEP_ANALYZE).task_id
        )
        complete_task(connection, analysis)
    assert seen[good.name].file_type == "csv"
    assert seen[good.name].reason is None
    assert seen[broken.name].reason == ERROR_CONTAINER
    resolution = claim_task(connection, step=STEP_RESOLVE)
    assert resolution is not None and resolution.task_id == run.resolution_task_id

    # Input replacement after inventory cannot be accepted as the old task's result.
    good.write_bytes(b"changed,input\n1,2\n")
    prepare_run(connection, input_directory, settings, key)
    changed_task = claim_task(connection, step=STEP_INSPECT)
    assert changed_task is not None
    changed_task.input_path.write_bytes(b"replaced after inventory")
    with pytest.raises(ValueError, match=ERROR_INPUT_CHANGED):
        handler(connection, changed_task)


def test_office_validation_checks_members_and_ignores_the_extension(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mislabelled.csv"
    content_types = (
        f'<Types xmlns="{OOXML_CONTENT_NAMESPACE}">'
        f'<Override PartName="/{DOCX_MAIN_PART}" ContentType="{DOCX_MAIN_TYPE}"/>'
        "</Types>"
    )
    base = {
        OOXML_CONTENT_TYPES: content_types,
        OOXML_PACKAGE_RELATIONSHIPS: (
            f'<Relationships xmlns="{OOXML_RELATIONSHIP_NAMESPACE}">'
            f'<Relationship Id="rId1" Type="{OOXML_OFFICE_DOCUMENT_RELATIONSHIP}" '
            f'Target="{DOCX_MAIN_PART}"/></Relationships>'
        ),
        DOCX_MAIN_PART: (
            f'<document xmlns="{DOCX_ROOT_TAG[1:].split("}")[0]}">'
            "<body><p><r><t>synthetic text</t></r></p></body></document>"
        ),
    }
    cases: tuple[tuple[dict[str, str], str | None], ...] = (
        ({}, None),
        ({"../outside.xml": "<outside/>"}, ERROR_CONTAINER),
        ({"customXml/data.xml": "<broken>"}, ERROR_CONTAINER),
        (
            {
                "customXml/data.xml": (
                    '<!DOCTYPE x [<!ENTITY data "private">]><x>&data;</x>'
                )
            },
            ERROR_CONTAINER,
        ),
        ({"customXml/data.xml": "<x>" * 18 + "</x>" * 18}, ERROR_RESOURCE_LIMIT),
    )
    for extra, expected in cases:
        with ZipFile(path, "w") as archive:
            for name, payload in (base | extra).items():
                archive.writestr(name, payload)
        result = inspect_file(path, ResourceSettings())
        assert result.reason == expected
        if expected is None:
            assert result.file_type == "docx"
    path.write_bytes(path.read_bytes()[:-8])
    assert inspect_file(path, ResourceSettings()).reason == ERROR_CONTAINER


def test_streaming_json_and_raster_inspection_enforce_limits(tmp_path: Path) -> None:
    path = tmp_path / "records.data"
    resources = ResourceSettings(chunk_bytes=7, max_record_bytes=64)
    path.write_bytes(
        b'{"resourceType":"Bundle","entry":[{"value":"escaped \\" word"}]}'
    )
    result = inspect_file(path, resources)
    assert result.file_type == "fhir" and result.reason is None
    for payload, expected in (
        (b'{"name":"first","name":"second"}', ERROR_STRUCTURE),
        (b'{"data":[1,2,', ERROR_STRUCTURE),
        (b'{"data":"' + b"x" * 65 + b'"}', ERROR_RESOURCE_LIMIT),
        (b"[" * 17 + b"0" + b"]" * 17, ERROR_RESOURCE_LIMIT),
    ):
        path.write_bytes(payload)
        assert inspect_file(path, resources).reason == expected
    with Image.new("RGB", (20, 10)) as image:
        image.save(path, format="PNG")
    result = inspect_file(path, resources)
    assert result.file_type == "png" and result.units == 1 and result.reason is None
    small_pixels = resources.model_copy(update={"max_image_pixels": 100})
    assert inspect_file(path, small_pixels).reason == ERROR_RESOURCE_LIMIT
    path.write_bytes(path.read_bytes()[:-12])
    assert inspect_file(path, resources).reason == ERROR_STRUCTURE
