"""legacy baseline schema

Revision ID: 0001_legacy_baseline
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_legacy_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("workspace_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])
    op.create_index("ix_workspaces_workspace_type", "workspaces", ["workspace_type"])

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("relationship", sa.String(length=40), nullable=False),
        sa.Column("monthly_income_cents", sa.Integer(), nullable=False),
        sa.Column("monthly_cost_cents", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_role", "workspace_members", ["role"])

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active_workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("appearance", sa.String(length=16), nullable=False),
        sa.Column("color_theme", sa.String(length=20), nullable=False),
        sa.Column("income_expense_chart", sa.String(length=20), nullable=False),
        sa.Column("category_chart", sa.String(length=20), nullable=False),
        sa.Column("animation_level", sa.String(length=20), nullable=False),
        sa.Column("calendar_week_start", sa.String(length=10), nullable=False),
        sa.Column("base_currency_code", sa.String(length=8), nullable=False),
        sa.Column("display_currency_code", sa.String(length=8), nullable=False),
        sa.Column("currency_code", sa.String(length=8), nullable=False),
        sa.Column("currency_symbol", sa.String(length=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)
    op.create_index("ix_user_settings_active_workspace_id", "user_settings", ["active_workspace_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("workspace_members.id"), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("is_income", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "workspace_id", "member_id", "date", "category", "is_income", "fingerprint"):
        op.create_index(f"ix_transactions_{column}", "transactions", [column])

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "workspace_id", "category", "month", "year", name="uq_budget_user_workspace_category_month_year"),
    )
    for column in ("user_id", "workspace_id", "category"):
        op.create_index(f"ix_budgets_{column}", "budgets", [column])

    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("field", sa.String(length=30), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("min_cents", sa.Integer(), nullable=True),
        sa.Column("max_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rules_user_id", "rules", ["user_id"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("normalized_name", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_category_user_normalized"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("message", sa.String(length=240), nullable=False),
        sa.Column("insight_type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_insights_user_id", "insights", ["user_id"])
    op.create_index("ix_insights_workspace_id", "insights", ["workspace_id"])

    op.create_table(
        "analyst_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_label", sa.String(length=60), nullable=False),
        sa.Column("health_score", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_analyst_runs_user_id", "analyst_runs", ["user_id"])
    op.create_index("ix_analyst_runs_created_at", "analyst_runs", ["created_at"])

    op.create_table(
        "currency_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_code", sa.String(length=8), nullable=False),
        sa.Column("target_code", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("rate_date", sa.String(length=20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("base_code", "target_code", name="uq_currency_rate_pair"),
    )
    op.create_index("ix_currency_rates_base_code", "currency_rates", ["base_code"])
    op.create_index("ix_currency_rates_target_code", "currency_rates", ["target_code"])


def downgrade() -> None:
    for table in (
        "currency_rates",
        "analyst_runs",
        "insights",
        "categories",
        "rules",
        "budgets",
        "transactions",
        "user_settings",
        "workspace_members",
        "workspaces",
        "users",
    ):
        op.drop_table(table)
