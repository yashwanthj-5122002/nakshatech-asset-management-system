from decimal import Decimal

from app.core.departments import SUPPORTED_DEPARTMENTS
from app.uat_2026 import (
    ARCHETYPES,
    DEFAULT_CLIENTS,
    DEFAULT_PROJECTS,
    DEFAULT_SEED,
    TARGET_REALIZED_REVENUE_INR,
    build_plan,
)


def test_default_plan_is_deterministic_and_full_year():
    first = build_plan()
    second = build_plan()
    assert first == second
    assert len(first) == DEFAULT_PROJECTS
    assert {row.client_ordinal for row in first} == set(range(1, DEFAULT_CLIENTS + 1))
    assert {row.department_code for row in first} == set(SUPPORTED_DEPARTMENTS)
    assert {row.award_date.month for row in first} == set(range(1, 13))
    assert {row.currency for row in first} == {"INR", "USD", "GBP", "AED"}


def test_default_plan_hits_exact_realized_revenue_target():
    rows = build_plan()
    realized = sum(
        (row.gross_inr for row in rows if row.archetype == "closed"),
        Decimal("0"),
    )
    assert realized == TARGET_REALIZED_REVENUE_INR


def test_default_plan_covers_every_lifecycle_archetype():
    rows = build_plan()
    found = {row.archetype for row in rows}
    assert found == set(ARCHETYPES)
    assert sum(1 for row in rows if row.archetype == "closed") == 80


def test_custom_seed_is_stable_but_changes_distribution_values():
    a = build_plan(seed=DEFAULT_SEED + 1)
    b = build_plan(seed=DEFAULT_SEED + 1)
    default = build_plan()
    assert a == b
    assert [row.gross_inr for row in a] != [row.gross_inr for row in default]
