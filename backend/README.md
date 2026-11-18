# Earnivanta API — development foundation

## Included in this milestone

- FastAPI application and health endpoint.
- Member registration and login with PBKDF2-HMAC-SHA256 password hashes.
- Signed, expiring bearer tokens.
- Role-protected advertiser campaign and draft-task creation.
- Campaign submission and reviewer/admin approval or rejection.
- Worker task evidence submission, one submission per worker/task, participant-capacity checks, and reviewer/admin approval or rejection.
- Task submission and reviewer/admin approval or rejection; workers only see published tasks under active campaigns.
- Admin role assignment endpoint; first admin can be bootstrapped with environment variables.
- SQLite for local development; SQLAlchemy supports a separately configured database URL.

## Run locally (Python 3.11+)

```bash
cd backend
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API reference.

Run the backend integration tests from the `backend` directory with `pip install pytest httpx` followed by `pytest -q`. The test suite covers campaign moderation, task publishing, worker evidence, duplicate submissions, participant limits and review outcomes.

## Moderation flow

1. An admin assigns the advertiser role to an approved account.
2. The advertiser creates a draft campaign and adds at least one draft task.
3. The advertiser submits the campaign with `POST /api/v1/campaigns/{id}/submit`.
4. An admin/reviewer approves or rejects it with `POST /api/v1/admin/campaigns/{id}/review` and JSON `{"decision":"approve"}` or `{"decision":"reject"}`.
5. Once the campaign is active, the advertiser submits each draft task with `POST /api/v1/campaigns/{campaign_id}/tasks/{task_id}/submit`.
6. An admin/reviewer approves or rejects each task with `POST /api/v1/admin/tasks/{task_id}/review`. Only approved tasks in active campaigns appear in the worker task feed.

Campaigns move from `draft` to `pending_review`, then to `active` or `rejected`. Tasks move from `draft` to `pending_review`, then to `published` or `rejected`.

Only approve campaigns and tasks that are lawful, accurately described, properly funded, and safe for participants. Do not approve fake engagement, fabricated reviews, misleading claims, or tasks that require users to deceive platforms or other people.

## Worker evidence flow

- Workers with the `member` or `maintenance` role can view published tasks and submit evidence using `POST /api/v1/tasks/{task_id}/submissions`.
- Evidence consists of a short written explanation and an optional reference URL. Do not upload identity documents or sensitive personal data as task evidence.
- A worker can submit once per task. Pending and approved submissions count toward the task participant capacity.
- Workers can see their own submission history at `GET /api/v1/my/submissions`.
- Admins/reviewers can inspect pending evidence at `GET /api/v1/admin/submissions` and decide with `POST /api/v1/admin/submissions/{submission_id}/review`, sending `{"decision":"approve","reviewer_note":"..."}` or `{"decision":"reject","reviewer_note":"..."}`.
- Approval records task completion only. It does not credit a wallet or promise a payout; a separately audited payment ledger and funded reward process are still required.

## Important deployment requirements

- Replace `TOKEN_SECRET` with a cryptographically random secret. The fallback secret is local-development-only.
- Set `CORS_ORIGINS` to the exact deployed frontend origin(s), not `*` when credentials are enabled.
- Set a strong `ADMIN_PASSWORD` only during initial bootstrap, then remove it from the deployment environment.
- SQLite is for local development/single-instance testing. Use managed PostgreSQL for a multi-instance production deployment and configure backups.
- This milestone is not production-ready: rate limiting, email verification, password reset, refresh/revocation, audit logging, migrations, CSRF strategy, monitoring and automated tests remain required.
- No real payments, wallet credits, identity document uploads, KYC, withdrawal payout or live chat are implemented. Do not collect NID/passport images or real money through this API yet.


## Wallet ledger and manual withdrawals (development foundation)

- Wallet balances are calculated from append-only ledger entries; existing entries are not edited or deleted by these API routes.
- Amounts use integer minor units: for BDT, 100 minor units = ৳1.00. Example: `15000` means ৳150.00.
- A user can view their own balance and transaction history at `GET /api/v1/wallet` and `GET /api/v1/wallet/transactions`.
- Only admin/finance staff can record a manual credit or debit through `POST /api/v1/admin/wallet/adjust`. Every adjustment needs a unique reference and a clear description. This endpoint is for verified manual reconciliation, not arbitrary balance creation.
- Members and maintenance staff can request a withdrawal through `POST /api/v1/withdrawals`. The requested amount is reserved immediately, so it cannot be requested twice while pending.
- Users can view only their own withdrawal requests at `GET /api/v1/withdrawals`. Admin/finance staff review the queue at `GET /api/v1/admin/withdrawals`.
- Finance/admin staff reject a request to release the reserved amount, or mark it paid with a payout transaction reference using `POST /api/v1/admin/withdrawals/{id}/process`.
- This is a ledger and request workflow only. It does not connect to bKash, Nagad, a bank, or any payment gateway. A payout reference must be entered only after an actual transfer is independently verified. Do not store full payment account numbers or NID/passport data in this workflow.
- No task reward is automatically credited yet: rewards must not be issued until advertiser funding/escrow and a verified reward-approval process exist. No real money should be collected or promised through this development API.
