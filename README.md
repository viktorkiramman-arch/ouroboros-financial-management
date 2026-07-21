# Ouroboros Financial Management

**Frontend:** https://viktorkiramman-arch.github.io/ouroboros-financial-management/

> The frontend link is a static product preview with sample data. Run the Flask application locally for accounts, transactions, reports, and persistence.

A private Flask financial-management workspace for personal, family, company, and group finances. Ouroboros combines transaction tracking, budgets, reports, calendar analytics, local workspace-aware guidance, currency conversion, and decision-planning calculators.

## Highlights

- Cohesive Ouroboros fintech identity with a custom serpent-and-growth logo.
- Dashboard for income, expenses, net cash flow, category trends, budget health, and member load.
- Transactions with CSV mapping, validation, categorization rules, and duplicate protection.
- Monthly budgets, calendar summaries, analyst runs, and Excel, Word, and PDF exports.
- Ouroboros Advisor, a deterministic local guide that does not call an external AI provider.
- Planning Toolkit for emergency funds, debt payoff, savings goals, and 50/30/20 scenarios.
- Multiple workspaces, roles, currencies, themes, chart styles, and motion settings.
- CSRF checks, server-side validation, owner checks, rate limits, secure headers, safe exports, and hosted-mode secret enforcement.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`, register a local account, and create a workspace. Local mode stores data in `instance/ouroboros.db` and rejects non-loopback traffic.

## Production Architecture

Firebase Hosting is configured as the public edge and routes requests to a containerized Cloud Run service. Production requires:

- A Firebase/Google Cloud project with billing enabled.
- A private PostgreSQL database. Do not use SQLite on Cloud Run; its filesystem is ephemeral.
- `SECRET_KEY` and `DATABASE_URL` supplied through Secret Manager.
- `APP_ENV=production`, `LOCAL_ONLY=false`, `AUTO_CREATE_DB=false`, and `SESSION_COOKIE_SECURE=true`.
- Database migrations run before serving new application code.

See `docs/firebase-deploy.md` for the deployment sequence.

## CSV Format

```csv
date,description,amount,category
2026-01-02,Salary,5200,Income
2026-01-04,Rent,-1850,Housing
2026-01-05,Grocery Market,-145.32,Food
```

Positive signed amounts are income and negative signed amounts are expenses. Separate debit and credit columns can also be mapped during import.

## Privacy Notes

- Ouroboros Advisor is local application logic, not a generative AI integration.
- Live currency conversion calls the configured public FX provider through the server and caches rates.
- Calculator inputs remain in the current browser tab and are not saved.
- Financial exports can contain sensitive data; store and share them carefully.

## Project Commands

Use these commands for this repo:

- Install: `python -m pip install -r requirements.txt`
- Dev: `python run.py`
- Build: `docker build -t ouroboros-financial-management .`
- Test: `python -m pytest`
- Lint: `python -m ruff check .`
- Type-check: not configured
- Format: `python -m ruff format .`

## Migrations

```powershell
$env:FLASK_APP = "wsgi.py"
$env:AUTO_CREATE_DB = "false"
python -m flask db upgrade
```

Back up the database before every production migration. See `docs/upgrade.md`.
