"""Generic Units of Measure (UOM) for shared production tracking (V8.1).

Deliberately department-neutral: the LiDAR Daily Activity report happens to use
kilometres, but nothing in the ERP may hard-code KM. Work packages store the
planned quantity together with a freely chosen unit; daily production entries
inherit the package unit, so a single package is always internally consistent.

Conversion is performed ONLY between units of the same measurement type
(1000 m = 1 km; 1 000 000 sq.m = 1 sq.km; 1 hectare = 10 000 sq.m). Count kinds
(files, images, tiles, ...) are distinct measurement types on purpose so that
``files + km`` or ``tiles + files`` can never silently aggregate.

Unknown / legacy unit strings (for example historical ``ha`` is mapped, but any
other free-text value) are treated as opaque: they keep working exactly as
before, progress is still computed inside the package (daily entries always use
the package unit), and the value is simply never converted or cross-summed.
"""

from __future__ import annotations

from decimal import Decimal

MEASUREMENT_DISTANCE = "distance"  # base: metre
MEASUREMENT_AREA = "area"  # base: square metre
MEASUREMENT_TIME = "time"  # base: hour

# unit -> (measurement_type, factor_to_base_unit)
UNIT_CATALOG: dict[str, tuple[str, Decimal]] = {
    # distance (base = m)
    "mm": (MEASUREMENT_DISTANCE, Decimal("0.001")),
    "cm": (MEASUREMENT_DISTANCE, Decimal("0.01")),
    "m": (MEASUREMENT_DISTANCE, Decimal("1")),
    "km": (MEASUREMENT_DISTANCE, Decimal("1000")),
    # area (base = sq.m)
    "sq.m": (MEASUREMENT_AREA, Decimal("1")),
    "sq.km": (MEASUREMENT_AREA, Decimal("1000000")),
    "hectare": (MEASUREMENT_AREA, Decimal("10000")),
    "ha": (MEASUREMENT_AREA, Decimal("10000")),
    "acre": (MEASUREMENT_AREA, Decimal("4046.8564224")),
    # count outputs — each kind is its own measurement type (never cross-summed)
    "file": ("count:file", Decimal("1")),
    "files": ("count:file", Decimal("1")),
    "image": ("count:image", Decimal("1")),
    "images": ("count:image", Decimal("1")),
    "tile": ("count:tile", Decimal("1")),
    "tiles": ("count:tile", Decimal("1")),
    "drawing": ("count:drawing", Decimal("1")),
    "drawings": ("count:drawing", Decimal("1")),
    "feature": ("count:feature", Decimal("1")),
    "features": ("count:feature", Decimal("1")),
    "point": ("count:point", Decimal("1")),
    "points": ("count:point", Decimal("1")),
    "location": ("count:location", Decimal("1")),
    "locations": ("count:location", Decimal("1")),
    # time (base = hour)
    "minute": (MEASUREMENT_TIME, Decimal("1") / Decimal("60")),
    "min": (MEASUREMENT_TIME, Decimal("1") / Decimal("60")),
    "hour": (MEASUREMENT_TIME, Decimal("1")),
    "hours": (MEASUREMENT_TIME, Decimal("1")),
    "day": (MEASUREMENT_TIME, Decimal("24")),
    "days": (MEASUREMENT_TIME, Decimal("24")),
}


def normalize_unit(unit: str | None) -> str | None:
    """Canonical catalog key for a unit string, or None when unknown."""
    if not unit:
        return None
    token = str(unit).strip().lower().replace(" ", "")
    return token if token in UNIT_CATALOG else None


def measurement_type(unit: str | None) -> str | None:
    """Measurement type of a unit, or ``opaque:<unit>`` for unknown units.

    Opaque units form their own singleton type so they are never converted and
    never mixed with anything else — historical data keeps loading unchanged.
    """
    key = normalize_unit(unit)
    if key is not None:
        return UNIT_CATALOG[key][0]
    raw = (str(unit).strip().lower() if unit else "")
    return f"opaque:{raw}" if raw else None


def units_compatible(first: str | None, second: str | None) -> bool:
    return measurement_type(first) is not None and measurement_type(first) == measurement_type(second)


def normalize_quantity(quantity: Decimal, unit: str | None) -> tuple[Decimal, str]:
    """Return (quantity converted to the base unit, measurement type)."""
    qtype = measurement_type(unit)
    key = normalize_unit(unit)
    if key is None:
        return quantity, qtype or "opaque:unknown"
    factor = UNIT_CATALOG[key][1]
    return quantity * factor, qtype  # type: ignore[return-value]


def convert_quantity(quantity: Decimal, from_unit: str | None, to_unit: str | None) -> Decimal:
    """Convert a quantity between compatible units. Raises ValueError otherwise."""
    if not units_compatible(from_unit, to_unit):
        raise ValueError(f"Cannot convert between incompatible units: {from_unit!r} and {to_unit!r}")
    from_key = normalize_unit(from_unit)
    to_key = normalize_unit(to_unit)
    if from_key is None or to_key is None:
        return quantity  # opaque-but-equal units: identity
    from_factor = UNIT_CATALOG[from_key][1]
    to_factor = UNIT_CATALOG[to_key][1]
    return quantity * from_factor / to_factor


def known_units() -> list[str]:
    """Stable, de-duplicated unit list for pickers (catalog order preserved)."""
    seen: list[str] = []
    for unit in UNIT_CATALOG:
        base = UNIT_CATALOG[unit][0]
        if base in {MEASUREMENT_DISTANCE, MEASUREMENT_AREA, MEASUREMENT_TIME} or unit not in {"hours", "days", "min"}:
            if unit in {"ha", "min", "hours", "days"}:
                continue  # keep aliases out of the picker; they still normalize
            seen.append(unit)
    return seen
