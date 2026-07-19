from __future__ import annotations

import pytest

from ouroboros_financial_management.config import _secret_key


def _authenticated_client(app, user):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    return client


def test_toolkit_requires_login(app) -> None:
    response = app.test_client().get("/toolkit")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_ouroboros_brand_and_toolkit_render(app, user) -> None:
    client = _authenticated_client(app, user)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert b"Ouroboros Financial Management" in dashboard.data
    assert b"ouroboros-logo.png" in dashboard.data
    assert b'aria-label="Open navigation"' in dashboard.data

    toolkit = client.get("/toolkit")
    assert toolkit.status_code == 200
    assert b"Emergency fund" in toolkit.data
    assert b"Debt payoff" in toolkit.data
    assert b"Savings goal" in toolkit.data
    assert b"50 / 30 / 20 guide" in toolkit.data
    assert toolkit.headers["X-Content-Type-Options"] == "nosniff"


def test_advisor_identity_uses_new_brand(app, user) -> None:
    client = _authenticated_client(app, user)
    page = client.get("/ai")
    assert page.status_code == 200
    with client.session_transaction() as session:
        csrf_token = session["csrf_token"]

    response = client.post(
        "/api/advisor/chat",
        json={"message": "Who are you?"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json["mode"] == "identity"
    assert "Ouroboros Advisor" in response.json["reply"]


def test_hosted_mode_requires_explicit_secret(monkeypatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _secret_key(app_env="production", local_only=False)
