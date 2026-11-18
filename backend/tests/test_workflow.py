import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import Base, User, app, get_db, hash_password


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        db.add(User(
            email="admin@example.test",
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
    return response.json()["access_token"]


def test_campaign_task_and_worker_submission_lifecycle(client):
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@example.test",
        "password": "test-admin-password",
    })
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    advertiser_token = register(client, "advertiser@example.test", "Advertiser")
    advertiser_headers = {"Authorization": f"Bearer {advertiser_token}"}
    worker_token = register(client, "worker@example.test", "Worker")
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
