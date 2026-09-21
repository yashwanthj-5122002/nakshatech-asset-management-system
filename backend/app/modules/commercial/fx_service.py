"""Exchange-rate retrieval for project commercial amounts.

* Runs on the backend only; no provider URL/credential is ever exposed to the browser.
* Provider details come from configuration (``FX_PROVIDER_ORDER`` ...). Every quote records
  the provider that produced it, so the data model is not coupled to one vendor.
* A quote is either a real provider rate or an explicit failure. There is no silent default,
  no fake fallback and no substitution of an unrelated date's rate. The only synthetic rate
  is the identity ``X -> X = 1`` (INR -> INR for the base currency).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Protocol

import httpx

from app.core.config import settings
from app.modules.commercial.currencies import BASE_CURRENCY, normalize_currency

logger = logging.getLogger(__name__)

RATE_QUANT = Decimal("0.00000001")
MONEY_QUANT = Decimal("0.01")

FX_MODE_AUTO = "AUTO"
FX_MODE_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
FX_MODE_CONTRACT_RATE = "CONTRACT_RATE"
FX_MODE_BANK_REALIZATION_RATE = "BANK_REALIZATION_RATE"
FX_MODE_BASE_CURRENCY = "BASE_CURRENCY"
FX_MODE_OTHER = "OTHER"
FX_MODES = {
    FX_MODE_AUTO, FX_MODE_MANUAL_OVERRIDE, FX_MODE_CONTRACT_RATE,
    FX_MODE_BANK_REALIZATION_RATE, FX_MODE_BASE_CURRENCY, FX_MODE_OTHER,
}
# Modes a person chooses when they replace the automatic reference rate; each needs a documented reason.
OVERRIDE_MODES = {FX_MODE_MANUAL_OVERRIDE, FX_MODE_CONTRACT_RATE, FX_MODE_BANK_REALIZATION_RATE, FX_MODE_OTHER}


class FxUnavailableError(RuntimeError):
    """No provider could supply a rate. The caller must offer Retry / manual entry, never a made-up value."""

    code = "FX_UNAVAILABLE"

    def __init__(self, message: str = "Automatic exchange rate unavailable.", *, attempts: list[str] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


class ProviderUnsupported(Exception):
    """The provider cannot serve this pair/date (permanent for this request; try the next provider)."""


class ProviderTransientError(Exception):
    """Timeout / connection / 5xx: worth retrying."""


@dataclass(frozen=True)
class FxQuote:
    from_currency: str
    to_currency: str
    rate: Decimal
    rate_date: date
    timestamp: datetime | None
    source: str
    mode: str = FX_MODE_AUTO


def quantize_rate(value: Decimal | float | int | str) -> Decimal:
    try:
        rate = Decimal(str(value)).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid exchange rate") from exc
    if rate <= 0:
        raise ValueError("Exchange rate must be greater than zero")
    return rate


def money(value: Decimal | float | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def convert_to_inr(amount: Decimal | float | int | str, rate: Decimal | float | int | str) -> Decimal:
    """Original-currency amount -> INR at ``rate`` (INR per 1 unit), rounded half-up to paise."""
    return (Decimal(str(amount)) * Decimal(str(rate))).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


class FxProvider(Protocol):
    name: str
    supports_historical: bool

    def get_rate(self, from_currency: str, to_currency: str, on_date: date | None, client: httpx.Client) -> FxQuote: ...


def _load_json(response: httpx.Response) -> dict:
    return json.loads(response.text, parse_float=Decimal)


def _raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.status_code in (400, 404, 422):
        raise ProviderUnsupported(f"{provider}: pair/date not supported (HTTP {response.status_code})")
    if response.status_code == 429 or response.status_code >= 500:
        raise ProviderTransientError(f"{provider}: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ProviderUnsupported(f"{provider}: HTTP {response.status_code}")


class FrankfurterProvider:
    """European Central Bank reference rates (dated). Covers the ECB currency set, not every ISO code."""

    name = "frankfurter"
    supports_historical = True

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.fx_frankfurter_base_url).rstrip("/")

    def get_rate(self, from_currency: str, to_currency: str, on_date: date | None, client: httpx.Client) -> FxQuote:
        path = on_date.isoformat() if on_date else "latest"
        try:
            response = client.get(f"{self.base_url}/{path}", params={"base": from_currency, "symbols": to_currency})
        except httpx.HTTPError as exc:
            raise ProviderTransientError(f"frankfurter: {type(exc).__name__}") from exc
        _raise_for_status(response, "frankfurter")
        try:
            payload = _load_json(response)
            rate = payload["rates"][to_currency]
            rate_date = date.fromisoformat(payload["date"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ProviderUnsupported("frankfurter: unexpected response shape") from exc
        return FxQuote(
            from_currency, to_currency, quantize_rate(rate), rate_date, None,
            "Frankfurter (ECB reference rate)", FX_MODE_AUTO,
        )


class OpenErApiProvider:
    """open.er-api.com: broad currency coverage, latest reference rate only (no history)."""

    name = "open_er_api"
    supports_historical = False

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.fx_open_er_api_base_url).rstrip("/")

    def get_rate(self, from_currency: str, to_currency: str, on_date: date | None, client: httpx.Client) -> FxQuote:
        if on_date is not None and on_date < datetime.now(timezone.utc).date():
            raise ProviderUnsupported("open_er_api: historical rates are not supported")
        try:
            response = client.get(f"{self.base_url}/latest/{from_currency}")
        except httpx.HTTPError as exc:
            raise ProviderTransientError(f"open_er_api: {type(exc).__name__}") from exc
        _raise_for_status(response, "open_er_api")
        try:
            payload = _load_json(response)
            if payload.get("result") != "success":
                raise ProviderUnsupported("open_er_api: provider reported failure")
            rate = payload["rates"][to_currency]
            updated = datetime.fromtimestamp(int(payload["time_last_update_unix"]), tz=timezone.utc)
        except (KeyError, ValueError, TypeError) as exc:
            raise ProviderUnsupported("open_er_api: unexpected response shape") from exc
        return FxQuote(
            from_currency, to_currency, quantize_rate(rate), updated.date(), updated.replace(tzinfo=None),
            "open.er-api.com (latest reference rate)", FX_MODE_AUTO,
        )


PROVIDER_REGISTRY: dict[str, Callable[[], FxProvider]] = {
    "frankfurter": FrankfurterProvider,
    "open_er_api": OpenErApiProvider,
}


def configured_providers() -> list[FxProvider]:
    providers: list[FxProvider] = []
    for name in [item.strip().lower() for item in settings.fx_provider_order.split(",") if item.strip()]:
        factory = PROVIDER_REGISTRY.get(name)
        if factory is None:
            logger.warning("Ignoring unknown FX provider %r", name)
            continue
        providers.append(factory())
    return providers


class FxRateService:
    def __init__(
        self,
        providers: list[FxProvider] | None = None,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        cache_ttl_seconds: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
        client_factory: Callable[[float], httpx.Client] | None = None,
    ) -> None:
        self._providers = providers
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_ttl = cache_ttl_seconds
        self._sleep = sleep
        self._client_factory = client_factory or (lambda t: httpx.Client(timeout=t, headers={"User-Agent": "Nakshatech-ERP-FX/1.0"}))
        self._cache: dict[tuple[str, str, str], tuple[float, FxQuote]] = {}
        self._lock = threading.Lock()

    @property
    def providers(self) -> list[FxProvider]:
        return self._providers if self._providers is not None else configured_providers()

    def _cached(self, key: tuple[str, str, str]) -> FxQuote | None:
        ttl = self._cache_ttl if self._cache_ttl is not None else settings.fx_cache_ttl_seconds
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < (86_400 if key[2] != "latest" else ttl):
                return hit[1]
        return None

    def _store(self, key: tuple[str, str, str], quote: FxQuote) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), quote)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def get_rate(self, from_currency: str, to_currency: str = BASE_CURRENCY, on_date: date | None = None) -> FxQuote:
        source = normalize_currency(from_currency)
        target = normalize_currency(to_currency)
        today = datetime.now(timezone.utc).date()
        if source == target:
            return FxQuote(source, target, Decimal("1.00000000"), on_date or today, None, "BASE_CURRENCY" if source == BASE_CURRENCY else "IDENTITY", FX_MODE_BASE_CURRENCY)
        historical = on_date is not None and on_date < today
        key = (source, target, on_date.isoformat() if historical and on_date else "latest")
        cached = self._cached(key)
        if cached is not None:
            return cached

        timeout = self._timeout if self._timeout is not None else settings.fx_timeout_seconds
        retries = self._max_retries if self._max_retries is not None else settings.fx_max_retries
        attempts: list[str] = []
        providers = self.providers
        if not providers:
            raise FxUnavailableError(attempts=["no FX provider configured"])
        with self._client_factory(timeout) as client:
            for provider in providers:
                if historical and not provider.supports_historical:
                    attempts.append(f"{provider.name}: no historical support")
                    continue
                for attempt in range(retries + 1):
                    try:
                        quote = provider.get_rate(source, target, on_date if historical else None, client)
                    except ProviderUnsupported as exc:
                        attempts.append(str(exc))
                        break
                    except ProviderTransientError as exc:
                        attempts.append(f"{exc} (attempt {attempt + 1})")
                        if attempt < retries:
                            self._sleep(min(0.4 * (attempt + 1), 2.0))
                        continue
                    except (ValueError, InvalidOperation) as exc:
                        attempts.append(f"{provider.name}: invalid rate ({exc})")
                        break
                    self._store(key, quote)
                    return quote
        logger.warning("FX unavailable %s->%s date=%s: %s", source, target, on_date, "; ".join(attempts))
        raise FxUnavailableError(attempts=attempts)


_service: FxRateService | None = None
_service_lock = threading.Lock()


def get_fx_service() -> FxRateService:
    global _service
    with _service_lock:
        if _service is None:
            _service = FxRateService()
        return _service


def set_fx_service(service: FxRateService | None) -> None:
    """Swap the process-wide service (tests inject a deterministic provider; ``None`` restores the default)."""
    global _service
    with _service_lock:
        _service = service
