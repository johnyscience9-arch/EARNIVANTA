import os
import re
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import Base, User, app, get_db, hash_password, _auth_attempts, totp_code
import app.main as auth_module

_TEST_EMAIL_OUTBOX = []


@pytest.fixture
def client(monkeypatch):
    # Isolate throttles and capture mail without contacting an SMTP server.
    _auth_attempts.clear()
    _TEST_EMAIL_OUTBOX.clear()
    monkeypatch.setattr(auth_module, "smtp_ready", lambda: True)
    monkeypatch.setattr(auth_module, "send_auth_email", lambda recipient, subject, body: _TEST_EMAIL_OUTBOX.append(body))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        db.add(User(
            email="admin@example.com",
            display_name="Test Admin",
            password_hash=hash_password("test-admin-password"),
            role="admin",
        ))
        db.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register(client, email, name):
    response = client.post("/api/v1/auth/register", json={
        "email": email,
        "display_name": name,
        "password": "strong-test-password",
    })
    assert response.status_code == 201, response.text
    assert response.json()["verification_required"] is True
    body = _TEST_EMAIL_OUTBOX[-1]
    token = re.search(r"verify=([A-Za-z0-9_-]+)", body).group(1)
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "strong-test-password"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_campaign_task_and_worker_submission_lifecycle(client):
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "test-admin-password",
    })
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    advertiser_token = register(client, "advertiser@example.com", "Advertiser")
    advertiser_headers = {"Authorization": f"Bearer {advertiser_token}"}
    worker_token = register(client, "worker@example.com", "Worker")
    worker_headers = {"Authorization": f"Bearer {worker_token}"}

    role_response = client.post(
        "/api/v1/admin/users/2/role?role=advertiser",
        headers=admin_headers,
    )
    assert role_response.status_code == 200, role_response.text

    campaign_response = client.post("/api/v1/campaigns", headers=advertiser_headers, json={
        "title": "Product feedback study",
        "objective": "Collect honest usability feedback from eligible participants.",
    })
    assert campaign_response.status_code == 201, campaign_response.text
    campaign_id = campaign_response.json()["id"]

    task_response = client.post(
        f"/api/v1/campaigns/{campaign_id}/tasks",
        headers=advertiser_headers,
        json={
            "title": "Test the product page",
            "instructions": "Visit the page, try the main flow, and write honest feedback.",
            "reward_minor": 5000,
            "capacity": 1,
        },
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["id"]

    seed_funds = client.post("/api/v1/admin/wallet/adjust", headers=admin_headers, json={
        "user_id": 2, "direction": "credit", "amount_minor": 5000,
        "reference": "lifecycle-campaign-fund", "description": "Test-only campaign funding",
    })
    assert seed_funds.status_code == 200, seed_funds.text
    assert client.post(f"/api/v1/campaigns/{campaign_id}/fund", headers=advertiser_headers,
                       json={"amount_minor": 5000}).status_code == 200

    assert client.post(
        f"/api/v1/campaigns/{campaign_id}/submit",
        headers=advertiser_headers,
    ).status_code == 200

    assert client.post(
        f"/api/v1/admin/campaigns/{campaign_id}/review",
        headers=admin_headers,
        json={"decision": "approve"},
    ).status_code == 200

    assert client.post(
        f"/api/v1/campaigns/{campaign_id}/tasks/{task_id}/submit",
        headers=advertiser_headers,
    ).status_code == 200

    assert client.post(
        f"/api/v1/admin/tasks/{task_id}/review",
        headers=admin_headers,
        json={"decision": "approve"},
    ).status_code == 200

    task_feed = client.get("/api/v1/tasks", headers=worker_headers)
    assert task_feed.status_code == 200
    assert any(item["id"] == task_id for item in task_feed.json())

    evidence = {
        "evidence_text": "I tested the product page and completed the main flow. The navigation was clear.",
        "evidence_url": "https://example.test/reference",
    }
    submission = client.post(
        f"/api/v1/tasks/{task_id}/submissions",
        headers=worker_headers,
        json=evidence,
    )
    assert submission.status_code == 201, submission.text
    submission_id = submission.json()["id"]

    duplicate = client.post(
        f"/api/v1/tasks/{task_id}/submissions",
        headers=worker_headers,
        json=evidence,
    )
    assert duplicate.status_code == 409

    second_worker_token = register(client, "second-worker@example.com", "Second Worker")
    second_worker_headers = {"Authorization": f"Bearer {second_worker_token}"}
    capacity_check = client.post(
        f"/api/v1/tasks/{task_id}/submissions",
        headers=second_worker_headers,
        json={"evidence_text": "I completed the task and have provided my feedback."},
    )
    assert capacity_check.status_code == 409
    assert "participant limit" in capacity_check.json()["detail"]

    queue = client.get("/api/v1/admin/submissions", headers=admin_headers)
    assert queue.status_code == 200
    assert any(item["id"] == submission_id for item in queue.json())

    reviewed = client.post(
        f"/api/v1/admin/submissions/{submission_id}/review",
        headers=admin_headers,
        json={"decision": "approve", "reviewer_note": "Evidence checked."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"

    my_submissions = client.get("/api/v1/my/submissions", headers=worker_headers)
    assert my_submissions.status_code == 200
    assert my_submissions.json()[0]["status"] == "approved"



def test_wallet_ledger_and_manual_withdrawal_lifecycle(client):
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "test-admin-password",
    })
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    worker_token = register(client, "wallet-worker@example.com", "Wallet Worker")
    worker_headers = {"Authorization": f"Bearer {worker_token}"}

    initial = client.get("/api/v1/wallet", headers=worker_headers)
    assert initial.status_code == 200
    assert initial.json()["available_minor"] == 0

    credit = client.post("/api/v1/admin/wallet/adjust", headers=admin_headers, json={
        "user_id": 2,
        "direction": "credit",
        "amount_minor": 15000,
        "reference": "manual-credit-0001",
        "description": "Verified pilot reward funding",
    })
    assert credit.status_code == 200, credit.text

    duplicate_reference = client.post("/api/v1/admin/wallet/adjust", headers=admin_headers, json={
        "user_id": 2,
        "direction": "credit",
        "amount_minor": 15000,
        "reference": "manual-credit-0001",
        "description": "Duplicate funding attempt",
    })
    assert duplicate_reference.status_code == 409

    insufficient = client.post("/api/v1/withdrawals", headers=worker_headers, json={"amount_minor": 16000})
    assert insufficient.status_code == 409

    first_request = client.post("/api/v1/withdrawals", headers=worker_headers, json={"amount_minor": 10000})
    assert first_request.status_code == 201, first_request.text
    withdrawal_id = first_request.json()["id"]
    after_hold = client.get("/api/v1/wallet", headers=worker_headers)
    assert after_hold.json()["available_minor"] == 5000

    queue = client.get("/api/v1/admin/withdrawals", headers=admin_headers)
    assert queue.status_code == 200
    assert any(item["id"] == withdrawal_id for item in queue.json())

    rejected = client.post(
        f"/api/v1/admin/withdrawals/{withdrawal_id}/process",
        headers=admin_headers,
        json={"decision": "reject", "staff_note": "Pilot test rejection; reserved funds released."},
    )
    assert rejected.status_code == 200
    after_release = client.get("/api/v1/wallet", headers=worker_headers)
    assert after_release.json()["available_minor"] == 15000

    second_request = client.post("/api/v1/withdrawals", headers=worker_headers, json={"amount_minor": 15000})
    assert second_request.status_code == 201
    paid_id = second_request.json()["id"]
    paid = client.post(
        f"/api/v1/admin/withdrawals/{paid_id}/process",
        headers=admin_headers,
        json={"decision": "pay", "payout_reference": "TEST-PAYOUT-REF-001", "payout_proof_image": "data:image/png;base64,aGVsbG8=", "staff_note": "Test payout only."},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    duplicate_process = client.post(
        f"/api/v1/admin/withdrawals/{paid_id}/process",
        headers=admin_headers,
        json={"decision": "pay", "payout_reference": "TEST-PAYOUT-REF-002"},
    )
    assert duplicate_process.status_code == 409

    final_wallet = client.get("/api/v1/wallet", headers=worker_headers)
    assert final_wallet.status_code == 200
    assert final_wallet.json()["available_minor"] == 0

    ledger = client.get("/api/v1/wallet/transactions", headers=worker_headers)
    assert ledger.status_code == 200
    assert len(ledger.json()) == 4

    own_withdrawals = client.get("/api/v1/withdrawals", headers=worker_headers)
    assert own_withdrawals.status_code == 200
    assert [item["status"] for item in own_withdrawals.json()] == ["paid", "rejected"]


def test_verified_deposit_campaign_escrow_and_reward_credit(client):
    admin_login = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    pricing = client.put("/api/v1/admin/pricing", headers=admin_headers, json={
        "commission_percent": 20, "referral_reward_minor": 700,
        "rates": {"product_feedback": 5000, "website_testing": 5000, "app_testing": 5000,
                  "survey": 5000, "data_labeling": 5000, "ai_evaluation": 5000,
                  "transcription": 5000, "other": 5000},
    })
    assert pricing.status_code == 200, pricing.text
    advertiser_token = register(client, "escrow-advertiser@example.com", "Escrow Advertiser")
    advertiser_headers = {"Authorization": f"Bearer {advertiser_token}"}
    referrer_token = register(client, "referrer@example.com", "Referrer")
    referrer_headers = {"Authorization": f"Bearer {referrer_token}"}
    referrer_code = client.get("/api/v1/me", headers=referrer_headers).json()["referral_code"]
    referred = client.post("/api/v1/auth/register", json={
        "email": "escrow-worker@example.com", "display_name": "Escrow Worker",
        "password": "strong-test-password", "referral_code": referrer_code,
    })
    assert referred.status_code == 201, referred.text
    worker_headers = {"Authorization": f"Bearer {referred.json()['access_token']}"} 
    assert client.post("/api/v1/admin/users/2/role?role=advertiser", headers=admin_headers).status_code == 200
    deposit = client.post("/api/v1/deposits", headers=advertiser_headers, json={
        "amount_minor": 12000, "method": "bkash", "payment_reference": "BKASH-VERIFY-12345"
    })
    assert deposit.status_code == 201, deposit.text
    assert client.get("/api/v1/wallet", headers=advertiser_headers).json()["available_minor"] == 0
    duplicate = client.post("/api/v1/deposits", headers=advertiser_headers, json={
        "amount_minor": 12000, "method": "bkash", "payment_reference": "BKASH-VERIFY-12345"
    })
    assert duplicate.status_code == 409
    verified = client.post(f"/api/v1/admin/deposits/{deposit.json()['id']}/review", headers=admin_headers, json={"decision": "verify"})
    assert verified.status_code == 200, verified.text
    assert client.get("/api/v1/wallet", headers=advertiser_headers).json()["available_minor"] == 12000
    campaign = client.post("/api/v1/campaigns", headers=advertiser_headers, json={
        "title": "Usability pilot", "objective": "Collect genuine feedback on a small business website."
    })
    campaign_id = campaign.json()["id"]
    task = client.post(f"/api/v1/campaigns/{campaign_id}/tasks", headers=advertiser_headers, json={
        "title": "Review the website", "instructions": "Explore the website and provide honest written feedback.",
        "category": "product_feedback", "capacity": 1
    })
    task_id = task.json()["id"]
    assert client.post(f"/api/v1/campaigns/{campaign_id}/fund", headers=advertiser_headers, json={"amount_minor": 6000}).status_code == 200
    assert client.get("/api/v1/wallet", headers=advertiser_headers).json()["available_minor"] == 6000
    assert client.post(f"/api/v1/campaigns/{campaign_id}/submit", headers=advertiser_headers).status_code == 200
    assert client.post(f"/api/v1/admin/campaigns/{campaign_id}/review", headers=admin_headers, json={"decision": "approve"}).status_code == 200
    assert client.post(f"/api/v1/campaigns/{campaign_id}/tasks/{task_id}/submit", headers=advertiser_headers).status_code == 200
    assert client.post(f"/api/v1/admin/tasks/{task_id}/review", headers=admin_headers, json={"decision": "approve"}).status_code == 200
    evidence = client.post(f"/api/v1/tasks/{task_id}/submissions", headers=worker_headers, json={
        "evidence_text": "I tested the main flow and submitted genuine feedback about the navigation."
    })
    assert evidence.status_code == 201, evidence.text
    submission_id = evidence.json()["id"]
    paid = client.post(f"/api/v1/admin/submissions/{submission_id}/review", headers=admin_headers, json={"decision": "approve"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["reward_credited_minor"] == 5000
    referral_result = client.get("/api/v1/referrals", headers=referrer_headers)
    assert referral_result.status_code == 200
    assert referral_result.json()["credited"] == 1
    assert referral_result.json()["earned_minor"] == 700
    assert client.get("/api/v1/wallet", headers=worker_headers).json()["available_minor"] == 5000
    budget = client.get(f"/api/v1/campaigns/{campaign_id}/budget", headers=advertiser_headers)
    assert budget.json()["escrow_balance_minor"] == 0
    assert budget.json()["spent_minor"] == 6000
    repeated = client.post(f"/api/v1/admin/submissions/{submission_id}/review", headers=admin_headers, json={"decision": "approve"})
    assert repeated.status_code == 409


def test_admin_user_directory_and_role_management(client):
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com", "password": "test-admin-password"
    })
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    member_token = register(client, "role-target@example.com", "Role Target")
    member_headers = {"Authorization": f"Bearer {member_token}"}

    denied = client.get("/api/v1/admin/users", headers=member_headers)
    assert denied.status_code == 403

    listed = client.get("/api/v1/admin/users", headers=admin_headers)
    assert listed.status_code == 200
    target = next(item for item in listed.json() if item["email"] == "role-target@example.com")
    assert target["role"] == "member"
    assert "password_hash" not in target

    changed = client.post(
        f"/api/v1/admin/users/{target['id']}/role?role=maintenance",
        headers=admin_headers,
    )
    assert changed.status_code == 200
    refreshed = client.get("/api/v1/admin/users", headers=admin_headers)
    updated = next(item for item in refreshed.json() if item["id"] == target["id"])
    assert updated["role"] == "maintenance"


def test_production_requires_explicit_secret_and_postgres():
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env.pop("TOKEN_SECRET", None)
    env.pop("DATABASE_URL", None)
    missing_secret = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert missing_secret.returncode != 0
    assert "TOKEN_SECRET is required in production" in missing_secret.stderr

    env["TOKEN_SECRET"] = "x" * 48
    env["DATABASE_URL"] = "sqlite:///./not-for-production.db"
    sqlite_blocked = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert sqlite_blocked.returncode != 0
    assert "SQLite is not allowed in production" in sqlite_blocked.stderr


def test_production_rejects_insecure_cors_origins():
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["TOKEN_SECRET"] = "x" * 48
    env["DATABASE_URL"] = "postgresql+psycopg://user:password@localhost:5432/earnivanta"
    env["CORS_ORIGINS"] = "*"
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "exact HTTPS frontend origin" in result.stderr



def test_email_verification_password_reset_and_session_revocation(client):
    blocked = client.post("/api/v1/auth/register", json={
        "email": "reset-user@example.com", "display_name": "Reset User",
        "password": "strong-test-password"
    })
    assert blocked.status_code == 201
    body = _TEST_EMAIL_OUTBOX[-1]
    verify_token = re.search(r"verify=([A-Za-z0-9_-]+)", body).group(1)
    unverified_login = client.post("/api/v1/auth/login", json={
        "email": "reset-user@example.com", "password": "strong-test-password"
    })
    assert unverified_login.status_code == 403
    assert client.post("/api/v1/auth/verify-email", json={"token": verify_token}).status_code == 200
    assert client.post("/api/v1/auth/verify-email", json={"token": verify_token}).status_code == 400

    login = client.post("/api/v1/auth/login", json={
        "email": "reset-user@example.com", "password": "strong-test-password"
    })
    old_token = login.json()["access_token"]
    assert client.post("/api/v1/auth/forgot-password", json={"email": "reset-user@example.com"}).status_code == 200
    reset_body = _TEST_EMAIL_OUTBOX[-1]
    reset_token = re.search(r"reset=([A-Za-z0-9_-]+)", reset_body).group(1)
    reset = client.post("/api/v1/auth/reset-password", json={
        "token": reset_token, "password": "a-different-strong-password"
    })
    assert reset.status_code == 200
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.post("/api/v1/auth/reset-password", json={
        "token": reset_token, "password": "another-strong-password"
    }).status_code == 400
    assert client.post("/api/v1/auth/login", json={
        "email": "reset-user@example.com", "password": "a-different-strong-password"
    }).status_code == 200


def test_admin_totp_mfa_enrollment_and_login_challenge(client):
    login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com", "password": "test-admin-password"
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = totp_code(secret)
    enabled = client.post("/api/v1/auth/mfa/enable", headers=headers, json={"code": code})
    assert enabled.status_code == 200
    challenge = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com", "password": "test-admin-password"
    })
    assert challenge.status_code == 200 and challenge.json()["mfa_required"] is True
    verified = client.post("/api/v1/auth/mfa/verify", json={
        "challenge_token": challenge.json()["challenge_token"], "code": totp_code(secret)
    })
    assert verified.status_code == 200 and verified.json().get("access_token")
