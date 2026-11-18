# Earnivanta

**Work. Promote. Build. Grow.**

Earnivanta is a digital marketplace project for:
- Workers: lawful research, product testing, feedback and real task opportunities.
- Advertisers: genuine awareness, voluntary participation and consent-based lead generation.
- Businesses and individuals: custom websites, Android applications and Windows software.
- Platform operations: human review of campaigns, task evidence and manual payment records.

## Current repository status

The public website and a connected API client portal are in the repository:
- `index.html` — bilingual English/Bangla public landing page.
- `portal.html` — member sign-up/sign-in, wallet, task feed and evidence submission, advertiser campaign drafts, deposit claims, admin/reviewer queues, finance queues and payment destination settings.
- `finance.html` — separate finance operations console.
- `payment-settings.html` — separate payment destination administration.
- `add-funds.html` — standalone manual deposit claim page.
- `backend/` — FastAPI API, SQLAlchemy models, PostgreSQL driver, Dockerfile, local environment example and workflow integration tests.
- `render.yaml` — API hosting blueprint for a Python web service; a persistent PostgreSQL URL and first-admin bootstrap credentials must be supplied privately.
- `.github/workflows/` — GitHub Pages deployment, backend checks and frontend JavaScript validation.

The public frontend is hosted by GitHub Pages. The API is a separate service and **has not been deployed or connected to a production database yet**. The repository now includes a hosting blueprint and production startup guards, but these do not create a hosting account or database automatically. The portal asks for an API base URL; until an API service is deployed and configured, sign-up, sign-in, wallet and operational actions cannot work online.

## What is implemented in the API foundation

- Registration and login with PBKDF2-HMAC-SHA256 password hashes and signed expiring bearer tokens.
- Role-protected member, advertiser, maintenance, reviewer, finance and admin routes.
- Campaign and task draft creation, moderation, worker evidence and reviewer decisions.
- Append-only wallet ledger, manual deposit claims, campaign escrow, reward credit on approved evidence, withdrawal holds and manual processing.
- Admin-managed bKash, Nagad, Rocket, Upay, bank and other payment destinations.
- Integration tests for campaign/task/submission lifecycle, wallet/withdrawal lifecycle and verified deposit/escrow/reward lifecycle.

## Not yet ready for public business operation

This repository is **not a production-ready marketplace**. The following are still required before accepting real users or money:
- Deploy the API and managed PostgreSQL database using `render.yaml`; configure a strong secret, exact CORS origins, backups and monitoring.
- Production security work: rate limiting, email verification, password reset, token revocation, audit logs, database migrations, CSRF strategy and security review.
- A complete user/staff directory and permission assignment interface; role assignment currently requires a known user ID.
- A real project-order workflow, quote/milestone/delivery tracking and live support chat.
- KYC workflow and legal/privacy review. Do not upload NID/passport images or sensitive identity documents to the current API.
- Payment reconciliation against actual merchant transaction history. No bKash/Nagad gateway or automatic payment verification exists.
- Production payout operations, customer support and dispute/refund policy.
- End-to-end tests against a deployed staging API and accessibility/security testing.

Do not collect real money, joining fees or identity documents through the current prototype. Do not promise income. Any future joining fee must pay for a clearly disclosed real service and must never fund other members or recruitment rewards.

## Campaign integrity

Do not publish artificial likes, follows, subscribers, views, fabricated reviews, deceptive platform manipulation or undisclosed engagement. Use compliant advertising, voluntary research, honest product feedback, consent-based leads and genuine work.

## Deploy

GitHub Pages publishes the static website from `main` using `.github/workflows/pages.yml`. The API is not deployed by that workflow. Backend deployment instructions and environment requirements are in [backend/README.md](backend/README.md) and [docs/FREE_DEPLOYMENT.md](docs/FREE_DEPLOYMENT.md).

## Tests

- Frontend: GitHub Actions extracts and syntax-checks every inline JavaScript block in all five HTML pages with Node.js.
- Backend: GitHub Actions compiles the FastAPI app and runs the integration test suite with pytest.
