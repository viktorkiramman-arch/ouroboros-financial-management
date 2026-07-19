"""add transaction currency history and Decimal FX cache

Revision ID: 0002_currency_integrity
Revises: 0001_legacy_baseline
Create Date: 2026-07-03
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002_currency_integrity"
down_revision = "0001_legacy_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("original_amount_cents", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("original_currency_code", sa.String(length=3), nullable=True))
        batch.add_column(sa.Column("reporting_amount_cents", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reporting_currency_code", sa.String(length=3), nullable=True))
        batch.add_column(sa.Column("exchange_rate", sa.Numeric(24, 12), nullable=True))
        batch.add_column(sa.Column("exchange_rate_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("exchange_rate_source", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("rate_precision", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("manual_rate_reason", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("source_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("select id, user_id, amount_cents, date, created_at from transactions")).mappings().all()
    for row in rows:
        setting = (
            connection.execute(
                sa.text("select base_currency_code from user_settings where user_id = :user_id"),
                {"user_id": row["user_id"]},
            )
            .mappings()
            .first()
        )
        currency_code = (setting["base_currency_code"] if setting else "USD") or "USD"
        currency_code = currency_code[:3].upper()
        connection.execute(
            sa.text(
                """
                update transactions
                set public_id = :public_id,
                    original_amount_cents = amount_cents,
                    original_currency_code = :currency_code,
                    reporting_amount_cents = amount_cents,
                    reporting_currency_code = :currency_code,
                    exchange_rate = :exchange_rate,
                    exchange_rate_date = date,
                    exchange_rate_source = 'legacy-reporting-currency',
                    rate_precision = 12,
                    status = 'posted',
                    updated_at = coalesce(created_at, CURRENT_TIMESTAMP),
                    version = 1
                where id = :id
                """
            ),
            {"id": row["id"], "public_id": str(uuid.uuid4()), "currency_code": currency_code, "exchange_rate": "1"},
        )

    with op.batch_alter_table("transactions") as batch:
        batch.alter_column("public_id", nullable=False)
        batch.alter_column("original_amount_cents", nullable=False)
        batch.alter_column("original_currency_code", nullable=False)
        batch.alter_column("reporting_amount_cents", nullable=False)
        batch.alter_column("reporting_currency_code", nullable=False)
        batch.alter_column("exchange_rate", nullable=False)
        batch.alter_column("exchange_rate_source", nullable=False)
        batch.alter_column("rate_precision", nullable=False)
        batch.alter_column("status", nullable=False)
        batch.alter_column("updated_at", nullable=False)
        batch.alter_column("version", nullable=False)
        batch.create_index("ix_transactions_public_id", ["public_id"], unique=True)
        batch.create_index("ix_transactions_original_currency_code", ["original_currency_code"])
        batch.create_index("ix_transactions_reporting_currency_code", ["reporting_currency_code"])
        batch.create_index("ix_transactions_status", ["status"])
        batch.create_index("ix_transactions_source_hash", ["source_hash"])
        batch.create_check_constraint("ck_transaction_original_currency_code", "length(original_currency_code) = 3")
        batch.create_check_constraint("ck_transaction_reporting_currency_code", "length(reporting_currency_code) = 3")
        batch.create_check_constraint("ck_transaction_exchange_rate_positive", "exchange_rate > 0")
        batch.create_check_constraint(
            "ck_transaction_status",
            "status in ('draft', 'pending', 'cleared', 'reconciled', 'voided', 'reversed', 'posted')",
        )

    with op.batch_alter_table("currency_rates") as batch:
        batch.drop_constraint("uq_currency_rate_pair", type_="unique")
        batch.alter_column("base_code", existing_type=sa.String(length=8), type_=sa.String(length=3), existing_nullable=False)
        batch.alter_column("target_code", existing_type=sa.String(length=8), type_=sa.String(length=3), existing_nullable=False)
        batch.alter_column("rate", existing_type=sa.Float(), type_=sa.Numeric(24, 12), existing_nullable=False)
        batch.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="live"))
        batch.add_column(sa.Column("quality", sa.String(length=20), nullable=False, server_default="provider"))
        batch.create_unique_constraint("uq_currency_rate_pair_provider", ["base_code", "target_code", "provider"])
        batch.create_check_constraint("ck_currency_rate_base_code", "length(base_code) = 3")
        batch.create_check_constraint("ck_currency_rate_target_code", "length(target_code) = 3")
        batch.create_check_constraint("ck_currency_rate_positive", "rate > 0")


def downgrade() -> None:
    with op.batch_alter_table("currency_rates") as batch:
        batch.drop_constraint("ck_currency_rate_positive", type_="check")
        batch.drop_constraint("ck_currency_rate_target_code", type_="check")
        batch.drop_constraint("ck_currency_rate_base_code", type_="check")
        batch.drop_constraint("uq_currency_rate_pair_provider", type_="unique")
        batch.drop_column("quality")
        batch.drop_column("status")
        batch.alter_column("rate", existing_type=sa.Numeric(24, 12), type_=sa.Float(), existing_nullable=False)
        batch.alter_column("target_code", existing_type=sa.String(length=3), type_=sa.String(length=8), existing_nullable=False)
        batch.alter_column("base_code", existing_type=sa.String(length=3), type_=sa.String(length=8), existing_nullable=False)
        batch.create_unique_constraint("uq_currency_rate_pair", ["base_code", "target_code"])

    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("ck_transaction_status", type_="check")
        batch.drop_constraint("ck_transaction_exchange_rate_positive", type_="check")
        batch.drop_constraint("ck_transaction_reporting_currency_code", type_="check")
        batch.drop_constraint("ck_transaction_original_currency_code", type_="check")
        batch.drop_index("ix_transactions_source_hash")
        batch.drop_index("ix_transactions_status")
        batch.drop_index("ix_transactions_reporting_currency_code")
        batch.drop_index("ix_transactions_original_currency_code")
        batch.drop_index("ix_transactions_public_id")
        for column in (
            "version",
            "updated_at",
            "source_hash",
            "status",
            "manual_rate_reason",
            "rate_precision",
            "exchange_rate_source",
            "exchange_rate_date",
            "exchange_rate",
            "reporting_currency_code",
            "reporting_amount_cents",
            "original_currency_code",
            "original_amount_cents",
            "public_id",
        ):
            batch.drop_column(column)
