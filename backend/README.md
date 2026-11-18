# Earnivanta API — development foundation

## Included in this milestone

- FastAPI application and health endpoint.
- Member registration and login with PBKDF2-HMAC-SHA256 password hashes.
- Signed, expiring bearer tokens.
- Role-protected advertiser campaign and draft-task creation.
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

## Important deployment requirements

- Replace `TOKEN_SECRET` with a cryptographically random secret. The fallback secret is local-development-only.
- Set `CORS_ORIGINS` to the exact deployed frontend origin(s), not `*` when credentials are enabled.
- Set a strong `ADMIN_PASSWORD` only during initial bootstrap, then remove it from the deployment environment.
- SQLite is for local development/single-instance testing. Use managed PostgreSQL for a multi-instance production deployment and configure backups.
- This milestone is not production-ready: rate limiting, email verification, password reset, refresh/revocation, audit logging, migrations, CSRF strategy, monitoring and automated tests remain required.
- No real payments, wallet credits, identity document uploads, KYC, withdrawal payout or live chat are implemented. Do not collect NID/passport images or real money through this API yet.
