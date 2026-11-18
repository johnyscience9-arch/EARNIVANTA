# Earnivanta — free-first deployment

## What is already online

The static frontend is published through GitHub Pages:
- https://johnyscience9-arch.github.io/EARNIVANTA/
- https://johnyscience9-arch.github.io/EARNIVANTA/portal.html

The FastAPI backend is a separate service. It is not live until a hosting provider and persistent PostgreSQL database are connected.

## Deploy the API with the included blueprint

1. Create a free account with a compatible Python hosting provider and connect the GitHub repository `johnyscience9-arch/EARNIVANTA`.
2. Select the repository blueprint file `render.yaml` (Render Blueprint flow).
3. The blueprint creates the API web service. Add a persistent PostgreSQL connection URL as `DATABASE_URL`; use a managed database provider such as Supabase PostgreSQL and copy its connection string privately.
4. Keep the generated `TOKEN_SECRET`. Do not paste it into GitHub files, public chat, or the frontend.
5. Set `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` only for the first administrator bootstrap. After the first successful admin login, remove `ADMIN_PASSWORD` from the host environment and redeploy.
6. Keep `APP_ENV=production`, `CORS_ORIGINS=https://johnyscience9-arch.github.io`, and `TOKEN_TTL_HOURS=24`.
7. Wait for the service health check to pass at `https://YOUR-API-HOST/api/v1/health`.
8. Open the portal, enter the API HTTPS base URL (without a trailing slash), and save the connection in that browser.

Free hosting/database limits and retention policies change. Check the provider's current terms and never assume a free plan is permanent or suitable for financial records. A sleeping free web service may take time to wake up. Use a persistent PostgreSQL database; do not use SQLite on an ephemeral host disk.

## Production safety gates

The API now refuses to start in production if:
- `TOKEN_SECRET` is missing or shorter than 32 characters;
- SQLite is selected;
- `CORS_ORIGINS` is wildcard, missing, or not HTTPS.

The deployment still requires an independent security and legal review before real users or money. Rate limiting, email verification, password reset, token revocation, audit logs, formal database migrations, monitoring, backup/restore drills, support/dispute processes, real payment reconciliation and payout operations are not yet implemented. There is no bKash/Nagad gateway or automatic payment verification. Do not accept real deposits, joining fees, identity documents or promise earnings through this development system.

## Local development

From the repository's `backend` folder:
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

## Campaign integrity

Only support lawful work with real value: voluntary research, honest product testing, disclosed content, consent-based leads and genuine feedback. Do not publish fake likes, follows, views, subscribers, fabricated reviews or deceptive platform manipulation.
