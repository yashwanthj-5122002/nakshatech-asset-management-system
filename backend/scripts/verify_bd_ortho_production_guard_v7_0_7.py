from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


def main() -> None:
    # Reproduce the exact V7.0.6 regression condition: production mode,
    # test-user seeding enabled, and a development-strength JWT secret.
    settings.environment = "production"
    settings.seed_operations_test_users_enabled = True
    settings.jwt_secret = "short-local-dev-secret"

    try:
        settings.validate_production_settings()
    except RuntimeError as exc:
        message = str(exc)
        if "SEED_OPERATIONS_TEST_USERS_ENABLED" not in message:
            raise SystemExit(
                "Production test-user guard was masked by another validation error: " + message
            )
    else:
        raise SystemExit("Production unexpectedly allowed BD/Ortho test-user seeding")

    print("V707_PRODUCTION_SEED_GUARD_OK")


if __name__ == "__main__":
    main()
