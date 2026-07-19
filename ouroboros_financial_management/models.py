from __future__ import annotations

import uuid
from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    workspaces = db.relationship("Workspace", back_populates="user", cascade="all, delete-orphan")
    members = db.relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    rules = db.relationship("Rule", back_populates="user", cascade="all, delete-orphan")
    categories = db.relationship("Category", back_populates="user", cascade="all, delete-orphan")
    insights = db.relationship("Insight", back_populates="user", cascade="all, delete-orphan")
    settings = db.relationship("UserSetting", back_populates="user", cascade="all, delete-orphan", uselist=False)
    analyst_runs = db.relationship("AnalystRun", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Workspace(db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    workspace_type = db.Column(db.String(20), nullable=False, default="personal", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="workspaces")
    members = db.relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", back_populates="workspace")
    budgets = db.relationship("Budget", back_populates="workspace")


class WorkspaceMember(db.Model):
    __tablename__ = "workspace_members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member", index=True)
    relationship = db.Column(db.String(40), nullable=False, default="Self")
    monthly_income_cents = db.Column(db.Integer, nullable=False, default=0)
    monthly_cost_cents = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.String(160), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="members")
    workspace = db.relationship("Workspace", back_populates="members")
    transactions = db.relationship("Transaction", back_populates="member")


class UserSetting(db.Model):
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)
    active_workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=True, index=True)
    appearance = db.Column(db.String(16), nullable=False, default="system")
    color_theme = db.Column(db.String(20), nullable=False, default="ocean")
    income_expense_chart = db.Column(db.String(20), nullable=False, default="line")
    category_chart = db.Column(db.String(20), nullable=False, default="donut")
    animation_level = db.Column(db.String(20), nullable=False, default="standard")
    calendar_week_start = db.Column(db.String(10), nullable=False, default="sunday")
    base_currency_code = db.Column(db.String(8), nullable=False, default="USD")
    display_currency_code = db.Column(db.String(8), nullable=False, default="USD")
    currency_code = db.Column(db.String(8), nullable=False, default="USD")
    currency_symbol = db.Column(db.String(6), nullable=False, default="$")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship("User", back_populates="settings")


class Transaction(db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.CheckConstraint("length(original_currency_code) = 3", name="ck_transaction_original_currency_code"),
        db.CheckConstraint("length(reporting_currency_code) = 3", name="ck_transaction_reporting_currency_code"),
        db.CheckConstraint("exchange_rate > 0", name="ck_transaction_exchange_rate_positive"),
        db.CheckConstraint(
            "status in ('draft', 'pending', 'cleared', 'reconciled', 'voided', 'reversed', 'posted')", name="ck_transaction_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey("workspace_members.id"), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    original_amount_cents = db.Column(db.Integer, nullable=False, default=0)
    original_currency_code = db.Column(db.String(3), nullable=False, default="USD", index=True)
    reporting_amount_cents = db.Column(db.Integer, nullable=False, default=0)
    reporting_currency_code = db.Column(db.String(3), nullable=False, default="USD", index=True)
    exchange_rate = db.Column(db.Numeric(24, 12), nullable=False, default=1)
    exchange_rate_date = db.Column(db.Date, nullable=True)
    exchange_rate_source = db.Column(db.String(40), nullable=False, default="local")
    rate_precision = db.Column(db.Integer, nullable=False, default=12)
    manual_rate_reason = db.Column(db.String(160), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="posted", index=True)
    description = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="Uncategorized", index=True)
    is_income = db.Column(db.Boolean, nullable=False, default=False, index=True)
    fingerprint = db.Column(db.String(80), nullable=True, index=True)
    source_hash = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)

    user = db.relationship("User", back_populates="transactions")
    workspace = db.relationship("Workspace", back_populates="transactions")
    member = db.relationship("WorkspaceMember", back_populates="transactions")


class Budget(db.Model):
    __tablename__ = "budgets"
    __table_args__ = (
        db.UniqueConstraint("user_id", "workspace_id", "category", "month", "year", name="uq_budget_user_workspace_category_month_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="budgets")
    workspace = db.relationship("Workspace", back_populates="budgets")


class Rule(db.Model):
    __tablename__ = "rules"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    field = db.Column(db.String(30), nullable=False, default="description")
    operator = db.Column(db.String(20), nullable=False)
    value = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    min_cents = db.Column(db.Integer, nullable=True)
    max_cents = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="rules")


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (db.UniqueConstraint("user_id", "normalized_name", name="uq_category_user_normalized"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(40), nullable=False)
    normalized_name = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="categories")


class Insight(db.Model):
    __tablename__ = "insights"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=True, index=True)
    message = db.Column(db.String(240), nullable=False)
    insight_type = db.Column(db.String(30), nullable=False, default="auto")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", back_populates="insights")


class AnalystRun(db.Model):
    __tablename__ = "analyst_runs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    period_label = db.Column(db.String(60), nullable=False, default="All data")
    health_score = db.Column(db.Integer, nullable=False, default=0)
    summary_text = db.Column(db.Text, nullable=False)
    result_json = db.Column(db.Text, nullable=False)

    user = db.relationship("User", back_populates="analyst_runs")


class CurrencyRate(db.Model):
    __tablename__ = "currency_rates"
    __table_args__ = (
        db.UniqueConstraint("base_code", "target_code", "provider", name="uq_currency_rate_pair_provider"),
        db.CheckConstraint("length(base_code) = 3", name="ck_currency_rate_base_code"),
        db.CheckConstraint("length(target_code) = 3", name="ck_currency_rate_target_code"),
        db.CheckConstraint("rate > 0", name="ck_currency_rate_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    base_code = db.Column(db.String(3), nullable=False, index=True)
    target_code = db.Column(db.String(3), nullable=False, index=True)
    rate = db.Column(db.Numeric(24, 12), nullable=False)
    provider = db.Column(db.String(40), nullable=False, default="frankfurter")
    rate_date = db.Column(db.String(20), nullable=False, default="")
    fetched_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="live", index=True)
    quality = db.Column(db.String(20), nullable=False, default="provider")
