import os
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./earnivanta.db")
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))
if not TOKEN_SECRET:
    TOKEN_SECRET = "LOCAL-ONLY-" + secrets.token_urlsafe(32)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(24), default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    objective: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    instructions: Mapped[str] = mapped_column(String(2000))
    reward_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="BDT")
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$" + b64(salt) + "$" + b64(derived)


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_text, digest_text = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64(json.dumps({
        "sub": str(user.id), "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())
    }, separators=(",", ":")).encode())
    signing_input = header + "." + payload
    signature = b64(hmac.new(TOKEN_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
    return signing_input + "." + signature


def decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        signing_input = header + "." + payload
        expected = b64(hmac.new(TOKEN_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(claims["exp"]) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        return claims
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


bearer = HTTPBearer(auto_error=False)


def current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Sign-in required")
    claims = decode_token(credentials.credentials)
    user = db.get(User, int(claims["sub"]))
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return user
    return checker


class RegisterInput(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=128)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CampaignInput(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    objective: str = Field(min_length=10, max_length=500)


class TaskInput(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    instructions: str = Field(min_length=10, max_length=2000)
    reward_minor: int = Field(ge=0, le=100_000_000)
    capacity: int = Field(ge=1, le=100_000)


app = FastAPI(title="Earnivanta API", version="0.1.0", description="Initial authentication and campaign foundation.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


@app.get("/api/v1/health")
def health():
    return {"ok": True, "service": "earnivanta-api", "version": "0.1.0"}


@app.post("/api/v1/auth/register", status_code=201)
def register(data: RegisterInput, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password), role="member")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_public(user)}


@app.post("/api/v1/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(data.password, user.password_hash) or not user.active:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_public(user)}


def user_public(user: User):
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "active": user.active}


@app.get("/api/v1/me")
def me(user: User = Depends(current_user)):
    return user_public(user)


@app.post("/api/v1/campaigns", status_code=201)
def create_campaign(data: CampaignInput, user: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    campaign = Campaign(advertiser_id=user.id, title=data.title.strip(), objective=data.objective.strip())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {"id": campaign.id, "title": campaign.title, "objective": campaign.objective, "status": campaign.status}


@app.get("/api/v1/campaigns")
def list_campaigns(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Campaign).order_by(Campaign.id.desc())
    if user.role != "admin":
        query = query.where(Campaign.advertiser_id == user.id)
    campaigns = db.scalars(query).all()
    return [{"id": c.id, "title": c.title, "objective": c.objective, "status": c.status} for c in campaigns]


@app.post("/api/v1/campaigns/{campaign_id}/tasks", status_code=201)
def create_task(campaign_id: int, data: TaskInput, user: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or (user.role != "admin" and campaign.advertiser_id != user.id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="Tasks can only be added while campaign is a draft")
    task = Task(campaign_id=campaign.id, title=data.title.strip(), instructions=data.instructions.strip(), reward_minor=data.reward_minor, capacity=data.capacity)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "campaign_id": task.campaign_id, "title": task.title, "status": task.status}


@app.get("/api/v1/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Task, Campaign).join(Campaign, Task.campaign_id == Campaign.id)
                      .where(Task.status == "published", Campaign.status == "active").order_by(Task.id.desc())).all()
    return [{"id": t.id, "campaign_id": t.campaign_id, "title": t.title, "instructions": t.instructions,
             "reward_minor": t.reward_minor, "currency": t.currency, "capacity": t.capacity} for t, _ in rows]


@app.post("/api/v1/admin/users/{user_id}/role")
def change_role(user_id: int, role: str, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    allowed = {"member", "advertiser", "maintenance", "reviewer", "kyc_reviewer", "finance"}
    if role not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported role")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = role
    db.commit()
    return {"user_id": target.id, "role": target.role, "changed_by": admin.id}


admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
admin_password = os.getenv("ADMIN_PASSWORD", "")
if admin_email and admin_password:
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == admin_email))
        if not existing:
            db.add(User(email=admin_email, display_name="Earnivanta Admin", password_hash=hash_password(admin_password), role="admin"))
            db.commit()


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


@app.post("/api/v1/campaigns/{campaign_id}/submit")
def submit_campaign(campaign_id: int, user: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or (user.role != "admin" and campaign.advertiser_id != user.id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft campaigns can be submitted")
    if not db.scalar(select(Task.id).where(Task.campaign_id == campaign.id)):
        raise HTTPException(status_code=409, detail="Add at least one task before submitting")
    campaign.status = "pending_review"
    db.commit()
    return {"id": campaign.id, "status": campaign.status, "message": "Campaign submitted for review"}


@app.post("/api/v1/admin/campaigns/{campaign_id}/review")
def review_campaign(campaign_id: int, data: ReviewDecision, admin: User = Depends(require_roles("admin", "reviewer")), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "pending_review":
        raise HTTPException(status_code=409, detail="Campaign is not waiting for review")
    campaign.status = "active" if data.decision == "approve" else "rejected"
    db.commit()
    return {"id": campaign.id, "status": campaign.status, "reviewed_by": admin.id}


@app.post("/api/v1/campaigns/{campaign_id}/tasks/{task_id}/submit")
def submit_task(campaign_id: int, task_id: int, user: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    task = db.get(Task, task_id)
    if not campaign or not task or task.campaign_id != campaign_id or (user.role != "admin" and campaign.advertiser_id != user.id):
        raise HTTPException(status_code=404, detail="Task not found")
    if campaign.status not in {"draft", "active"} or task.status != "draft":
        raise HTTPException(status_code=409, detail="Task cannot be submitted in its current state")
    task.status = "pending_review"
    db.commit()
    return {"id": task.id, "status": task.status, "message": "Task submitted for review"}


@app.post("/api/v1/admin/tasks/{task_id}/review")
def review_task(task_id: int, data: ReviewDecision, admin: User = Depends(require_roles("admin", "reviewer")), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "pending_review":
        raise HTTPException(status_code=409, detail="Task is not waiting for review")
    campaign = db.get(Campaign, task.campaign_id)
    if data.decision == "approve" and campaign.status != "active":
        raise HTTPException(status_code=409, detail="Campaign must be approved before its tasks")
    task.status = "published" if data.decision == "approve" else "rejected"
    db.commit()
    return {"id": task.id, "status": task.status, "reviewed_by": admin.id}
