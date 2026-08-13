import pytest

from app.modules.employee_portal.ticket_attachments import (
    TicketAttachmentValidationError,
    detect_ticket_image_type,
    validate_ticket_attachment_bytes,
)


def test_ticket_attachment_detects_supported_image_signatures() -> None:
    assert detect_ticket_image_type(b"\x89PNG\r\n\x1a\n" + b"data") == "image/png"
    assert detect_ticket_image_type(b"\xff\xd8\xff" + b"data") == "image/jpeg"
    assert detect_ticket_image_type(b"RIFF\x00\x00\x00\x00WEBP" + b"data") == "image/webp"


def test_ticket_attachment_rejects_mime_spoofing() -> None:
    with pytest.raises(TicketAttachmentValidationError) as exc:
        validate_ticket_attachment_bytes(
            filename="fake.png",
            declared_mime_type="image/png",
            data=b"not-an-image",
        )
    assert exc.value.status_code == 415


def test_ticket_attachment_sanitizes_original_filename() -> None:
    result = validate_ticket_attachment_bytes(
        filename="../screenshots/error\x00.png",
        declared_mime_type="image/png",
        data=b"\x89PNG\r\n\x1a\n" + b"safe-payload",
    )
    assert result.original_filename == "error.png"
    assert result.mime_type == "image/png"
    assert result.extension == ".png"
