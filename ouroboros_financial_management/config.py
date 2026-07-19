from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
load_dotenv(BASE_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _secret_key(*, app_env: str, local_only: bool) -> str:
    env_secret = os.environ.get("SECRET_KEY", "").strip()
    if len(env_secret) >= 32:
        return env_secret
    if app_env == "production" or not local_only:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters in hosted mode.")
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = INSTANCE_DIR / "local_secret.key"
    if secret_file.exists():
        value = secret_file.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    value = secrets.token_hex(32)
    secret_file.write_text(value, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return value


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'ouroboros.db'}")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


class Config:
    ENV = os.environ.get("FLASK_ENV", os.environ.get("APP_ENV", "development"))
    LOCAL_ONLY = _bool_env("LOCAL_ONLY", True)
    SECRET_KEY = _secret_key(app_env=ENV, local_only=LOCAL_ONLY)
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = _bool_env("AUTO_CREATE_DB", LOCAL_ONLY and ENV != "production")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", "1048576"))
    MAX_CSV_ROWS = int(os.environ.get("MAX_CSV_ROWS", "1000"))
    FX_TIMEOUT_SECONDS = float(os.environ.get("FX_TIMEOUT_SECONDS", "4"))
    FX_RETRY_ATTEMPTS = int(os.environ.get("FX_RETRY_ATTEMPTS", "2"))
    FX_FAILURE_COOLDOWN_SECONDS = int(os.environ.get("FX_FAILURE_COOLDOWN_SECONDS", "120"))
    PREVIEW_FILE_TTL_SECONDS = int(os.environ.get("PREVIEW_FILE_TTL_SECONDS", str(60 * 60)))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", not LOCAL_ONLY or ENV == "production")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    PREFERRED_URL_SCHEME = "https" if SESSION_COOKIE_SECURE else "http"
    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "object-src 'none'; "
        "manifest-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )
