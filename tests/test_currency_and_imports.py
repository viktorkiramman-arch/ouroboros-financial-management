from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from ouroboros_financial_management.extensions import db
from ouroboros_financial_management.fx import ProviderError, parse_frankfurter_payload
from ouroboros_financial_management.models import CurrencyRate, Transaction
from ouroboros_financial_management.services import ensure_active_workspace, get_exchange_rate, import_csv_text


def test_sqlite_foreign_keys_enabled(app) -> None:
    with app.app_context():
        enabled = db.session.execute(text("PRAGMA foreign_keys")).scalar()
        assert enabled == 1


def test_frankfurter_parser_accepts_dict_payload() -> None:
    quote = parse_frankfurter_payload({"date": "2026-07-03", "rates": {"PHP": "58.25"}}, base="USD", target="PHP")
    assert quote.rate == Decimal("58.25")
    assert quote.rate_date == "2026-07-03"


def test_frankfurter_parser_accepts_list_payload() -> None:
    quote = parse_frankfurter_payload(
        [{"base": "USD", "quote": "PHP", "rate": "58.25", "date": "2026-07-03"}],
        base="USD",
        target="PHP",
    )
    assert quote.rate == Decimal("58.25")


def test_csv_import_preserves_same_date_description_amount_rows(user, app) -> None:
    with app.app_context():
        workspace = ensure_active_workspace(user)
        csv_text = "date,description,amount,memo\n2026-01-01,Coffee,-5.00,first purchase\n2026-01-01,Coffee,-5.00,second purchase\n"
        mapping = {"date": "date", "description": "description", "amount": "amount"}

        first_result = import_csv_text(user.id, workspace.id, csv_text, mapping)
        second_result = import_csv_text(user.id, workspace.id, csv_text, mapping)

        assert first_result == {"imported": 2, "skipped": 0, "errors": 0}
        assert second_result == {"imported": 0, "skipped": 2, "errors": 0}
        rows = Transaction.query.filter_by(user_id=user.id, workspace_id=workspace.id).all()
        assert len(rows) == 2
        assert {row.original_currency_code for row in rows} == {"USD"}
        assert {row.reporting_currency_code for row in rows} == {"USD"}
        assert {row.exchange_rate for row in rows} == {Decimal("1.000000000000")}


def test_fx_falls_back_to_cached_rate(monkeypatch, user, app) -> None:
    with app.app_context():
        db.session.add(
            CurrencyRate(
                base_code="USD",
                target_code="PHP",
                rate=Decimal("58.25"),
                provider="frankfurter",
                rate_date="2026-07-03",
                fetched_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.session.commit()

        def fail_fetch(_provider, _base, _target):
            raise ProviderError("offline")

        monkeypatch.setattr("ouroboros_financial_management.fx.FrankfurterProvider.fetch_rate", fail_fetch)
        data = get_exchange_rate("USD", "PHP")

        assert data["rate"] == "58.250000000000"
        assert data["cached"] is True
        assert data["offlineFallback"] is True
