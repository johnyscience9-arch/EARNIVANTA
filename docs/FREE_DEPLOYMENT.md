# Earnivanta — deployment and operations

## Live deployment

The current deployment is online:

- Website: https://johnyscience9-arch.github.io/EARNIVANTA/
- Member portal: https://johnyscience9-arch.github.io/EARNIVANTA/portal.html
- API: https://earnivanta-api-ozq5.onrender.com
- Health endpoint: https://earnivanta-api-ozq5.onrender.com/api/v1/health
- Render dashboard: https://dashboard.render.com/web/srv-dbv0v6ek1f9s73b33g4g
- GitHub repository: https://github.com/johnyscience9-arch/EARNIVANTA

The Render service is configured from the repository's `backend` directory, using Python, `pip install -r requirements.txt`, and `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Its health-check path is `/api/v1/health`. The live service uses the Supabase PostgreSQL connection configured privately in Render. Never put database passwords, token secrets or administrator passwords in this repository or in public messages.

The GitHub Pages workflow publishes the repository root. The portal, finance console, payment settings and add-funds pages now default to the live API base URL.

## Verified deployment checks

At the latest release check:
- Render's latest deployment status was `live`.
- Render logs showed repeated successful `GET /api/v1/health` responses with `200 OK`.
- Supabase project status was `ACTIVE_HEALTHY`.
- GitHub Pages deployment workflow completed successfully for the latest frontend commit.
- Frontend checks completed successfully, including Node.js syntax validation of inline scripts in all five HTML pages.
- Backend validation and integration tests passed on the latest backend commit.

These checks establish that the hosting and health endpoint are operating. They do not prove every user journey, payment or administrative operation has passed a live end-to-end test.

## Runtime environment

The Render service should retain:
- `APP_ENV=production`
- `DATABASE_URL` — Supabase PostgreSQL Session Pooler URL, with URL-encoded password characters where required.
- `TOKEN_SECRET` — generated secret of at least 32 characters.
- `TOKEN_TTL_HOURS=24`
- `CORS_ORIGINS=https://johnyscience9-arch.github.io`
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` only for initial administrator bootstrap.

The backend creates the initial administrator only when both admin variables are present and the email does not already exist. After confirming the first administrator can sign in, remove `ADMIN_PASSWORD` from the Render environment and redeploy. Do not share credentials in chat or commit them.

## Current product scope

Implemented workflows include account registration/login, role-based portal views, campaign and task moderation, worker evidence submission, wallet ledger, manual deposit claims, staff verification, campaign escrow, funded task reward credit, withdrawal holds/manual processing, and payment destination administration.

## Production safety gates still outstanding

This project remains a deployed prototype and must not be represented as a fully audited or production-ready financial service. Before accepting real users or money, complete:
- Email verification and password reset delivery.
- Rate limiting, token revocation and audit logging.
- Formal database migrations and tested backup/restore procedures.
- Security, privacy and legal review.
- Independent reconciliation of actual bKash/Nagad/bank payments; no automatic gateway or automatic payment verification is connected.
- Dispute/refund process, support operations and end-to-end tests for all roles and money flows.

Do not collect joining fees, deposits or identity documents and do not promise earnings through the prototype. Payment destination details are instructions for manual transfers, not proof of payment. Staff must independently verify a transaction before approving a deposit. A screenshot alone is not verification.

## Campaign integrity

Only support lawful work with real value: voluntary research, honest product testing, disclosed content, consent-based leads and genuine feedback. Do not publish fake likes, follows, views, subscribers, fabricated reviews or deceptive platform manipulation.
