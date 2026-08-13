import pytest
from pydantic import ValidationError

from app.modules.employee_portal.schemas import TicketCreateRequest


def payload(description: str) -> dict:
    return {
        "department": "it",
        "reporting_manager_email": "manager@nakshatech.com",
        "title": "RAM issue",
        "description": description,
    }


def test_ticket_description_requires_ten_characters() -> None:
    with pytest.raises(ValidationError):
        TicketCreateRequest(**payload("RAM issue"))


def test_ticket_description_does_not_count_outer_whitespace() -> None:
    with pytest.raises(ValidationError):
        TicketCreateRequest(**payload("     RAM     "))


def test_ticket_description_accepts_ten_meaningful_characters() -> None:
    request = TicketCreateRequest(**payload("RAM issue!!"))
    assert request.description == "RAM issue!!"
