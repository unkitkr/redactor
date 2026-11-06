"""Expose supported ADT fields using the delimiters declared in MSH."""

import re
from functools import partial
from pathlib import Path
from typing import cast

from redactor.formats.hl7_encoding import (
    decode_component,
    read_message,
)
from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.redaction import ColumnPolicy, FieldKind
from redactor.utils.constants import (
    ACCOUNT_NAMESPACE,
    FIELD_ADDRESS,
    FIELD_BIRTH_DATE,
    FIELD_CLINICAL,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_ID,
    FIELD_PROVIDER_NAME,
    FIELD_RELATIVE_NAME,
    FIELD_SSN,
    FIELD_TEXT,
    FIELD_ZIP,
    HL7_ADDRESS_FIELDS,
    HL7_DATE_FIELDS,
    HL7_IDENTIFIER_FIELDS,
    HL7_NAME_MODE,
    HL7_PHONE_FIELDS,
    HL7_PHONE_MODE,
    HL7_STRUCTURAL_FIELDS,
    HL7_VALUE_MODE,
    LAB_DESCRIPTION_NAMESPACE,
    MRN_NAMESPACE,
    NPI_NAMESPACE,
    SSN_NAMESPACE,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def read_hl7(path: Path, encoding: str) -> NativeDocument:
    message = read_message(path, encoding)
    cells: list[tuple[str, ColumnPolicy, tuple[str, ...]]] = []
    providers: list[NativeRecord] = []
    structural = {
        (segment, field): pattern for segment, field, pattern in HL7_STRUCTURAL_FIELDS
    }

    for segment_number, segment in enumerate(message.segments):
        name = segment[0]
        for index, field in enumerate(segment[1:], 1):
            field_number = index + int(name == "MSH")
            if name == "MSH" and field_number == 2:
                continue
            if not field:
                continue
            position = (name, field_number)
            if position in structural:
                pattern = structural[position].replace(
                    "{component}", re.escape(message.component)
                )
                if re.fullmatch(pattern, field) is None:
                    raise ValueError(ERROR_COVERAGE)
                continue
            for repeat, raw in enumerate(field.split(message.repetition)):
                parts = [
                    decode_component(value, message)
                    for value in raw.split(message.component)
                ]
                prefix = (str(segment_number), str(index), str(repeat))

                add = partial(_add_cell, cells, parts, prefix)

                if position in HL7_DATE_FIELDS:
                    _single(parts)
                    add(
                        0, 1, FIELD_BIRTH_DATE if position == ("PID", 7) else FIELD_DATE
                    )
                elif position in HL7_IDENTIFIER_FIELDS:
                    _single(parts)
                    add(0, 1, FIELD_IDENTIFIER, namespace=f"{name}:{field_number}")
                elif position == ("PID", 3):
                    if len(parts) > 5 or any(parts[1:3]):
                        raise ValueError(ERROR_COVERAGE)
                    identifier_type = parts[4] if len(parts) > 4 else ""
                    if identifier_type not in ("MR", "SS"):
                        raise ValueError(ERROR_COVERAGE)
                    add(
                        0,
                        1,
                        FIELD_PATIENT_ID if identifier_type == "MR" else FIELD_SSN,
                        MRN_NAMESPACE if identifier_type == "MR" else SSN_NAMESPACE,
                    )
                    if len(parts) > 3:
                        add(3, 4, FIELD_IDENTIFIER, "assigning-authority")
                elif position in (("PID", 5), ("PID", 6), ("NK1", 2)):
                    if len(parts) > 3:
                        raise ValueError(ERROR_COVERAGE)
                    add(
                        0,
                        len(parts),
                        FIELD_PATIENT_NAME
                        if position == ("PID", 5)
                        else FIELD_RELATIVE_NAME,
                        mode=HL7_NAME_MODE,
                    )
                elif position in (("PV1", 7), ("PV1", 8), ("PV1", 9)):
                    if len(parts) > 9 or any(
                        value and component not in (0, 1, 2, 3, 5, 8)
                        for component, value in enumerate(parts)
                    ):
                        raise ValueError(ERROR_COVERAGE)
                    if (len(parts) > 5 and parts[5] not in ("", "DR", "MD")) or (
                        len(parts) > 8 and parts[8] not in ("", "NPI")
                    ):
                        raise ValueError(ERROR_COVERAGE)
                    saved = len(cells)
                    add(0, 1, FIELD_PROVIDER_ID, NPI_NAMESPACE)
                    add(1, min(4, len(parts)), FIELD_PROVIDER_NAME, mode=HL7_NAME_MODE)
                    providers.append(_record(cells[saved:]))
                    del cells[saved:]
                elif position in HL7_ADDRESS_FIELDS:
                    if len(parts) > 6 or (
                        len(parts) > 5 and parts[5] not in ("", "USA", "US")
                    ):
                        raise ValueError(ERROR_COVERAGE)
                    for component, kind in enumerate(
                        (
                            FIELD_ADDRESS,
                            FIELD_ADDRESS,
                            FIELD_LOCATION,
                            FIELD_CLINICAL,
                            FIELD_ZIP,
                        )
                    ):
                        if component < len(parts):
                            add(
                                component,
                                component + 1,
                                cast(FieldKind, kind),
                                "state" if component == 3 else "",
                            )
                elif position in HL7_PHONE_FIELDS:
                    if (
                        len(parts) > 7
                        or (
                            len(parts) > 1 and parts[1] not in ("", "PRN", "WPN", "NET")
                        )
                        or (
                            len(parts) > 2
                            and parts[2] not in ("", "PH", "FX", "Internet", "CP")
                        )
                    ):
                        raise ValueError(ERROR_COVERAGE)
                    add(0, 1, FIELD_PHONE)
                    if len(parts) > 3:
                        add(3, 4, FIELD_EMAIL)
                    if any(parts[4:]):
                        if (
                            len(parts) != 7
                            or parts[4] not in ("", "1")
                            or len(parts[5]) != 3
                            or len(parts[6]) != 7
                        ):
                            raise ValueError(ERROR_COVERAGE)
                        add(4, 7, FIELD_PHONE, mode=HL7_PHONE_MODE)
                elif position == ("PID", 18):
                    _single(parts)
                    add(0, 1, FIELD_IDENTIFIER, ACCOUNT_NAMESPACE)
                elif position == ("PID", 19):
                    _single(parts)
                    add(0, 1, FIELD_SSN, SSN_NAMESPACE)
                elif position == ("PV1", 3):
                    for component in range(len(parts)):
                        add(
                            component,
                            component + 1,
                            FIELD_IDENTIFIER,
                            f"location:{component}",
                        )
                elif position in (("DG1", 3), ("OBX", 3), ("NK1", 3)):
                    if len(parts) > 3:
                        raise ValueError(ERROR_COVERAGE)
                    add(
                        0,
                        1,
                        FIELD_CLINICAL,
                        "icd"
                        if name == "DG1"
                        else "loinc"
                        if name == "OBX"
                        else "kinship",
                    )
                    if len(parts) > 1:
                        add(
                            1,
                            2,
                            FIELD_CLINICAL
                            if name == "OBX" and segment[2] == "NM"
                            else FIELD_TEXT,
                            LAB_DESCRIPTION_NAMESPACE
                            if name == "OBX" and segment[2] == "NM"
                            else "",
                        )
                    if len(parts) > 2 and parts[2] not in ("I10", "LN", "HL70063"):
                        raise ValueError(ERROR_COVERAGE)
                elif position == ("OBX", 5):
                    _single(parts)
                    if segment[2] not in ("NM", "TX", "ST", "FT"):
                        raise ValueError(ERROR_COVERAGE)
                    add(
                        0,
                        1,
                        FIELD_CLINICAL if segment[2] == "NM" else FIELD_TEXT,
                        "quantity" if segment[2] == "NM" else "",
                    )
                elif position == ("OBX", 6):
                    _single(parts)
                    add(0, 1, FIELD_CLINICAL, "unit")
                elif position == ("NTE", 3):
                    _single(parts)
                    add(0, 1, FIELD_TEXT)
                else:
                    raise ValueError(ERROR_COVERAGE)
    return NativeDocument(records=(_record(cells), *providers))


def _single(parts: list[str]) -> None:
    if len(parts) != 1:
        raise ValueError(ERROR_COVERAGE)


def _record(cells: list[tuple[str, ColumnPolicy, tuple[str, ...]]]) -> NativeRecord:
    return NativeRecord(
        values=tuple(value for value, _, _ in cells),
        policies=tuple(
            policy.model_copy(update={"index": index})
            for index, (_, policy, _) in enumerate(cells)
        ),
        locations=tuple(location for _, _, location in cells),
    )


def _add_cell(
    cells: list[tuple[str, ColumnPolicy, tuple[str, ...]]],
    parts: list[str],
    prefix: tuple[str, ...],
    start: int,
    stop: int,
    kind: FieldKind,
    namespace: str = "",
    mode: str = HL7_VALUE_MODE,
) -> None:
    selected = parts[start:stop]
    if not selected or not any(selected):
        return
    value = ("^" if mode == HL7_NAME_MODE else "").join(selected)
    if mode == HL7_VALUE_MODE and stop - start != 1:
        raise ValueError(ERROR_STRUCTURE)
    cells.append(
        (
            value,
            ColumnPolicy(
                index=len(cells),
                kind=kind,
                namespace=namespace,
                supports_date_bounds=False,
            ),
            (*prefix, str(start), str(stop), mode),
        )
    )
