from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from flask import current_app

from .constants import CURRENCY_OPTIONS
from .money import ValidationError


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class FxQuote:
    base: str
    target: str
    rate: Decimal
    provider: str
    rate_date: str


class FxProvider(Protocol):
    name: str

    def fetch_rate(self, base: str, target: str) -> FxQuote: ...


_FAILURE_UNTIL: dict[tuple[str, str, str], float] = {}


def normalize_currency_code(value: str) -> str:
    code = value.upper().strip()
    if code not in CURRENCY_OPTIONS:
        raise ValidationError("Unsupported currency pair.")
    return code


def parse_decimal_rate(value: Any) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderError("FX provider returned a malformed rate.") from exc
    if not rate.is_finite() or rate <= 0:
        raise ProviderError("FX provider returned an invalid rate.")
    return rate


def parse_frankfurter_payload(payload: Any, *, base: str, target: str) -> FxQuote:
    if isinstance(payload, dict):
        records = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("rates")
        if isinstance(records, dict):
            return FxQuote(
                base=base,
                target=target,
                rate=parse_decimal_rate(records.get(target)),
                provider="frankfurter",
                rate_date=str(payload.get("date") or payload.get("effective_date") or ""),
            )
        if isinstance(records, list):
            payload = records
        else:
            raise ProviderError("FX provider returned an unsupported payload.")

    if isinstance(payload, list):
        for record in payload:
            if not isinstance(record, dict):
                continue
            record_base = str(record.get("base") or record.get("base_code") or base).upper()
            record_target = str(
                record.get("target") or record.get("quote") or record.get("quote_code") or record.get("currency") or ""
            ).upper()
            if record_base == base and record_target == target:
                return FxQuote(
                    base=base,
                    target=target,
                    rate=parse_decimal_rate(record.get("rate") or record.get("value")),
                    provider="frankfurter",
                    rate_date=str(record.get("date") or record.get("effective_date") or ""),
                )
        raise ProviderError("FX provider response did not include the requested currency.")

    raise ProviderError("FX provider returned an unsupported payload.")


class FrankfurterProvider:
    name = "frankfurter"

    def fetch_rate(self, base: str, target: str) -> FxQuote:
        query = urllib.parse.urlencode({"base": base, "quotes": target})
        url = f"https://api.frankfurter.dev/v2/rates?{query}"
        timeout = float(current_app.config.get("FX_TIMEOUT_SECONDS", 4))
        attempts = max(1, int(current_app.config.get("FX_RETRY_ATTEMPTS", 2)))
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(url, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return parse_frankfurter_payload(payload, base=base, target=target)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ProviderError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(min(0.25 * (2**attempt), 1.0))
        raise ProviderError("FX provider is unavailable.") from last_error


def cooldown_active(provider: str, base: str, target: str) -> bool:
    return _FAILURE_UNTIL.get((provider, base, target), 0) > time.monotonic()


def record_failure(provider: str, base: str, target: str) -> None:
    seconds = int(current_app.config.get("FX_FAILURE_COOLDOWN_SECONDS", 120))
    _FAILURE_UNTIL[(provider, base, target)] = time.monotonic() + seconds
    current_app.logger.warning(
        "fx_provider_failure",
        extra={"provider": provider, "base": base, "target": target, "cooldown_seconds": seconds},
    )


def same_currency_quote(base: str, target: str) -> FxQuote:
    return FxQuote(base=base, target=target, rate=Decimal("1"), provider="local", rate_date="same-currency")


def utc_now() -> datetime:
    return datetime.now(UTC)
