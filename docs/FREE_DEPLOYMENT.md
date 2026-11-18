# Earnivanta — free-first deployment checklist

This repository can be developed with free tools. A GitHub repository and GitHub Pages do not provide a running Python API or a persistent production database.

## 1. Publish the static website with GitHub Pages

1. Open the repository: https://github.com/johnyscience9-arch/EARNIVANTA
2. Open **Settings → Pages**.
3. Under **Build and deployment**, choose **GitHub Actions** as the source.
4. Save the setting.
5. Open **Actions → Deploy Earnivanta website** and confirm the newest run succeeds.
6. The expected project URL is https://johnyscience9-arch.github.io/EARNIVANTA/ after GitHub reports a successful deployment.

The current Pages workflow stopped at **Configure Pages** because GitHub returned “Get Pages site failed / Not Found”. Enabling Pages with GitHub Actions is the required repository-side step; rerunning the workflow before that setting is fixed will fail again.

## 2. The API is a separate service

GitHub Pages only serves static files. It cannot run FastAPI, authenticate users, store task evidence, or process wallet/deposit/withdrawal requests.

For a free-first pilot:
- Deploy the FastAPI app in `backend/` to a provider that currently offers a free Python web-service tier.
- Use a managed PostgreSQL database for any hosted multi-user test. Do not use the local SQLite file on an ephemeral web-service filesystem as production storage.
- Free-tier quotas, sleep/hibernation, database retention and pricing can change. Check the provider's current limits before choosing it; never assume a free tier is permanent or suitable for financial records.
- Set the API start command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT` with the service root set to `backend` (or adapt the command to the provider).
- Configure these environment variables in the backend host:
  - `DATABASE_URL`: provider's PostgreSQL connection URL.
  - `TOKEN_SECRET`: a long, random secret generated privately; never commit it.
  - `CORS_ORIGINS`: the exact deployed website origin, for example `https://johnyscience9-arch.github.io` (no trailing slash).
  - `ADMIN_EMAIL` and `ADMIN_PASSWORD`: only for first-admin bootstrap; remove the bootstrap password after creating the admin.
- Test `GET /api/v1/health` and `/docs` after deployment.
- Put the backend's HTTPS base URL into the Control Desk API URL field.

## 3. Safe test order

1. Publish the static site.
2. Deploy the API and persistent database.
3. Confirm health endpoint and CORS from the published site.
4. Create a test account and grant admin/finance role only through the controlled admin process.
5. Test deposits, campaign escrow, task review, wallet ledger and withdrawals with test records only.
6. Verify backups, access controls, audit logging, rate limits, email verification, password reset, migrations and incident procedures before any real users or funds.

## 4. Do not use real money or identity documents yet

This is an evolving development foundation, not a production financial platform. The current API does not integrate with bKash/Nagad, automatically verify transfers, or provide production-grade KYC, NID/passport image storage, live chat or payout automation. Do not collect real deposits, promise earnings, request identity-document images, or pay workers through this test system until security, privacy/legal review, reconciliation, backups and operational controls are independently completed.

## 5. Free-tool policy

- Keep source code and issue tracking in GitHub.
- Use GitHub Actions for automated checks and static-site deployment.
- Prefer free local development tools and free tiers only while their current terms fit the pilot.
- Do not add a paid AI API, paid theme, purchased template, or paid design module without explicit approval.
- Keep Earnivanta's original bespoke visual identity; do not replace it with a generic dashboard/template.
