from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _limiter():
    from app.core.ratelimit import RateLimiter

    return RateLimiter(window_seconds=60.0, max_hits=3)


def test_limiter_allows_up_to_max_then_blocks():
    limiter = _limiter()
    for attempt in range(3):
        allowed, _ = limiter.hit("key")
        assert allowed, f"attempt {attempt + 1} should be allowed"
    allowed, retry_after = limiter.hit("key")
    assert allowed is False
    assert retry_after >= 1


def test_limiter_window_expires():
    import time

    from app.core.ratelimit import RateLimiter

    limiter = RateLimiter(window_seconds=0.05, max_hits=1)
    assert limiter.hit("key")[0] is True
    assert limiter.hit("key")[0] is False
    time.sleep(0.1)
    assert limiter.hit("key")[0] is True


def test_reset_clears_window():
    limiter = _limiter()
    for _ in range(3):
        limiter.hit("key")
    assert limiter.hit("key")[0] is False
    limiter.reset("key")
    assert limiter.hit("key")[0] is True


def test_client_ip_ignores_header_from_untrusted_peer():
    from app.core.ratelimit import RateLimiter

    limiter = RateLimiter(window_seconds=60.0, max_hits=1, trusted_proxy_cidrs="")
    scope = {
        "client": ("203.0.113.9", 1234),
        "headers": [(b"x-real-ip", b"1.2.3.4")],
    }
    assert limiter.client_ip(scope) == "203.0.113.9"


def test_client_ip_honours_header_from_trusted_proxy():
    from app.core.ratelimit import RateLimiter

    limiter = RateLimiter(window_seconds=60.0, max_hits=1, trusted_proxy_cidrs="10.0.0.0/8")
    scope = {
        "client": ("10.1.2.3", 1234),
        "headers": [(b"x-real-ip", b"198.51.100.7")],
    }
    assert limiter.client_ip(scope) == "198.51.100.7"


def test_client_ip_rejects_malformed_header():
    from app.core.ratelimit import RateLimiter

    limiter = RateLimiter(window_seconds=60.0, max_hits=1, trusted_proxy_cidrs="10.0.0.0/8")
    scope = {
        "client": ("10.1.2.3", 1234),
        "headers": [(b"x-real-ip", b"not-an-ip")],
    }
    assert limiter.client_ip(scope) == "10.1.2.3"


@pytest.fixture()
def rate_limited_client():
    """Real application client with the auth limiter enabled and a low budget."""
    from app.core.config import settings
    from app.main import app
    import app.main as main_module

    previous = settings.rate_limit_enabled
    previous_failures = settings.rate_limit_auth_failures_per_minute
    previous_max_hits = main_module._auth_failure_limiter.max_hits
    main_module._auth_volume_limiter._hits.clear()
    main_module._auth_failure_limiter._hits.clear()
    # The limiter captures max_hits when it is built, so the instance has to be
    # adjusted too - reassigning the setting alone would not tighten the budget.
    settings.rate_limit_auth_failures_per_minute = 3
    main_module._auth_failure_limiter.max_hits = 3
    settings.rate_limit_enabled = True
    try:
        yield TestClient(app, base_url="http://localhost")
    finally:
        settings.rate_limit_enabled = previous
        settings.rate_limit_auth_failures_per_minute = previous_failures
        main_module._auth_failure_limiter.max_hits = previous_max_hits
        main_module._auth_volume_limiter._hits.clear()
        main_module._auth_failure_limiter._hits.clear()


def test_repeated_bad_logins_return_429(rate_limited_client):
    """Credential stuffing is cut off after the configured failure budget."""
    payload = {"email": "nobody@nakshatech.com", "password": "wrong-password-1"}

    statuses = []
    for _ in range(5):
        response = rate_limited_client.post("/api/auth/login", json=payload)
        statuses.append(response.status_code)

    # The first three attempts are rejected normally; the rest are throttled.
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]

    throttled = rate_limited_client.post("/api/auth/login", json=payload)
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) >= 1


def test_unprotected_endpoint_is_not_throttled(rate_limited_client):
    """Only the credential surfaces are rate limited."""
    for _ in range(8):
        response = rate_limited_client.post(
            "/api/auth/login", json={"email": "a@b.com", "password": "x"}
        )
        if response.status_code == 429:
            break
    # /auth/logout is not a credential-guessing surface.
    assert rate_limited_client.post("/api/auth/logout").status_code != 429


def test_non_post_requests_bypass_limiter(rate_limited_client):
    response = rate_limited_client.get("/api/auth/me")
    assert response.status_code in {401, 403, 404}
    assert response.status_code != 429
