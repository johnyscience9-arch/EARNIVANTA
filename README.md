# Earnivanta

**Work. Promote. Build. Grow.**

Earnivanta is a bilingual digital work and promotion platform prototype for genuine research, product feedback, consent-based lead generation, advertiser campaigns, and custom digital services.

## Live services

- Public website: https://johnyscience9-arch.github.io/EARNIVANTA/
- Member portal: https://johnyscience9-arch.github.io/EARNIVANTA/portal.html
- Finance console: https://johnyscience9-arch.github.io/EARNIVANTA/finance.html
- Payment destination settings: https://johnyscience9-arch.github.io/EARNIVANTA/payment-settings.html
- Add funds: https://johnyscience9-arch.github.io/EARNIVANTA/add-funds.html
- API health: https://earnivanta-api-ozq5.onrender.com/api/v1/health
- API docs: https://earnivanta-api-ozq5.onrender.com/docs

The frontend is deployed by GitHub Pages. The FastAPI backend is deployed on Render and connects to the Supabase PostgreSQL project. The member portal now has the live API base URL preconfigured; users do not need to enter it manually.

## Repository map

- `index.html` — public bilingual landing page.
- `portal.html` — registration/login, member wallet, tasks and submissions, advertiser campaign and funding flows, admin/reviewer queues, finance queues, user-role and payment destination administration.
- `finance.html` — finance operations console.
- `payment-settings.html` — payment destination administration.
- `add-funds.html` — manual deposit claim page.
- `backend/` — FastAPI, SQLAlchemy models, authentication, campaign/task moderation, submissions, wallet ledger, manual deposit verification, campaign escrow and manual withdrawals.
- `render.yaml` — Render service blueprint.
- `.github/workflows/` — Pages deployment and frontend/backend validation workflows.

## Implemented API features

- Email/password registration and login; PBKDF2-HMAC-SHA256 password hashing and signed expiring bearer tokens.
- Role-based authorization for member, advertiser, reviewer, finance and admin operations.
- Campaign and task creation, review, publishing and participant evidence submissions.
- Wallet balance and transaction history backed by an append-only ledger.
- Manual deposit claims, staff verification, advertiser wallet credits and campaign budget escrow.
- Reward credit from funded campaign escrow after staff approves task evidence.
- Withdrawal requests with reserved funds and manual finance processing.
- Admin-managed payment destinations for manual payment instructions.

## Release checks completed

- Render API deployment reports `live`.
- Render service logs show repeated `GET /api/v1/health` responses with `200 OK`.
- Supabase project reports `ACTIVE_HEALTHY`.
- GitHub Pages deployment workflow succeeded for the latest frontend commit.
- Frontend validation workflow succeeded, including inline JavaScript syntax checks for all five HTML pages.
- Backend checks passed on the latest backend commit.

See [docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md) for the verification scope and remaining production gates.

## Important limits — not ready for real-money public operation

This is a deployed prototype, not a fully audited financial marketplace. The following still require implementation or independent verification before public launch:
- Email verification and secure password reset delivery.
- Rate limiting, token revocation, audit logging and formal database migrations.
- Backup/restore testing, monitoring and a security review.
- Payment reconciliation against actual merchant transaction records; no bKash/Nagad automatic gateway or automatic verification is connected.
- Dispute/refund procedures, operational support and legal/privacy review.
- End-to-end testing of every role and payment path against production data.

Do not collect joining fees, deposits or identity documents, and do not promise earnings until those controls and operating procedures are completed. Only publish lawful work with real value. Do not support fake likes, follows, views, subscribers, fabricated reviews or deceptive platform manipulation.

## Local development

From the `backend` folder, create a Python 3.12 virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, and run:

```bash
uvicorn app.main:app --reload
```

Run backend tests from `backend` using `pytest -q`.
