"""SEC-14: multipart uploads are read through a size-bounded helper.

``await file.read()`` materialises the whole part before any check runs, so an
oversized (or simply large, up to nginx's ``client_max_body_size``) body costs
memory proportional to the upload instead of to the cap. Every handler now
calls :func:`app.core.uploads.read_upload_bytes`, which stops reading the
moment the limit is passed.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.core.uploads import MAX_IMPORT_BYTES, read_upload_bytes


def _upload(data: bytes, *, size: int | None = None) -> UploadFile:
    if size is None:
        return UploadFile(file=io.BytesIO(data), filename="upload.xlsx")
    try:
        return UploadFile(file=io.BytesIO(data), filename="upload.xlsx", size=size)
    except TypeError:  # starlette build without UploadFile.size
        return UploadFile(file=io.BytesIO(data), filename="upload.xlsx")


def _read(upload: UploadFile, **kwargs) -> bytes:
    return asyncio.run(read_upload_bytes(upload, **kwargs))


def test_read_upload_bytes_returns_payload_within_limit():
    payload = b"naksha" * 1024
    assert _read(_upload(payload), max_bytes=1024 * 1024) == payload


def test_read_upload_bytes_rejects_streamed_oversize():
    with pytest.raises(HTTPException) as exc:
        _read(_upload(b"a" * (2 * 1024 * 1024)), max_bytes=1024 * 1024)
    assert exc.value.status_code == 400
    assert "1 MB" in exc.value.detail


def test_read_upload_bytes_rejects_declared_oversize_without_reading_body():
    upload = _upload(b"", size=MAX_IMPORT_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        _read(upload, max_bytes=MAX_IMPORT_BYTES)
    assert exc.value.status_code == 400
    assert "25 MB" in exc.value.detail


def test_read_upload_bytes_keeps_handler_status_and_detail():
    with pytest.raises(HTTPException) as exc:
        _read(_upload(b"a" * 100), max_bytes=10, status_code=413, detail="Workbook is too big")
    assert exc.value.status_code == 413
    assert exc.value.detail == "Workbook is too big"


def test_import_endpoint_refuses_oversized_workbook():
    """End to end: the IT handover import caps the body at 25 MB."""
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.main import app
    from app.models.entities import User

    with SessionLocal() as db:
        user = User(
            email="upload.limit@nakshatech.com",
            full_name="Upload Limit",
            password_hash="pytest-only-password-hash",
            role="admin",
            branch="Head Office",
            is_active=True,
            token_version=0,
        )
        db.add(user)
        db.commit()
        token = create_access_token(user.email, "admin", token_version=int(user.token_version or 0))

    client = TestClient(app)
    body = b"x" * (MAX_IMPORT_BYTES + 1024)
    response = client.post(
        "/api/it-activity/imports/handover.xlsx",
        params={"device_category": "laptop"},
        files={"file": ("big.xlsx", body, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400, response.text
    assert "25 MB" in response.json()["detail"]
