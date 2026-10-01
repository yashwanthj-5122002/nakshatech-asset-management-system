"""Bounded reads for multipart uploads.

``UploadFile.read()`` with no argument loads the whole part into memory. An
unauthenticated or lightly authenticated endpoint that does that can be made to
allocate hundreds of megabytes per request simply by posting a large body, and
nginx only rejects bodies above ``client_max_body_size``. Every upload handler
therefore reads through this helper, which enforces the limit while streaming
so the memory actually used is one chunk plus the accumulated result up to the
cap - never the full incoming part.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

__all__ = ["MAX_IMPORT_BYTES", "MAX_ATTACHMENT_BYTES", "MAX_PHOTO_BYTES", "read_upload_bytes"]

CHUNK_SIZE = 1024 * 1024

# Excel/CSV imports (workbook parsing is the expensive part).
MAX_IMPORT_BYTES = 25 * 1024 * 1024
# Document and image attachments (tickets, claims, receipts, evidence).
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
# Photos taken on a phone.
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def _megabytes(max_bytes: int) -> str:
    value = max_bytes / (1024 * 1024)
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


async def read_upload_bytes(
    file: UploadFile,
    *,
    max_bytes: int,
    label: str = "File",
    status_code: int = 400,
    detail: str | None = None,
) -> bytes:
    """Read one uploaded part, refusing anything above ``max_bytes``.

    ``detail`` lets a handler keep its established error message and
    ``status_code`` its established rejection status; both branches below raise
    the identical response so the limit behaves the same whether the size was
    known up front or only became clear mid-stream.
    """
    message = detail or f"{label} is larger than {_megabytes(max_bytes)} MB"

    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise HTTPException(status_code=status_code, detail=message)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status_code, detail=message)
        chunks.append(chunk)
    return b"".join(chunks)
