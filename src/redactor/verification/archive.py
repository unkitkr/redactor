"""Account for every byte of a rebuilt Office ZIP container."""

import struct
import zlib
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from redactor.utils.constants import (
    HASH_CHUNK_BYTES,
    TEXT_ENCODING,
    ZIP_CENTRAL_HEADER_BYTES,
    ZIP_END_RECORD_BYTES,
    ZIP_END_RECORD_FORMAT,
    ZIP_END_SIGNATURE,
    ZIP_FIXED_TIMESTAMP,
    ZIP_LEGACY_ENCODING,
    ZIP_LOCAL_HEADER_FORMAT,
    ZIP_SIGNATURE,
    ZIP_UTF8_FLAG,
)
from redactor.utils.errors import ERROR_COVERAGE


def check_saved_archive(path: Path) -> None:
    """The writer emits contiguous members, then one directory and an empty footer."""
    with ZipFile(path) as archive, path.open("rb") as stream:
        entries = archive.infolist()
        size = path.stat().st_size
        if size < ZIP_END_RECORD_BYTES or archive.comment:
            raise ValueError(ERROR_COVERAGE)
        stream.seek(-ZIP_END_RECORD_BYTES, 2)
        signature, disk, directory_disk, disk_count, count, length, offset, comment = (
            struct.unpack(ZIP_END_RECORD_FORMAT, stream.read(ZIP_END_RECORD_BYTES))
        )
        if (
            signature != ZIP_END_SIGNATURE
            or disk
            or directory_disk
            or disk_count != count
            or count != len(entries)
            or comment
            or offset + length + ZIP_END_RECORD_BYTES != size
        ):
            raise ValueError(ERROR_COVERAGE)
        position = directory_size = 0
        for entry in entries:
            encoding = (
                TEXT_ENCODING
                if entry.flag_bits & ZIP_UTF8_FLAG
                else ZIP_LEGACY_ENCODING
            )
            name = entry.filename.encode(encoding)
            if (
                entry.header_offset != position
                or entry.extra
                or entry.comment
                or entry.date_time != ZIP_FIXED_TIMESTAMP
                or entry.flag_bits & ~ZIP_UTF8_FLAG
                or entry.compress_type != ZIP_DEFLATED
            ):
                raise ValueError(ERROR_COVERAGE)
            stream.seek(position)
            header_size = struct.calcsize(ZIP_LOCAL_HEADER_FORMAT)
            header = stream.read(header_size)
            if len(header) != header_size:
                raise ValueError(ERROR_COVERAGE)
            fields = struct.unpack(ZIP_LOCAL_HEADER_FORMAT, header)
            (
                signature,
                _,
                flags,
                compression,
                _,
                _,
                crc,
                compressed,
                expanded,
                name_size,
                extra_size,
            ) = fields
            if (
                signature != ZIP_SIGNATURE
                or flags != entry.flag_bits
                or compression != entry.compress_type
                or crc != entry.CRC
                or compressed != entry.compress_size
                or expanded != entry.file_size
                or name_size != len(name)
                or extra_size
                or stream.read(name_size) != name
            ):
                raise ValueError(ERROR_COVERAGE)
            _check_compressed_member(stream, compressed)
            position += header_size + name_size + compressed
            directory_size += ZIP_CENTRAL_HEADER_BYTES + name_size
        if position != offset or directory_size != length:
            raise ValueError(ERROR_COVERAGE)


def _check_compressed_member(stream: BinaryIO, size: int) -> None:
    """ZIP readers ignore bytes after a deflate stream; those bytes need coverage."""
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    remaining = size
    try:
        while remaining:
            compressed = stream.read(min(HASH_CHUNK_BYTES, remaining))
            if not compressed:
                raise ValueError(ERROR_COVERAGE)
            remaining -= len(compressed)
            while compressed:
                decoder.decompress(compressed, HASH_CHUNK_BYTES)
                if decoder.unused_data:
                    raise ValueError(ERROR_COVERAGE)
                compressed = decoder.unconsumed_tail
        if not decoder.eof:
            raise ValueError(ERROR_COVERAGE)
    except zlib.error:
        raise ValueError(ERROR_COVERAGE) from None
