from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import hashlib
import re
from typing import Any, Iterator
from uuid import uuid4

from app.core.config import settings

FINANCE_ATTACHMENT_MAX_FILES = 8
FINANCE_SETTLEMENT_ATTACHMENT_MAX_FILES = 50
FINANCE_ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024
FINANCE_ATTACHMENT_CHUNK_BYTES = 64 * 1024
_ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class FinanceAttachmentValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class FinanceAttachmentStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedFinanceAttachment:
    original_filename: str
    mime_type: str
    extension: str
    data: bytes

    @property
    def file_size(self) -> int:
        return len(self.data)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _clean_filename(filename: str | None) -> str:
    raw = Path(filename or "expense-proof").name
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip()
    return (cleaned or "expense-proof")[:255]


def _detect_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_finance_attachment_bytes(*, filename: str | None, declared_mime_type: str | None, data: bytes) -> ValidatedFinanceAttachment:
    if not data:
        raise FinanceAttachmentValidationError("The selected attachment is empty.", status_code=422)
    if len(data) > FINANCE_ATTACHMENT_MAX_BYTES:
        raise FinanceAttachmentValidationError("Each expense attachment must be 15 MB or smaller.", status_code=413)

    declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()
    if declared not in _ALLOWED_TYPES:
        raise FinanceAttachmentValidationError("Only PDF, JPG, PNG, and WebP files can be attached.", status_code=415)

    detected = _detect_type(data)
    if detected is None or detected != declared:
        raise FinanceAttachmentValidationError("The uploaded file content does not match a supported file type.", status_code=415)

    return ValidatedFinanceAttachment(
        original_filename=_clean_filename(filename),
        mime_type=detected,
        extension=_ALLOWED_TYPES[detected],
        data=data,
    )


def _client() -> Any:
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )


def _ensure_bucket(client: Any) -> None:
    from minio.error import S3Error

    try:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
    except S3Error as exc:
        if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
            raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc
    except Exception as exc:
        raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc


def store_finance_attachment(claim_id: int, attachment: ValidatedFinanceAttachment, *, namespace: str = "claims") -> str:
    client = _client()
    _ensure_bucket(client)
    safe_namespace = re.sub(r"[^a-zA-Z0-9_-]", "", namespace) or "claims"
    storage_key = f"finance-expenses/{safe_namespace}/{claim_id}/{uuid4().hex}{attachment.extension}"
    try:
        client.put_object(
            settings.minio_bucket,
            storage_key,
            BytesIO(attachment.data),
            attachment.file_size,
            content_type=attachment.mime_type,
        )
    except Exception as exc:
        raise FinanceAttachmentStorageError("Expense proof could not be stored.") from exc
    return storage_key


def delete_finance_attachment_object(storage_key: str) -> None:
    try:
        _client().remove_object(settings.minio_bucket, storage_key)
    except Exception:
        return


def stream_finance_attachment(storage_key: str) -> Iterator[bytes]:
    from minio.error import S3Error

    client = _client()
    try:
        response = client.get_object(settings.minio_bucket, storage_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise FileNotFoundError(storage_key) from exc
        raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc
    except Exception as exc:
        raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc

    def iterator() -> Iterator[bytes]:
        try:
            for chunk in response.stream(FINANCE_ATTACHMENT_CHUNK_BYTES):
                if chunk:
                    yield chunk
        finally:
            response.close()
            response.release_conn()

    return iterator()


def read_finance_attachment_bytes(storage_key: str) -> bytes:
    """Read a stored Finance proof as bytes for controlled ZIP/PDF report generation."""
    from minio.error import S3Error

    client = _client()
    try:
        response = client.get_object(settings.minio_bucket, storage_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise FileNotFoundError(storage_key) from exc
        raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc
    except Exception as exc:
        raise FinanceAttachmentStorageError("Expense proof storage is unavailable.") from exc
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
