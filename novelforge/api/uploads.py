"""Shared limits and bounded readers for user-supplied material files."""

from __future__ import annotations

from fastapi import UploadFile


MEBIBYTE = 1024 * 1024
MAX_MATERIAL_FILE_BYTES = 32 * MEBIBYTE
MAX_MATERIAL_BATCH_BYTES = 128 * MEBIBYTE
MAX_MATERIAL_BATCH_FILES = 20
UPLOAD_READ_CHUNK_BYTES = MEBIBYTE


async def read_material_upload(file: UploadFile) -> bytes:
    """Read one upload without buffering data beyond the public size limit."""

    content = bytearray()
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_MATERIAL_FILE_BYTES:
            filename = file.filename or "资料文件"
            raise ValueError(f"{filename} 超过 32MB 单文件限制。")
    return bytes(content)
