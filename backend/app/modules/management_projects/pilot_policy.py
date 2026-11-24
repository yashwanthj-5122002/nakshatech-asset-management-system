
from decimal import Decimal, InvalidOperation

PROJECT_TYPES = {"regular", "pilot"}
PILOT_PAYMENT_TYPES = {"free", "paid"}


def validate_project_classification(
    *,
    project_type: str = "regular",
    pilot_payment_type: str | None = None,
    project_value=None,
) -> dict:
    """
    Shared validation for Management-origin projects.

    This function does not create projects, approve
    projects, raise invoices or modify existing data.
    """

    kind = (project_type or "regular").strip().lower()

    if kind not in PROJECT_TYPES:
        raise ValueError("Invalid project type")

    if kind == "regular":
        if pilot_payment_type not in (None, ""):
            raise ValueError(
                "Regular projects cannot have "
                "a pilot payment type"
            )

        return {
            "project_type": "regular",
            "pilot_payment_type": None,
        }

    payment = (
        pilot_payment_type or ""
    ).strip().lower()

    if payment not in PILOT_PAYMENT_TYPES:
        raise ValueError(
            "Select Free Pilot or Paid Pilot"
        )

    if project_value is not None:
        try:
            amount = Decimal(str(project_value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid project value")

        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid project value")

        if payment == "free" and amount != 0:
            raise ValueError(
                "Free pilots must have zero "
                "customer contract value"
            )

    return {
        "project_type": "pilot",
        "pilot_payment_type": payment,
    }


def is_pilot_project(project) -> bool:
    return (
        getattr(project, "project_type", "regular")
        == "pilot"
    )
