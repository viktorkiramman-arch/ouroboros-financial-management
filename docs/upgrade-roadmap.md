# Upgrade Roadmap

## Implemented in this release

- Renamed the product, Python package, assistant, storage defaults, metadata, and documentation to Ouroboros Financial Management.
- Added a custom Ouroboros financial-growth logo and an emerald, navy, and antique-gold visual system.
- Added a responsive Planning Toolkit with emergency-fund, debt-payoff, savings-goal, and 50/30/20 calculators.
- Improved the dashboard with a clearer action layer linking daily tracking, planning, and reporting.
- Added hosted-mode secret enforcement, HSTS for secure sessions, stronger authentication throttles, and stricter CSP directives.
- Removed the packaged local secret and kept instance data out of container builds.
- Added a production container and Firebase Hosting-to-Cloud Run routing configuration.

## Recommended next upgrades

1. Add passkeys or a managed identity provider before supporting multiple people over the public internet.
2. Replace in-memory rate-limit buckets with a shared Redis-backed limiter for multi-instance Cloud Run deployments.
3. Add account and liability models for net-worth tracking and balance reconciliation.
4. Persist recurring bills and savings goals, then surface upcoming obligations on the dashboard and calendar.
5. Add immutable audit events for edits, imports, deletes, workspace changes, and report generation.
6. Add encrypted backups, restore drills, retention rules, and user-controlled data export/deletion.
7. Add browser-level accessibility and end-to-end tests for the highest-risk money flows.
8. Add observability with privacy-safe structured logs, latency/error alerts, and no financial values in log payloads.

These items are intentionally staged. Identity, shared rate limits, auditability, and backup recovery should precede broader multi-user or mobile expansion.
