# Firebase Deployment

The application uses Firebase Hosting as the public edge and Cloud Run for the Flask backend. Cloud Run must use PostgreSQL because its local filesystem is ephemeral.

## Prerequisites

- Firebase CLI and Google Cloud CLI installed and authenticated.
- A Firebase project on the Blaze plan.
- A private PostgreSQL database reachable from Cloud Run.
- Secret Manager API, Cloud Run API, Cloud Build API, and Artifact Registry API enabled.

## One-Time Secrets

Create a random application secret with at least 32 characters and store both values in Secret Manager. Do not put their values in `.env`, `firebase.json`, shell history, or source control.

```powershell
gcloud secrets create ouroboros-secret-key --replication-policy=automatic
gcloud secrets create ouroboros-database-url --replication-policy=automatic
```

Add secret versions through the Google Cloud console or a secure local input flow. Grant the Cloud Run runtime service account `Secret Manager Secret Accessor` for only these secrets.

## Deploy Cloud Run

```powershell
gcloud run deploy ouroboros-financial-management `
  --source . `
  --region asia-southeast1 `
  --allow-unauthenticated `
  --set-env-vars APP_ENV=production,LOCAL_ONLY=false,AUTO_CREATE_DB=false,SESSION_COOKIE_SECURE=true `
  --set-secrets SECRET_KEY=ouroboros-secret-key:latest,DATABASE_URL=ouroboros-database-url:latest
```

Cloud Run is public because Firebase Hosting must reach it. Application accounts, owner checks, CSRF protection, secure cookies, and rate limits protect app routes.

## Run Migrations

Run migrations against the same production `DATABASE_URL` before routing traffic to a schema-changing release. For repeatable deployments, create a Cloud Run Job using the same image with this command:

```text
python -m flask db upgrade
```

Back up PostgreSQL first. Do not set `AUTO_CREATE_DB=true` in production.

## Deploy Firebase Hosting

```powershell
firebase use <your-project-id>
firebase deploy --only hosting
```

The rewrite in `firebase.json` sends every route to the `ouroboros-financial-management` Cloud Run service in `asia-southeast1`.

## Verify

```powershell
firebase hosting:sites:list
gcloud run services describe ouroboros-financial-management --region asia-southeast1
```

Then verify registration, login, CSRF-protected writes, transaction ownership, exports, live FX fallback, secure cookies, and logout on the Firebase URL.

## Rollback

Firebase Hosting keeps release history. Cloud Run keeps immutable revisions. Roll application traffic back to the prior Cloud Run revision and restore the database only when the migration rollback plan explicitly requires it.
