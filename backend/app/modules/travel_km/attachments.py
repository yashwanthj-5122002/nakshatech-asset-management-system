from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
import base64
import hashlib
import re
from typing import Any, Iterator
from uuid import uuid4

from app.core.config import settings

TRAVEL_PHOTO_MAX_BYTES = 15 * 1024 * 1024
TRAVEL_PHOTO_CHUNK_BYTES = 64 * 1024
_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class TravelPhotoValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class TravelPhotoStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedTravelPhoto:
    original_filename: str
    mime_type: str
    extension: str
    data: bytes
    exif_latitude: float | None = None
    exif_longitude: float | None = None
    exif_captured_at: datetime | None = None

    @property
    def file_size(self) -> int:
        return len(self.data)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _clean_filename(filename: str | None) -> str:
    raw = Path(filename or "odometer-photo").name
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip()
    return (cleaned or "odometer-photo")[:255]


def _detect_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _rational_to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        try:
            return float(value[0]) / float(value[1])
        except Exception:
            return 0.0


def _gps_to_decimal(values: Any, ref: str | bytes | None) -> float | None:
    try:
        degrees, minutes, seconds = values
        decimal = _rational_to_float(degrees) + _rational_to_float(minutes) / 60.0 + _rational_to_float(seconds) / 3600.0
        ref_text = ref.decode(errors="ignore") if isinstance(ref, bytes) else str(ref or "")
        if ref_text.upper() in {"S", "W"}:
            decimal *= -1.0
        return float(decimal)
    except Exception:
        return None


def _extract_exif(data: bytes) -> tuple[float | None, float | None, datetime | None]:
    try:
        from PIL import ExifTags, Image

        with Image.open(BytesIO(data)) as image:
            exif = image.getexif()
            if not exif:
                return None, None, None
            captured = None
            for key in (36867, 36868, 306):
                raw = exif.get(key)
                if raw:
                    try:
                        captured = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
                        break
                    except ValueError:
                        pass
            gps = None
            try:
                gps_ifd = getattr(getattr(ExifTags, "IFD", None), "GPSInfo", 34853)
                gps = dict(exif.get_ifd(gps_ifd))
            except Exception:
                raw = exif.get(34853)
                if isinstance(raw, dict):
                    gps = dict(raw)
            if not gps:
                return None, None, captured
            lat = _gps_to_decimal(gps.get(2), gps.get(1))
            lon = _gps_to_decimal(gps.get(4), gps.get(3))
            return lat, lon, captured
    except Exception:
        return None, None, None


def validate_travel_photo(*, filename: str | None, declared_mime_type: str | None, data: bytes) -> ValidatedTravelPhoto:
    if not data:
        raise TravelPhotoValidationError("The selected odometer photo is empty.", status_code=422)
    if len(data) > TRAVEL_PHOTO_MAX_BYTES:
        raise TravelPhotoValidationError("Each odometer photo must be 15 MB or smaller.", status_code=413)
    declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()
    if declared not in _ALLOWED_TYPES:
        raise TravelPhotoValidationError("Only JPG, PNG, and WebP odometer photos are accepted.", status_code=415)
    detected = _detect_type(data)
    if detected is None or detected != declared:
        raise TravelPhotoValidationError("The uploaded content does not match a supported image type.", status_code=415)
    lat, lon, captured = _extract_exif(data)
    return ValidatedTravelPhoto(
        original_filename=_clean_filename(filename),
        mime_type=detected,
        extension=_ALLOWED_TYPES[detected],
        data=data,
        exif_latitude=lat,
        exif_longitude=lon,
        exif_captured_at=captured,
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
            raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc
    except Exception as exc:
        raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc


def store_travel_photo(claim_id: int, phase: str, photo: ValidatedTravelPhoto) -> str:
    client = _client()
    _ensure_bucket(client)
    storage_key = f"travel-km/{claim_id}/{phase}/{uuid4().hex}{photo.extension}"
    try:
        client.put_object(
            settings.minio_bucket,
            storage_key,
            BytesIO(photo.data),
            photo.file_size,
            content_type=photo.mime_type,
        )
    except Exception as exc:
        raise TravelPhotoStorageError("Travel evidence could not be stored.") from exc
    return storage_key


def delete_travel_photo(storage_key: str) -> None:
    try:
        _client().remove_object(settings.minio_bucket, storage_key)
    except Exception:
        return


def read_travel_photo(storage_key: str) -> bytes:
    from minio.error import S3Error
    client = _client()
    try:
        response = client.get_object(settings.minio_bucket, storage_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise FileNotFoundError(storage_key) from exc
        raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc
    except Exception as exc:
        raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def stream_travel_photo(storage_key: str) -> Iterator[bytes]:
    from minio.error import S3Error
    client = _client()
    try:
        response = client.get_object(settings.minio_bucket, storage_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise FileNotFoundError(storage_key) from exc
        raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc
    except Exception as exc:
        raise TravelPhotoStorageError("Travel evidence storage is unavailable.") from exc

    def iterator() -> Iterator[bytes]:
        try:
            for chunk in response.stream(TRAVEL_PHOTO_CHUNK_BYTES):
                if chunk:
                    yield chunk
        finally:
            response.close()
            response.release_conn()
    return iterator()


def preview_data_url(storage_key: str) -> str:
    """Create an authenticated, compact preview so the UI can show evidence without exposing MinIO."""
    data = read_travel_photo(storage_key)
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as image:
            image = image.convert("RGB")
            image.thumbnail((1280, 1280))
            out = BytesIO()
            image.save(out, format="JPEG", quality=82, optimize=True)
            payload = out.getvalue()
    except Exception:
        payload = data
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")
