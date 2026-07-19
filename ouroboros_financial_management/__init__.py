from __future__ import annotations

from flask import Flask, g, request

from .config import INSTANCE_DIR, Config
from .constants import CURRENCY_OPTIONS
from .extensions import db, migrate
from .money import format_cents
from .security import apply_security_headers, csrf_token, enforce_localhost, load_logged_in_user, validate_csrf


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=True)
    app.config.from_object(config_object)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    if migrate is not None:
        migrate.init_app(app, db)

    from .auth import bp as auth_bp
    from .routes import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    app.before_request(enforce_localhost)
    app.before_request(load_logged_in_user)
    app.before_request(validate_csrf)
    app.after_request(apply_security_headers)

    @app.template_filter("money")
    def money_filter(cents: int | None) -> str:
        settings = getattr(g, "settings", None)
        code = getattr(settings, "base_currency_code", "USD")
        symbol = CURRENCY_OPTIONS.get(code, "$")
        return format_cents(cents, symbol, code)

    @app.context_processor
    def inject_globals():
        settings = getattr(g, "settings", None)
        base_code = getattr(settings, "base_currency_code", "USD")
        display_code = getattr(settings, "display_currency_code", base_code)
        return {
            "current_user": getattr(g, "user", None),
            "settings": settings,
            "workspace": getattr(g, "workspace", None),
            "csrf_token": csrf_token,
            "request": request,
            "currency_options": CURRENCY_OPTIONS,
            "base_currency_code": base_code,
            "base_currency_symbol": CURRENCY_OPTIONS.get(base_code, "$"),
            "display_currency_code": display_code,
            "display_currency_symbol": CURRENCY_OPTIONS.get(display_code, CURRENCY_OPTIONS.get(base_code, "$")),
        }

    if app.config.get("AUTO_CREATE_DB", False):
        with app.app_context():
            db.create_all()

    return app
