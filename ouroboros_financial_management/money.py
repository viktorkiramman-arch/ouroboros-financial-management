from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MAX_CENTS = 99_999_999_999
MONEY_QUANT = Decimal("0.01")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE = re.compile(r"\s+")
CATEGORY_ALLOWED = re.compile(r"^[\w &.,/'()\-]{1,40}$", re.UNICODE)
USERNAME_ALLOWED = re.compile(r"^[A-Za-z0-9_\-.]{3,32}$")
DANGEROUS_SPREADSHEET_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class ValidationError(ValueError):
    pass


def clean_text(value: Any, *, max_length: int, field_name: str) -> str:
    if value is None:
        return ""
    text = CONTROL_CHARS.sub(" ", str(value))
    text = WHITESPACE.sub(" ", text).strip()
    if len(text) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or less.")
    return text


def normalize_username(value: Any) -> str:
    username = clean_text(value, max_length=32, field_name="Username")
    if not USERNAME_ALLOWED.match(username):
        raise ValidationError("Username must be 3-32 characters and use letters, numbers, dots, hyphens, or underscores.")
    return username


def validate_password(value: Any) -> str:
    password = str(value or "")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValidationError("Password must be 128 characters or less.")
    return password


def normalize_category(value: Any, *, default: str = "Uncategorized") -> str:
    text = clean_text(value, max_length=40, field_name="Category")
    if not text:
        text = default
    if not CATEGORY_ALLOWED.match(text):
        raise ValidationError("Category contains unsupported characters.")
    return text


def normalized_lookup(value: Any) -> str:
    return WHITESPACE.sub(" ", str(value or "").strip().casefold())


def parse_money_to_cents(value: Any, *, allow_negative: bool = True, field_name: str = "Amount") -> int:
    if value is None:
        raise ValidationError(f"{field_name} is required.")
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip().replace(",", "")
        for symbol in ("$", "₱", "€", "£", "¥", "₹", "₩", "฿", "₫"):
            text = text.replace(symbol, "")
        text = text.replace("USD", "").replace("PHP", "").strip()
        if not text:
            raise ValidationError(f"{field_name} is required.")
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(f"{field_name} must be a valid money value.") from exc
    if not amount.is_finite():
        raise ValidationError(f"{field_name} must be finite.")
    if not allow_negative and amount < 0:
        raise ValidationError(f"{field_name} cannot be negative.")
    amount = amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    cents = int(amount * 100)
    if abs(cents) > MAX_CENTS:
        raise ValidationError(f"{field_name} is too large.")
    return cents


def cents_to_number(cents: int | None) -> float:
    return round((int(cents or 0) / 100), 2)


def format_cents(cents: int | None, symbol: str = "$", code: str | None = None) -> str:
    cents_value = int(cents or 0)
    sign = "-" if cents_value < 0 else ""
    cents_abs = abs(cents_value)
    dollars = cents_abs // 100
    remainder = cents_abs % 100
    prefix = f"{symbol}" if symbol else ""
    suffix = f" {code}" if code and code not in {"USD"} else ""
    return f"{sign}{prefix}{dollars:,}.{remainder:02d}{suffix}"


def spreadsheet_safe(value: Any) -> str:
    text = clean_text(value, max_length=500, field_name="Export text")
    if text.startswith(DANGEROUS_SPREADSHEET_PREFIXES):
        return "'" + text
    return text
