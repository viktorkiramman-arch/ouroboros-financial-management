from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import secrets
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import mean, pstdev
from typing import Any

from flask import current_app
from sqlalchemy import desc

from .config import INSTANCE_DIR
from .constants import (
    CURRENCY_OPTIONS,
    DEFAULT_CATEGORIES,
    DEFAULT_RULES,
    FX_CACHE_SECONDS,
    MEMBER_ROLES,
    OUROBOROS_ADVISOR_IDENTITY,
    WORKSPACE_TYPES,
)
from .dates import month_bounds, month_key, month_label_from_key, parse_date
from .extensions import db
from .fx import FrankfurterProvider, ProviderError, cooldown_active, normalize_currency_code, record_failure, same_currency_quote
from .models import (
    AnalystRun,
    Budget,
    Category,
    CurrencyRate,
    Insight,
    Rule,
    Transaction,
    User,
    UserSetting,
    Workspace,
    WorkspaceMember,
)
from .money import (
    ValidationError,
    cents_to_number,
    clean_text,
    format_cents,
    normalize_category,
    normalized_lookup,
    parse_money_to_cents,
)


def ensure_user_settings(user: User) -> UserSetting:
    if user.settings:
        return user.settings
    setting = UserSetting(user_id=user.id)
    db.session.add(setting)
    db.session.flush()
    user.settings = setting
    return setting


def create_default_workspace(user: User, *, workspace_type: str = "personal", name: str | None = None) -> Workspace:
    if workspace_type not in WORKSPACE_TYPES:
        workspace_type = "personal"
    label = name or ("Family Budget" if workspace_type == "family" else "Personal Finance")
    workspace = Workspace(
        user_id=user.id, name=clean_text(label, max_length=60, field_name="Workspace name"), workspace_type=workspace_type
    )
    db.session.add(workspace)
    db.session.flush()
    member = WorkspaceMember(
        user_id=user.id,
        workspace_id=workspace.id,
        name=user.username,
        role="breadwinner" if workspace_type in {"personal", "family"} else "member",
        relationship="Self",
    )
    db.session.add(member)
    return workspace


def ensure_active_workspace(user: User) -> Workspace:
    setting = ensure_user_settings(user)
    workspace = None
    if setting.active_workspace_id:
        workspace = Workspace.query.filter_by(id=setting.active_workspace_id, user_id=user.id).first()
    if workspace:
        return workspace
    workspace = Workspace.query.filter_by(user_id=user.id).order_by(Workspace.created_at.asc()).first()
    if not workspace:
        workspace = create_default_workspace(user)
    setting.active_workspace_id = workspace.id
    db.session.flush()
    return workspace


def seed_user_defaults(user: User) -> None:
    setting = ensure_user_settings(user)
    workspace = create_default_workspace(user)
    setting.active_workspace_id = workspace.id
    for name in DEFAULT_CATEGORIES:
        normalized = normalized_lookup(name)
        if not Category.query.filter_by(user_id=user.id, normalized_name=normalized).first():
            db.session.add(Category(user_id=user.id, name=name, normalized_name=normalized))
    for operator, value, category in DEFAULT_RULES:
        exists = Rule.query.filter_by(user_id=user.id, operator=operator, value=value, category=category).first()
        if not exists:
            db.session.add(Rule(user_id=user.id, field="description", operator=operator, value=value, category=category))


def set_active_workspace(user_id: int, workspace_id: int) -> Workspace:
    workspace = Workspace.query.filter_by(id=workspace_id, user_id=user_id).first()
    if not workspace:
        raise ValidationError("Workspace not found.")
    setting = UserSetting.query.filter_by(user_id=user_id).first()
    if not setting:
        raise ValidationError("Settings not found.")
    setting.active_workspace_id = workspace.id
    db.session.flush()
    return workspace


def validate_workspace_form(form: dict[str, Any], *, user_id: int) -> Workspace:
    name = clean_text(form.get("name"), max_length=60, field_name="Workspace name")
    if not name:
        raise ValidationError("Workspace name is required.")
    workspace_type = str(form.get("workspace_type") or "personal")
    if workspace_type not in WORKSPACE_TYPES:
        raise ValidationError("Unsupported workspace type.")
    return Workspace(user_id=user_id, name=name, workspace_type=workspace_type)


def validate_member_form(form: dict[str, Any], *, user_id: int, workspace_id: int) -> WorkspaceMember:
    name = clean_text(form.get("name"), max_length=60, field_name="Member name")
    if not name:
        raise ValidationError("Member name is required.")
    role = str(form.get("role") or "member")
    if role not in MEMBER_ROLES:
        raise ValidationError("Unsupported member role.")
    relationship = clean_text(form.get("relationship") or "Member", max_length=40, field_name="Relationship")
    notes = clean_text(form.get("notes") or "", max_length=160, field_name="Notes")
    income = parse_money_to_cents(form.get("monthly_income") or "0", allow_negative=False, field_name="Monthly income")
    cost = parse_money_to_cents(form.get("monthly_cost") or "0", allow_negative=False, field_name="Monthly cost")
    return WorkspaceMember(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        role=role,
        relationship=relationship,
        monthly_income_cents=income,
        monthly_cost_cents=cost,
        notes=notes,
    )


def transaction_fingerprint(user_id: int, workspace_id: int, tx_date: date, amount_cents: int, description: str) -> str:
    raw = f"{user_id}|{workspace_id}|{tx_date.isoformat()}|{amount_cents}|{normalized_lookup(description)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def import_row_source_hash(user_id: int, workspace_id: int, row: dict[str, Any]) -> str:
    normalized_row = {
        str(key): clean_text(value, max_length=500, field_name="CSV source value")
        for key, value in sorted(row.items(), key=lambda item: str(item[0]))
    }
    raw = json.dumps({"user_id": user_id, "workspace_id": workspace_id, "row": normalized_row}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def import_transaction_fingerprint(user_id: int, workspace_id: int, source_hash: str) -> str:
    raw = f"csv|{user_id}|{workspace_id}|{source_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _currency_snapshot(user_id: int, amount_cents: int, tx_date: date) -> dict[str, Any]:
    setting = UserSetting.query.filter_by(user_id=user_id).first()
    reporting_code = normalize_currency_code(getattr(setting, "base_currency_code", "USD") if setting else "USD")
    return {
        "original_amount_cents": amount_cents,
        "original_currency_code": reporting_code,
        "reporting_amount_cents": amount_cents,
        "reporting_currency_code": reporting_code,
        "exchange_rate": "1",
        "exchange_rate_date": tx_date,
        "exchange_rate_source": "legacy-reporting-currency",
        "rate_precision": 12,
        "status": "posted",
    }


def _utc_age_seconds(now: datetime, value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (now - value).total_seconds()


def categorize_with_rules(description: str, amount_cents: int, rules: list[Rule]) -> str:
    desc = normalized_lookup(description)
    abs_amount = abs(amount_cents)
    for rule in rules:
        if rule.min_cents is not None and abs_amount < rule.min_cents:
            continue
        if rule.max_cents is not None and abs_amount > rule.max_cents:
            continue
        value = normalized_lookup(rule.value)
        if rule.operator == "contains" and value in desc:
            return rule.category
        if rule.operator == "equals" and desc == value:
            return rule.category
        if rule.operator == "starts_with" and desc.startswith(value):
            return rule.category
        if rule.operator == "ends_with" and desc.endswith(value):
            return rule.category
    return "Uncategorized"


def _validated_member_id(value: Any, *, user_id: int, workspace_id: int) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        member_id = int(raw)
    except ValueError as exc:
        raise ValidationError("Invalid member selection.") from exc
    member = WorkspaceMember.query.filter_by(id=member_id, user_id=user_id, workspace_id=workspace_id).first()
    if not member:
        raise ValidationError("Selected member does not belong to this workspace.")
    return member.id


def validate_transaction_form(form: dict[str, Any], *, user_id: int, workspace_id: int) -> Transaction:
    tx_date = parse_date(form.get("date"))
    description = clean_text(form.get("description"), max_length=120, field_name="Description")
    if not description:
        raise ValidationError("Description is required.")
    amount_input = parse_money_to_cents(form.get("amount"), allow_negative=False)
    is_income = form.get("is_income") == "on"
    amount_cents = amount_input if is_income else -abs(amount_input)
    category = normalize_category(form.get("category"), default="Income" if is_income else "Uncategorized")
    member_id = _validated_member_id(form.get("member_id"), user_id=user_id, workspace_id=workspace_id)
    return Transaction(
        user_id=user_id,
        workspace_id=workspace_id,
        member_id=member_id,
        date=tx_date,
        amount_cents=amount_cents,
        **_currency_snapshot(user_id, amount_cents, tx_date),
        description=description,
        category=category,
        is_income=is_income,
        fingerprint=transaction_fingerprint(user_id, workspace_id, tx_date, amount_cents, description),
    )


def upsert_category(user_id: int, name: str) -> None:
    category = normalize_category(name)
    normalized = normalized_lookup(category)
    existing = Category.query.filter_by(user_id=user_id, normalized_name=normalized).first()
    if not existing:
        db.session.add(Category(user_id=user_id, name=category, normalized_name=normalized))


def workspace_transactions(user_id: int, workspace_id: int) -> list[Transaction]:
    return (
        Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )


def monthly_income_expense_series(transactions: list[Transaction], *, max_months: int = 12) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"income": 0, "expenses": 0})
    for t in transactions:
        key = month_key(t.date)
        if t.is_income:
            grouped[key]["income"] += t.amount_cents
        else:
            grouped[key]["expenses"] += abs(t.amount_cents)
    keys = sorted(grouped.keys())[-max_months:]
    return [
        {
            "key": key,
            "label": month_label_from_key(key),
            "income": cents_to_number(grouped[key]["income"]),
            "expenses": cents_to_number(grouped[key]["expenses"]),
            "net": cents_to_number(grouped[key]["income"] - grouped[key]["expenses"]),
        }
        for key in keys
    ]


def budget_status_rows(
    user_id: int, workspace_id: int, *, transactions: list[Transaction] | None = None, budgets: list[Budget] | None = None
) -> list[dict[str, Any]]:
    transactions = (
        transactions if transactions is not None else Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id).all()
    )
    budgets = budgets if budgets is not None else Budget.query.filter_by(user_id=user_id, workspace_id=workspace_id).all()
    today = date.today()
    rows: list[dict[str, Any]] = []
    for budget in budgets:
        actual = sum(
            abs(t.amount_cents)
            for t in transactions
            if not t.is_income and t.category == budget.category and t.date.month == budget.month and t.date.year == budget.year
        )
        remaining = budget.amount_cents - actual
        utilization = round((actual / budget.amount_cents) * 100, 1) if budget.amount_cents else 0
        rows.append(
            {
                "id": budget.id,
                "category": budget.category,
                "month": budget.month,
                "year": budget.year,
                "label": f"{calendar.month_abbr[budget.month]} {budget.year}",
                "budget_cents": budget.amount_cents,
                "actual_cents": actual,
                "remaining_cents": remaining,
                "utilization": utilization,
                "is_over": actual > budget.amount_cents,
                "is_current_month": budget.month == today.month and budget.year == today.year,
            }
        )
    rows.sort(key=lambda r: (r["year"], r["month"], r["category"]), reverse=True)
    return rows


def member_analytics(user_id: int, workspace_id: int, transactions: list[Transaction]) -> dict[str, Any]:
    members = (
        WorkspaceMember.query.filter_by(user_id=user_id, workspace_id=workspace_id)
        .order_by(WorkspaceMember.role.asc(), WorkspaceMember.name.asc())
        .all()
    )
    by_member: dict[int, dict[str, Any]] = {}
    for member in members:
        by_member[member.id] = {
            "id": member.id,
            "name": member.name,
            "role": member.role,
            "relationship": member.relationship,
            "planned_income_cents": member.monthly_income_cents,
            "planned_cost_cents": member.monthly_cost_cents,
            "actual_income_cents": 0,
            "actual_expense_cents": 0,
            "count": 0,
        }
    unassigned = {
        "id": None,
        "name": "Unassigned",
        "role": "other",
        "relationship": "",
        "planned_income_cents": 0,
        "planned_cost_cents": 0,
        "actual_income_cents": 0,
        "actual_expense_cents": 0,
        "count": 0,
    }
    for t in transactions:
        row = by_member.get(t.member_id) if t.member_id else unassigned
        if row is None:
            row = unassigned
        if t.is_income:
            row["actual_income_cents"] += t.amount_cents
        else:
            row["actual_expense_cents"] += abs(t.amount_cents)
        row["count"] += 1
    rows = list(by_member.values())
    if unassigned["count"]:
        rows.append(unassigned)
    breadwinners = [m for m in members if m.role in {"breadwinner", "employee", "department"}]
    dependents = [m for m in members if m.role == "dependent"]
    planned_income = sum(m.monthly_income_cents for m in members)
    planned_cost = sum(m.monthly_cost_cents for m in members)
    return {
        "rows": rows,
        "breadwinner_count": len(breadwinners),
        "dependent_count": len(dependents),
        "planned_income_cents": planned_income,
        "planned_cost_cents": planned_cost,
        "dependent_ratio": round((len(dependents) / max(1, len(breadwinners))) if breadwinners else len(dependents), 2),
    }


def dashboard_summary(user_id: int, workspace_id: int, *, settings: UserSetting, workspace: Workspace) -> dict[str, Any]:
    transactions = (
        Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(Transaction.date.asc(), Transaction.id.asc()).all()
    )
    budgets = (
        Budget.query.filter_by(user_id=user_id, workspace_id=workspace_id)
        .order_by(Budget.year.desc(), Budget.month.desc(), Budget.category.asc())
        .all()
    )
    total_income = sum(t.amount_cents for t in transactions if t.is_income)
    total_expense = sum(abs(t.amount_cents) for t in transactions if not t.is_income)
    net = total_income - total_expense
    savings_rate = round((net / total_income) * 100, 1) if total_income else 0

    today = date.today()
    current_start, current_end = month_bounds(today.year, today.month)
    current_month_transactions = [t for t in transactions if current_start <= t.date <= current_end]
    current_income = sum(t.amount_cents for t in current_month_transactions if t.is_income)
    current_expense = sum(abs(t.amount_cents) for t in current_month_transactions if not t.is_income)

    budget_rows = budget_status_rows(user_id, workspace_id, transactions=transactions, budgets=budgets)
    budget_total = sum(row["budget_cents"] for row in budget_rows if row["is_current_month"])
    budget_actual = sum(row["actual_cents"] for row in budget_rows if row["is_current_month"])
    utilization = round((budget_actual / budget_total) * 100, 1) if budget_total else 0

    expense_by_category: dict[str, int] = defaultdict(int)
    for t in transactions:
        if not t.is_income:
            expense_by_category[t.category] += abs(t.amount_cents)

    monthly = monthly_income_expense_series(transactions)
    recent = sorted(transactions, key=lambda t: (t.date, t.id), reverse=True)[:12]
    insights = (
        Insight.query.filter_by(user_id=user_id, workspace_id=workspace_id, is_read=False).order_by(desc(Insight.created_at)).limit(8).all()
    )
    latest_run = AnalystRun.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(desc(AnalystRun.created_at)).first()
    members = member_analytics(user_id, workspace_id, transactions)

    dependent_load = (
        round((members["planned_cost_cents"] / max(1, members["planned_income_cents"])) * 100, 1) if members["planned_income_cents"] else 0
    )
    fixed_pressure = round((current_expense / max(1, current_income)) * 100, 1) if current_income else 0

    return {
        "workspace": workspace,
        "member_analytics": members,
        "recent": recent,
        "insights": insights,
        "latest_run": latest_run,
        "cards": [
            {"label": "Workspace", "value": workspace.workspace_type.title(), "sub": workspace.name, "tone": "primary"},
            {
                "label": "Total Income",
                "value": format_cents(total_income, CURRENCY_OPTIONS.get(settings.base_currency_code, "$"), settings.base_currency_code),
                "sub": "All-time inflow",
                "tone": "positive",
                "cents": total_income,
            },
            {
                "label": "Total Expenses",
                "value": format_cents(total_expense, CURRENCY_OPTIONS.get(settings.base_currency_code, "$"), settings.base_currency_code),
                "sub": "All-time outflow",
                "tone": "warning",
                "cents": total_expense,
            },
            {
                "label": "Net Cash Flow",
                "value": format_cents(net, CURRENCY_OPTIONS.get(settings.base_currency_code, "$"), settings.base_currency_code),
                "sub": f"Savings rate {savings_rate}%",
                "tone": "primary",
                "cents": net,
            },
            {"label": "Budget Utilization", "value": f"{utilization}%", "sub": "Current month", "tone": "neutral"},
            {
                "label": "Members",
                "value": f"{len(members['rows'])}",
                "sub": f"{members['breadwinner_count']} breadwinner(s), {members['dependent_count']} dependent(s)",
                "tone": "neutral",
            },
            {
                "label": "Dependent Load",
                "value": f"{dependent_load}%",
                "sub": "Planned cost / planned income",
                "tone": "warning" if dependent_load > 30 else "neutral",
            },
            {
                "label": "Monthly Pressure",
                "value": f"{fixed_pressure}%",
                "sub": "This month expense / income",
                "tone": "warning" if fixed_pressure > 80 else "positive",
            },
            {"label": "Transactions", "value": f"{len(transactions):,}", "sub": "Workspace records", "tone": "neutral"},
        ],
        "income_expense_chart": {
            "labels": [item["label"] for item in monthly],
            "income": [item["income"] for item in monthly],
            "expenses": [item["expenses"] for item in monthly],
            "net": [item["net"] for item in monthly],
            "type": settings.income_expense_chart,
            "currency": CURRENCY_OPTIONS.get(settings.base_currency_code, "$"),
            "baseCurrency": settings.base_currency_code,
        },
        "category_chart": {
            "labels": list(expense_by_category.keys()),
            "values": [cents_to_number(v) for v in expense_by_category.values()],
            "type": settings.category_chart,
            "currency": CURRENCY_OPTIONS.get(settings.base_currency_code, "$"),
            "baseCurrency": settings.base_currency_code,
        },
        "budget_rows": budget_rows[:8],
    }


def detect_recurring(transactions: list[Transaction]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[date]] = defaultdict(list)
    for t in transactions:
        groups[(normalized_lookup(t.description), t.amount_cents)].append(t.date)
    recurring: list[dict[str, Any]] = []
    for (description, amount), dates in groups.items():
        dates = sorted(dates)
        if len(dates) < 3:
            continue
        diffs = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        monthly_hits = sum(1 for d in diffs if 25 <= d <= 35)
        weekly_hits = sum(1 for d in diffs if 6 <= d <= 8)
        if monthly_hits >= 2 or weekly_hits >= 3:
            recurring.append(
                {
                    "description": description.title(),
                    "amount_cents": amount,
                    "cadence": "Monthly" if monthly_hits >= 2 else "Weekly",
                    "count": len(dates),
                    "last_date": dates[-1].isoformat(),
                }
            )
    recurring.sort(key=lambda r: abs(r["amount_cents"]), reverse=True)
    return recurring[:10]


def detect_anomalies(transactions: list[Transaction]) -> list[dict[str, Any]]:
    by_cat: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if not t.is_income:
            by_cat[t.category].append(t)
    anomalies: list[dict[str, Any]] = []
    for category, group in by_cat.items():
        if len(group) < 4:
            continue
        values = [abs(t.amount_cents) for t in group]
        avg = mean(values)
        deviation = pstdev(values)
        if deviation <= 0:
            continue
        threshold = avg + 2 * deviation
        for t in group:
            amount = abs(t.amount_cents)
            if amount > threshold:
                anomalies.append(
                    {
                        "date": t.date.isoformat(),
                        "description": t.description,
                        "category": category,
                        "amount_cents": amount,
                        "average_cents": round(avg),
                    }
                )
    anomalies.sort(key=lambda a: a["amount_cents"], reverse=True)
    return anomalies[:10]


def trend_findings(monthly: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    if len(monthly) < 2:
        return findings
    prev = monthly[-2]
    curr = monthly[-1]
    if prev["expenses"] > 0:
        expense_change = ((curr["expenses"] - prev["expenses"]) / prev["expenses"]) * 100
        if expense_change >= 15:
            findings.append(f"Expenses increased {expense_change:.1f}% versus the previous month.")
        elif expense_change <= -15:
            findings.append(f"Expenses decreased {abs(expense_change):.1f}% versus the previous month.")
    if prev["income"] > 0:
        income_change = ((curr["income"] - prev["income"]) / prev["income"]) * 100
        if income_change >= 10:
            findings.append(f"Income increased {income_change:.1f}% versus the previous month.")
        elif income_change <= -10:
            findings.append(f"Income decreased {abs(income_change):.1f}% versus the previous month.")
    if curr["net"] < 0:
        findings.append("The latest month has negative net cash flow.")
    return findings


def generate_analyst_report(user_id: int, workspace_id: int, *, settings: UserSetting) -> AnalystRun:
    workspace = Workspace.query.filter_by(id=workspace_id, user_id=user_id).first()
    transactions = Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(Transaction.date.asc()).all()
    budgets = Budget.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(Budget.year.desc(), Budget.month.desc()).all()
    total_income = sum(t.amount_cents for t in transactions if t.is_income)
    total_expense = sum(abs(t.amount_cents) for t in transactions if not t.is_income)
    net = total_income - total_expense
    savings_rate = (net / total_income * 100) if total_income else 0
    expense_by_category: dict[str, int] = defaultdict(int)
    for t in transactions:
        if not t.is_income:
            expense_by_category[t.category] += abs(t.amount_cents)
    top_categories = sorted(expense_by_category.items(), key=lambda kv: kv[1], reverse=True)[:7]
    monthly = monthly_income_expense_series(transactions, max_months=18)
    budget_rows = budget_status_rows(user_id, workspace_id, transactions=transactions, budgets=budgets)
    over_budget = [row for row in budget_rows if row["is_over"]]
    recurring = detect_recurring(transactions)
    anomalies = detect_anomalies(transactions)
    findings = trend_findings(monthly)
    members = member_analytics(user_id, workspace_id, transactions)

    score = 100
    if total_income <= 0:
        score -= 30
    if savings_rate < 0:
        score -= 35
    elif savings_rate < 10:
        score -= 20
    elif savings_rate < 20:
        score -= 10
    score -= min(25, len(over_budget) * 5)
    score -= min(20, len(anomalies) * 4)
    if members["dependent_count"] and members["breadwinner_count"] == 0:
        score -= 10
    score = max(0, min(100, round(score)))

    period_label = "All data"
    if transactions:
        period_label = f"{transactions[0].date.isoformat()} to {transactions[-1].date.isoformat()}"

    priority_actions: list[str] = []
    if over_budget:
        priority_actions.append(f"Review {len(over_budget)} over-budget budget record(s).")
    if anomalies:
        priority_actions.append("Inspect unusually large transactions before updating budgets.")
    if savings_rate < 10 and total_income > 0:
        priority_actions.append("Build a savings target before adding new discretionary budgets.")
    if workspace and workspace.workspace_type == "family" and members["dependent_count"] and members["breadwinner_count"]:
        priority_actions.append("Compare dependent planned costs with actual dependent-linked spending monthly.")
    if not budgets:
        priority_actions.append("Create monthly budgets for the largest recurring categories.")
    if not priority_actions:
        priority_actions.append("Maintain current budget controls and review trends monthly.")

    symbol = CURRENCY_OPTIONS.get(settings.base_currency_code, "$")
    code = settings.base_currency_code
    if transactions:
        top_text = (
            ", ".join(f"{cat} ({format_cents(amount, symbol, code)})" for cat, amount in top_categories[:3]) or "no expense categories"
        )
        role_text = f"Workspace mode is {workspace.workspace_type if workspace else 'personal'} with {members['breadwinner_count']} breadwinner(s) and {members['dependent_count']} dependent(s)."
        summary_text = (
            f"Ouroboros Advisor summary: Across {len(transactions)} transaction(s), income is "
            f"{format_cents(total_income, symbol, code)}, expenses are {format_cents(total_expense, symbol, code)}, "
            f"and net cash flow is {format_cents(net, symbol, code)}. Savings rate is {savings_rate:.1f}%. "
            f"Largest expense categories: {top_text}. {role_text} Health score: {score}/100. "
            f"Top action: {priority_actions[0]}"
        )
    else:
        summary_text = "Ouroboros Advisor summary: No transactions exist yet. Import or add transactions, then run the analyst again."

    result = {
        "totals": {
            "income_cents": total_income,
            "expense_cents": total_expense,
            "net_cents": net,
            "savings_rate": round(savings_rate, 1),
            "transaction_count": len(transactions),
        },
        "top_categories": [
            {"category": category, "amount_cents": amount, "amount": cents_to_number(amount)} for category, amount in top_categories
        ],
        "monthly": monthly,
        "budget_rows": budget_rows,
        "over_budget": over_budget,
        "recurring": recurring,
        "anomalies": anomalies,
        "trend_findings": findings,
        "priority_actions": priority_actions,
        "members": members,
        "workspace_type": workspace.workspace_type if workspace else "personal",
    }

    Insight.query.filter_by(user_id=user_id, workspace_id=workspace_id).delete()
    for message in priority_actions[:5]:
        db.session.add(Insight(user_id=user_id, workspace_id=workspace_id, message=message, insight_type="analyst"))
    for anomaly in anomalies[:3]:
        db.session.add(
            Insight(
                user_id=user_id,
                workspace_id=workspace_id,
                message=f"Anomaly: {anomaly['description']} in {anomaly['category']} at {format_cents(anomaly['amount_cents'], symbol, code)}.",
                insight_type="anomaly",
            )
        )

    run = AnalystRun(
        user_id=user_id,
        workspace_id=workspace_id,
        period_label=period_label,
        health_score=score,
        summary_text=summary_text,
        result_json=json.dumps(result, default=str),
    )
    db.session.add(run)
    db.session.commit()
    return run


def parse_analyst_result(run: AnalystRun | None) -> dict[str, Any]:
    if not run:
        return {}
    try:
        return json.loads(run.result_json)
    except json.JSONDecodeError:
        return {}


def detect_csv_columns(headers: list[str]) -> dict[str, str]:
    normalized = {normalized_lookup(h).replace("_", " ").replace("-", " "): h for h in headers}

    def pick(candidates: list[str]) -> str:
        for candidate in candidates:
            candidate_norm = normalized_lookup(candidate).replace("_", " ").replace("-", " ")
            if candidate_norm in normalized:
                return normalized[candidate_norm]
        for norm, original in normalized.items():
            if any(candidate in norm for candidate in candidates):
                return original
        return ""

    return {
        "date": pick(["date", "posted date", "transaction date", "posting date"]),
        "description": pick(["description", "memo", "name", "merchant", "details", "payee"]),
        "amount": pick(["amount", "transaction amount", "signed amount"]),
        "debit": pick(["debit", "withdrawal", "spent", "charge"]),
        "credit": pick(["credit", "deposit", "received", "income"]),
        "category": pick(["category", "type"]),
    }


def preview_csv(file_storage) -> dict[str, Any]:
    raw = file_storage.read()
    if not raw:
        raise ValidationError("CSV file is empty.")
    if len(raw) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise ValidationError("CSV file is too large.")
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("CSV must include a header row.")
    headers = [clean_text(h, max_length=80, field_name="CSV header") for h in reader.fieldnames]
    rows = []
    for index, row in enumerate(reader):
        if index >= 5:
            break
        rows.append({h: clean_text(row.get(h), max_length=120, field_name="CSV preview cell") for h in headers})
    if not rows:
        raise ValidationError("CSV has no data rows.")
    return {"headers": headers, "rows": rows, "detected": detect_csv_columns(headers), "raw_text": text}


def save_csv_preview_text(user_id: int, text: str) -> str:
    preview_dir = INSTANCE_DIR / "csv_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    cleanup_csv_previews()
    token = secrets.token_urlsafe(24)
    path = preview_dir / f"{user_id}_{token}.csv"
    path.write_text(text, encoding="utf-8")
    return token


def load_csv_preview_text(user_id: int, token: str) -> str:
    if not token or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in token):
        raise ValidationError("CSV preview expired. Upload the file again.")
    path = INSTANCE_DIR / "csv_previews" / f"{user_id}_{token}.csv"
    if not path.exists():
        raise ValidationError("CSV preview expired. Upload the file again.")
    text = path.read_text(encoding="utf-8")
    try:
        path.unlink()
    except OSError:
        pass
    return text


def cleanup_csv_previews() -> int:
    preview_dir = INSTANCE_DIR / "csv_previews"
    if not preview_dir.exists():
        return 0
    ttl = int(current_app.config.get("PREVIEW_FILE_TTL_SECONDS", 60 * 60))
    cutoff = datetime.now(UTC).timestamp() - ttl
    removed = 0
    for path in preview_dir.glob("*.csv"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            current_app.logger.warning("csv_preview_cleanup_failed", extra={"path": str(path)})
    return removed


def import_csv_text(user_id: int, workspace_id: int, text: str, mapping: dict[str, str]) -> dict[str, int]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("CSV must include a header row.")
    max_rows = int(current_app.config["MAX_CSV_ROWS"])
    rules = Rule.query.filter_by(user_id=user_id).all()
    imported = skipped = errors = 0
    for index, row in enumerate(reader):
        if index >= max_rows:
            skipped += 1
            continue
        try:
            date_col = mapping.get("date", "")
            desc_col = mapping.get("description", "")
            amount_col = mapping.get("amount", "")
            debit_col = mapping.get("debit", "")
            credit_col = mapping.get("credit", "")
            cat_col = mapping.get("category", "")
            tx_date = parse_date(row.get(date_col), field_name="CSV date")
            description = clean_text(row.get(desc_col), max_length=120, field_name="CSV description")
            if not description:
                raise ValidationError("CSV description is required.")

            if amount_col:
                amount_cents = parse_money_to_cents(row.get(amount_col), allow_negative=True, field_name="CSV amount")
            else:
                debit = parse_money_to_cents(row.get(debit_col) or "0", allow_negative=False, field_name="CSV debit") if debit_col else 0
                credit = (
                    parse_money_to_cents(row.get(credit_col) or "0", allow_negative=False, field_name="CSV credit") if credit_col else 0
                )
                amount_cents = credit - debit
            if amount_cents == 0:
                raise ValidationError("Zero amount skipped.")
            is_income = amount_cents > 0
            raw_category = row.get(cat_col) if cat_col else ""
            if raw_category:
                category = normalize_category(raw_category, default="Income" if is_income else "Uncategorized")
            else:
                category = "Income" if is_income else categorize_with_rules(description, amount_cents, rules)
            source_hash = import_row_source_hash(user_id, workspace_id, row)
            fingerprint = import_transaction_fingerprint(user_id, workspace_id, source_hash)
            exists = Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id, fingerprint=fingerprint).first()
            if exists:
                skipped += 1
                continue
            db.session.add(
                Transaction(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    date=tx_date,
                    amount_cents=amount_cents,
                    **_currency_snapshot(user_id, amount_cents, tx_date),
                    description=description,
                    category=category,
                    is_income=is_income,
                    fingerprint=fingerprint,
                    source_hash=source_hash,
                )
            )
            upsert_category(user_id, category)
            imported += 1
        except Exception:
            errors += 1
    db.session.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}


def calendar_data(user_id: int, workspace_id: int, *, year: int, month: int, settings: UserSetting) -> dict[str, Any]:
    start, end = month_bounds(year, month)
    first_weekday, _last_day = calendar.monthrange(year, month)
    offset = first_weekday if settings.calendar_week_start == "monday" else (first_weekday + 1) % 7
    grid_start = start - timedelta(days=offset)
    grid_days = [grid_start + timedelta(days=i) for i in range(42)]
    grid_end = grid_days[-1]
    transactions = (
        Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.workspace_id == workspace_id,
            Transaction.date >= grid_start,
            Transaction.date <= grid_end,
        )
        .order_by(Transaction.date.asc())
        .all()
    )
    by_day: dict[date, dict[str, Any]] = defaultdict(lambda: {"income": 0, "expense": 0, "count": 0, "items": []})
    for t in transactions:
        day = by_day[t.date]
        if t.is_income:
            day["income"] += t.amount_cents
        else:
            day["expense"] += abs(t.amount_cents)
        day["count"] += 1
        day["items"].append(t)

    cells = []
    for d in grid_days:
        data = by_day[d]
        cells.append(
            {
                "date": d,
                "day": d.day,
                "in_month": d.month == month,
                "income_cents": data["income"],
                "expense_cents": data["expense"],
                "net_cents": data["income"] - data["expense"],
                "count": data["count"],
                "items": data["items"],
            }
        )
    month_transactions = [t for t in transactions if start <= t.date <= end]
    income = sum(t.amount_cents for t in month_transactions if t.is_income)
    expense = sum(abs(t.amount_cents) for t in month_transactions if not t.is_income)
    day_summaries = [(d, by_day[d]) for d in by_day if start <= d <= end]
    busiest = max(day_summaries, key=lambda item: item[1]["count"], default=(None, {"count": 0}))
    biggest_expense = max((t for t in month_transactions if not t.is_income), key=lambda t: abs(t.amount_cents), default=None)
    return {
        "cells": cells,
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if settings.calendar_week_start == "monday"
        else ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "label": f"{calendar.month_name[month]} {year}",
        "summary": {
            "income_cents": income,
            "expense_cents": expense,
            "net_cents": income - expense,
            "transaction_count": len(month_transactions),
            "busiest_day": busiest[0],
            "busiest_count": busiest[1]["count"],
            "biggest_expense": biggest_expense,
        },
    }


def get_exchange_rate(base: str, target: str) -> dict[str, Any]:
    base = normalize_currency_code(base)
    target = normalize_currency_code(target)
    if base == target:
        quote = same_currency_quote(base, target)
        return {
            "rate": str(quote.rate),
            "base": base,
            "target": target,
            "provider": quote.provider,
            "date": quote.rate_date,
            "cached": False,
        }
    now = datetime.now(UTC)
    provider = FrankfurterProvider()
    cached = CurrencyRate.query.filter_by(base_code=base, target_code=target, provider=provider.name).first()
    if cached and cached.fetched_at and _utc_age_seconds(now, cached.fetched_at) < FX_CACHE_SECONDS:
        return {
            "rate": str(cached.rate),
            "base": base,
            "target": target,
            "provider": cached.provider,
            "date": cached.rate_date,
            "cached": True,
        }
    if cooldown_active(provider.name, base, target):
        if cached:
            return {
                "rate": str(cached.rate),
                "base": base,
                "target": target,
                "provider": cached.provider,
                "date": cached.rate_date,
                "cached": True,
                "offlineFallback": True,
                "cooldown": True,
            }
        raise ValidationError("Live currency conversion is cooling down after provider failures. Try again shortly.")
    try:
        quote = provider.fetch_rate(base, target)
        if cached:
            cached.rate = quote.rate
            cached.provider = quote.provider
            cached.rate_date = quote.rate_date
            cached.fetched_at = now
            cached.status = "live"
            cached.quality = "provider"
        else:
            db.session.add(
                CurrencyRate(
                    base_code=base, target_code=target, rate=quote.rate, provider=quote.provider, rate_date=quote.rate_date, fetched_at=now
                )
            )
        db.session.commit()
        return {
            "rate": str(quote.rate),
            "base": base,
            "target": target,
            "provider": quote.provider,
            "date": quote.rate_date,
            "cached": False,
        }
    except ProviderError as exc:
        db.session.rollback()
        record_failure(provider.name, base, target)
        if cached:
            return {
                "rate": str(cached.rate),
                "base": base,
                "target": target,
                "provider": cached.provider,
                "date": cached.rate_date,
                "cached": True,
                "offlineFallback": True,
            }
        raise ValidationError("Live currency conversion is unavailable. The app is offline or the provider did not answer.") from exc


def ouroboros_advisor_reply(user_id: int, workspace_id: int, message: str, *, settings: UserSetting) -> dict[str, Any]:
    prompt = clean_text(message, max_length=800, field_name="Message")
    if not prompt:
        raise ValidationError("Message is required.")
    low = prompt.casefold()
    identity_terms = ("who are you", "your name", "identity", "ouroboros advisor", "ouroboros")
    restricted_terms = ("system prompt", "developer", "secret", "password", "database", "leak", "api key", "private info", "hidden")
    if any(term in low for term in identity_terms):
        return {"reply": OUROBOROS_ADVISOR_IDENTITY, "mode": "identity"}
    if any(term in low for term in restricted_terms):
        return {
            "reply": "I can answer finance questions and my public identity only. I will not reveal private app internals or account data.",
            "mode": "safe",
        }

    transactions = Transaction.query.filter_by(user_id=user_id, workspace_id=workspace_id).order_by(Transaction.date.asc()).all()
    budgets = Budget.query.filter_by(user_id=user_id, workspace_id=workspace_id).all()
    total_income = sum(t.amount_cents for t in transactions if t.is_income)
    total_expense = sum(abs(t.amount_cents) for t in transactions if not t.is_income)
    net = total_income - total_expense
    savings_rate = (net / total_income * 100) if total_income else 0
    symbol = CURRENCY_OPTIONS.get(settings.base_currency_code, "$")
    code = settings.base_currency_code
    expense_by_category: dict[str, int] = defaultdict(int)
    for t in transactions:
        if not t.is_income:
            expense_by_category[t.category] += abs(t.amount_cents)
    top_categories = sorted(expense_by_category.items(), key=lambda kv: kv[1], reverse=True)[:5]
    budget_rows = budget_status_rows(user_id, workspace_id, transactions=transactions, budgets=budgets)
    over_budget = [row for row in budget_rows if row["is_over"]]
    members = member_analytics(user_id, workspace_id, transactions)

    if not transactions:
        return {
            "reply": "Add or import transactions first. After that, I can explain cash flow, spending categories, budget pressure, member load, and anomalies.",
            "mode": "finance",
        }

    if any(term in low for term in ("budget", "over budget", "variance")):
        if not budgets:
            reply = "You do not have budgets yet. Create monthly budgets for your largest spending categories first: "
            reply += ", ".join(cat for cat, _ in top_categories[:3]) or "Food, Housing, and Utilities."
        elif over_budget:
            lines = [
                f"{row['category']} is over by {format_cents(-row['remaining_cents'], symbol, code)} for {row['label']}"
                for row in over_budget[:4]
            ]
            reply = "Budget pressure found: " + "; ".join(lines) + ". Start with the largest overrun before changing all budgets."
        else:
            reply = "Your current tracked budgets are not over limit. Keep watching high-frequency categories and update budget caps if income or family/company obligations change."
        return {"reply": reply, "mode": "finance"}

    if any(term in low for term in ("spending", "expense", "category", "where")):
        if top_categories:
            reply = (
                "Largest expense categories are "
                + ", ".join(f"{cat}: {format_cents(amount, symbol, code)}" for cat, amount in top_categories)
                + ". Reduce the first category if you need the fastest cash-flow improvement."
            )
        else:
            reply = "No expense categories are available yet. Add expense transactions or import a CSV."
        return {"reply": reply, "mode": "finance"}

    if any(term in low for term in ("income", "cash flow", "net", "save", "savings")):
        reply = (
            f"Income is {format_cents(total_income, symbol, code)}, expenses are {format_cents(total_expense, symbol, code)}, "
            f"and net cash flow is {format_cents(net, symbol, code)}. Savings rate is {savings_rate:.1f}%. "
        )
        if savings_rate < 0:
            reply += "Cash flow is negative. Cut discretionary categories or increase income before expanding budgets."
        elif savings_rate < 10:
            reply += "Savings rate is thin. Aim for at least a small fixed surplus before adding new recurring costs."
        else:
            reply += "Cash flow has a workable surplus. Review recurring costs monthly."
        return {"reply": reply, "mode": "finance"}

    if any(term in low for term in ("family", "dependent", "breadwinner", "member")):
        reply = (
            f"This workspace has {members['breadwinner_count']} breadwinner(s) and {members['dependent_count']} dependent(s). "
            f"Planned member income is {format_cents(members['planned_income_cents'], symbol, code)} and planned member cost is {format_cents(members['planned_cost_cents'], symbol, code)}. "
            "Link transactions to members to make the family or group analysis sharper."
        )
        return {"reply": reply, "mode": "finance"}

    reply = (
        f"Summary: {len(transactions)} transaction(s), income {format_cents(total_income, symbol, code)}, "
        f"expenses {format_cents(total_expense, symbol, code)}, net {format_cents(net, symbol, code)}, savings rate {savings_rate:.1f}%. "
    )
    if top_categories:
        reply += f"Largest category is {top_categories[0][0]} at {format_cents(top_categories[0][1], symbol, code)}. "
    reply += "Ask about budgets, spending, income, cash flow, family members, dependents, or breadwinners for a more specific answer."
    return {"reply": reply, "mode": "finance"}
