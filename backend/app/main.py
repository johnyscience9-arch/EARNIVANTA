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
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./earnivanta.db").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))
if TOKEN_TTL_HOURS < 1 or TOKEN_TTL_HOURS > 720:
    raise RuntimeError("TOKEN_TTL_HOURS must be between 1 and 720")
if not TOKEN_SECRET:
    if APP_ENV == "production":
        raise RuntimeError("TOKEN_SECRET is required in production")
    TOKEN_SECRET = "LOCAL-ONLY-" + secrets.token_urlsafe(32)
if APP_ENV == "production":
    if len(TOKEN_SECRET) < 32:
        raise RuntimeError("TOKEN_SECRET must contain at least 32 characters in production")
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("SQLite is not allowed in production; configure managed PostgreSQL")
cors_value = os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
origins = [x.strip().rstrip("/") for x in cors_value.split(",") if x.strip()]
if APP_ENV == "production":
    if not origins or any(origin == "*" for origin in origins):
        raise RuntimeError("Set CORS_ORIGINS to the exact HTTPS frontend origin(s) in production")
    if any(not origin.startswith("https://") for origin in origins):
        raise RuntimeError("Production CORS_ORIGINS must contain HTTPS origins only")

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
    referral_code: Mapped[Optional[str]] = mapped_column(String(16), unique=True, index=True, nullable=True)
    referred_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    objective: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    escrow_balance_minor: Mapped[int] = mapped_column(Integer, default=0)
    spent_minor: Mapped[int] = mapped_column(Integer, default=0)
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
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    category: Mapped[str] = mapped_column(String(32), default="other")
    client_charge_minor: Mapped[int] = mapped_column(Integer, default=0)


class TaskSubmission(Base):
    __tablename__ = "task_submissions"
    __table_args__ = (UniqueConstraint("task_id", "worker_id", name="uq_task_worker_submission"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    evidence_text: Mapped[str] = mapped_column(String(3000))
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_review")
    reviewer_note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class WalletEntry(Base):
    __tablename__ = "wallet_entries"
    __table_args__ = (UniqueConstraint("reference", name="uq_wallet_entry_reference"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="BDT")
    reference: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DepositRequest(Base):
    __tablename__ = "deposit_requests"
    __table_args__ = (UniqueConstraint("payment_reference", name="uq_deposit_payment_reference"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(24))
    payment_destination_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payment_reference: Mapped[str] = mapped_column(String(120))
    proof_image_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_review")
    staff_note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)



class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    reward_minor: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    credited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PricingSettings(Base):
    __tablename__ = "pricing_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    commission_percent: Mapped[int] = mapped_column(Integer, default=20)
    referral_reward_minor: Mapped[int] = mapped_column(Integer, default=500)
    rates_json: Mapped[str] = mapped_column(Text, default='{"product_feedback":1500,"website_testing":2000,"app_testing":2500,"survey":1000,"data_labeling":1200,"ai_evaluation":1800,"transcription":2000,"other":1000}')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DailyHeadline(Base):
    __tablename__ = "daily_headlines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    headline: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(String(1000), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="BDT")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    payout_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    payout_proof_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    staff_note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentDestination(Base):
    __tablename__ = "payment_destinations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    method: Mapped[str] = mapped_column(String(24), index=True)
    label: Mapped[str] = mapped_column(String(80))
    account_type: Mapped[str] = mapped_column(String(24), default="Personal")
    account_number: Mapped[str] = mapped_column(String(40))
    instructions: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DailyHeadlineInput(BaseModel):
    headline: str = Field(min_length=3, max_length=180)
    body: str = Field(default="", max_length=1000)

class TaskPinInput(BaseModel):
    pinned: bool


Base.metadata.create_all(bind=engine)
from sqlalchemy import inspect, text
if "payment_destination_id" not in {c["name"] for c in inspect(engine).get_columns("deposit_requests")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE deposit_requests ADD COLUMN payment_destination_id INTEGER"))
if "proof_image_data" not in {c["name"] for c in inspect(engine).get_columns("deposit_requests")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE deposit_requests ADD COLUMN proof_image_data TEXT"))
if "referral_code" not in {c["name"] for c in inspect(engine).get_columns("users")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR(16)"))
if "referred_by_id" not in {c["name"] for c in inspect(engine).get_columns("users")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN referred_by_id INTEGER"))
if "pinned" not in {c["name"] for c in inspect(engine).get_columns("tasks")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT FALSE"))
if "category" not in {c["name"] for c in inspect(engine).get_columns("tasks")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'other'"))
if "client_charge_minor" not in {c["name"] for c in inspect(engine).get_columns("tasks")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN client_charge_minor INTEGER NOT NULL DEFAULT 0"))

if "payout_proof_image" not in {c["name"] for c in inspect(engine).get_columns("withdrawals")}:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE withdrawals ADD COLUMN payout_proof_image TEXT"))


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
    referral_code: Optional[str] = Field(default=None, min_length=4, max_length=16)
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
    category: str = Field(default="other", pattern="^(product_feedback|website_testing|app_testing|survey|data_labeling|ai_evaluation|transcription|other)$")
    title: str = Field(min_length=3, max_length=140)
    instructions: str = Field(min_length=10, max_length=2000)
    capacity: int = Field(ge=1, le=100_000)


class PaymentDestinationInput(BaseModel):
    method: str = Field(min_length=2, max_length=24)
    label: str = Field(min_length=2, max_length=80)
    account_type: str = Field(default="Personal", min_length=2, max_length=24)
    account_number: str = Field(min_length=5, max_length=40)
    instructions: Optional[str] = Field(default=None, max_length=500)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)


class PaymentDestinationUpdate(BaseModel):
    method: Optional[str] = Field(default=None, min_length=2, max_length=24)
    label: Optional[str] = Field(default=None, min_length=2, max_length=80)
    account_type: Optional[str] = Field(default=None, min_length=2, max_length=24)
    account_number: Optional[str] = Field(default=None, min_length=5, max_length=40)
    instructions: Optional[str] = Field(default=None, max_length=500)
    active: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0, le=10000)


def payment_destination_public(item: PaymentDestination):
    return {"id": item.id, "method": item.method, "label": item.label,
            "account_type": item.account_type, "account_number": item.account_number,
            "instructions": item.instructions, "active": item.active, "sort_order": item.sort_order}


app = FastAPI(title="Earnivanta API", version="0.1.0", description="Initial authentication and campaign foundation.")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])




TASK_RATE_DEFAULTS = {"product_feedback":1500,"website_testing":2000,"app_testing":2500,"survey":1000,"data_labeling":1200,"ai_evaluation":1800,"transcription":2000,"other":1000}
class PricingSettingsInput(BaseModel):
    commission_percent: int = Field(ge=0, le=200)
    referral_reward_minor: int = Field(ge=0, le=10000000)
    rates: dict[str, int]

@app.get("/api/v1/pricing")
def get_pricing(db: Session = Depends(get_db)):
    item = db.get(PricingSettings, 1)
    rates = json.loads(item.rates_json) if item else TASK_RATE_DEFAULTS
    return {"rates": rates, "commission_percent": item.commission_percent if item else 20, "referral_reward_minor": item.referral_reward_minor if item else 500}

@app.put("/api/v1/admin/pricing")
def update_pricing(data: PricingSettingsInput, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    if set(data.rates) != set(TASK_RATE_DEFAULTS) or any(v < 0 or v > 10000000 for v in data.rates.values()):
        raise HTTPException(status_code=422, detail="Provide valid BDT worker rates for every supported task category")
    item = db.get(PricingSettings, 1)
    if not item:
        item = PricingSettings(id=1)
        db.add(item)
    item.commission_percent = data.commission_percent
    item.referral_reward_minor = data.referral_reward_minor
    item.rates_json = json.dumps(data.rates, separators=(",", ":"))
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"rates": data.rates, "commission_percent": item.commission_percent, "referral_reward_minor": item.referral_reward_minor}



@app.get("/api/v1/referrals")
def my_referrals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Referral).where(Referral.referrer_id == user.id).order_by(Referral.id.desc())).all()
    settings = db.get(PricingSettings, 1)
    return {"referral_code": user.referral_code, "reward_minor": settings.referral_reward_minor if settings else 500,
            "total": len(rows), "credited": sum(1 for r in rows if r.status == "credited"),
            "earned_minor": sum(r.reward_minor for r in rows if r.status == "credited"),
            "referrals": [{"id": r.id, "status": r.status, "reward_minor": r.reward_minor,
                           "created_at": r.created_at.isoformat()} for r in rows]}

@app.get("/api/v1/health")
def health():
    return {"ok": True, "service": "earnivanta-api", "version": "0.1.0"}


@app.get("/api/v1/daily-headline")
def get_daily_headline(db: Session = Depends(get_db)):
    item = db.get(DailyHeadline, 1)
    if not item:
        return {"headline": "Welcome to Earnivanta", "body": "Check today’s verified opportunities and follow each task instruction carefully."}
    return {"headline": item.headline, "body": item.body, "updated_at": item.updated_at.isoformat()}

@app.put("/api/v1/admin/daily-headline")
def set_daily_headline(data: DailyHeadlineInput, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    item = db.get(DailyHeadline, 1)
    if not item:
        item = DailyHeadline(id=1, headline=data.headline.strip(), body=data.body.strip(), updated_at=datetime.now(timezone.utc))
        db.add(item)
    else:
        item.headline = data.headline.strip()
        item.body = data.body.strip()
        item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"headline": item.headline, "body": item.body, "updated_at": item.updated_at.isoformat()}

@app.get("/api/v1/payment-destinations")
def public_payment_destinations(db: Session = Depends(get_db)):
    items = db.scalars(select(PaymentDestination).where(PaymentDestination.active == True)
                       .order_by(PaymentDestination.sort_order.asc(), PaymentDestination.id.asc())).all()
    return [payment_destination_public(item) for item in items]


@app.get("/api/v1/admin/payment-destinations")
def admin_payment_destinations(admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    items = db.scalars(select(PaymentDestination).order_by(PaymentDestination.id.desc())).all()
    return [payment_destination_public(item) for item in items]


@app.post("/api/v1/admin/payment-destinations", status_code=201)
def add_payment_destination(data: PaymentDestinationInput, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    item = PaymentDestination(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return payment_destination_public(item)


@app.patch("/api/v1/admin/payment-destinations/{destination_id}")
def edit_payment_destination(destination_id: int, data: PaymentDestinationUpdate, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    item = db.get(PaymentDestination, destination_id)
    if not item:
        raise HTTPException(status_code=404, detail="Payment destination not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return payment_destination_public(item)


@app.delete("/api/v1/admin/payment-destinations/{destination_id}")
def disable_payment_destination(destination_id: int, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    item = db.get(PaymentDestination, destination_id)
    if not item:
        raise HTTPException(status_code=404, detail="Payment destination not found")
    item.active = False
    db.commit()
    return {"id": item.id, "active": False, "message": "Payment destination disabled"}


@app.post("/api/v1/auth/register", status_code=201)
def register(data: RegisterInput, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    referrer = None
    if data.referral_code:
        referrer = db.scalar(select(User).where(User.referral_code == data.referral_code.strip().upper(), User.active == True))
        if not referrer:
            raise HTTPException(status_code=422, detail="Referral code is invalid")
    user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password), role="member",
                referral_code=secrets.token_hex(4).upper(), referred_by_id=(referrer.id if referrer else None))
    db.add(user)
    db.commit()
    db.refresh(user)
    if referrer:
        db.add(Referral(referrer_id=referrer.id, referred_user_id=user.id, status="pending"))
        db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_public(user)}


@app.post("/api/v1/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(data.password, user.password_hash) or not user.active:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_public(user)}


def user_public(user: User):
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role, "active": user.active, "referral_code": user.referral_code}


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
    if user.role not in {"admin", "reviewer", "finance"}:
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
    pricing = db.get(PricingSettings, 1)
    if not pricing:
        pricing = PricingSettings(id=1)
        db.add(pricing)
        db.flush()
    rates = json.loads(pricing.rates_json)
    worker_reward = int(rates.get(data.category, rates.get("other", 1000)))
    commission = max(0, min(200, int(pricing.commission_percent)))
    client_charge = worker_reward + (worker_reward * commission + 99) // 100
    task = Task(campaign_id=campaign.id, title=data.title.strip(), instructions=data.instructions.strip(), reward_minor=worker_reward, client_charge_minor=client_charge, category=data.category, capacity=data.capacity)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "campaign_id": task.campaign_id, "title": task.title, "category": task.category, "worker_reward_minor": task.reward_minor, "client_charge_minor": task.client_charge_minor, "commission_percent": commission, "status": task.status}


@app.get("/api/v1/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Task, Campaign).join(Campaign, Task.campaign_id == Campaign.id)
                      .where(Task.status == "published", Campaign.status == "active").order_by(Task.pinned.desc(), Task.id.desc())).all()
    return [{"id": t.id, "campaign_id": t.campaign_id, "title": t.title, "instructions": t.instructions,
             "reward_minor": t.reward_minor, "currency": t.currency, "capacity": t.capacity, "pinned": t.pinned} for t, _ in rows]


@app.get("/api/v1/admin/tasks")
def admin_list_tasks(admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Task).order_by(Task.id.desc())).all()
    return [{"id": t.id, "title": t.title, "status": t.status, "pinned": t.pinned} for t in rows]

@app.patch("/api/v1/admin/tasks/{task_id}/pin")
def pin_task(task_id: int, data: TaskPinInput, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.pinned = data.pinned
    db.commit()
    return {"id": task.id, "pinned": task.pinned}

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

@app.get("/api/v1/admin/users")
def list_users(admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id.asc())).all()
    return [{"id": u.id, "email": u.email, "display_name": u.display_name,
             "role": u.role, "active": u.active,
             "created_at": u.created_at.isoformat()} for u in users]


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


@app.get("/api/v1/admin/review-queue")
def review_queue(staff: User = Depends(require_roles("admin", "reviewer")), db: Session = Depends(get_db)):
    campaigns = db.scalars(select(Campaign).where(Campaign.status == "pending_review").order_by(Campaign.id.asc())).all()
    tasks = db.execute(select(Task, Campaign).join(Campaign, Task.campaign_id == Campaign.id)
                       .where(Task.status == "pending_review").order_by(Task.id.asc())).all()
    return {
        "campaigns": [{"id": c.id, "advertiser_id": c.advertiser_id, "title": c.title, "objective": c.objective, "status": c.status} for c in campaigns],
        "tasks": [{"id": t.id, "campaign_id": t.campaign_id, "campaign_title": campaign.title, "title": t.title,
                   "instructions": t.instructions, "reward_minor": t.reward_minor, "currency": t.currency,
                   "capacity": t.capacity, "status": t.status} for t, campaign in tasks]
    }


class SubmissionInput(BaseModel):
    evidence_text: str = Field(min_length=10, max_length=3000)
    evidence_url: Optional[str] = Field(default=None, max_length=500)


class SubmissionReviewInput(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reviewer_note: Optional[str] = Field(default=None, max_length=1000)


@app.post("/api/v1/tasks/{task_id}/submissions", status_code=201)
def create_submission(task_id: int, data: SubmissionInput, worker: User = Depends(require_roles("member", "maintenance")), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task or task.status != "published":
        raise HTTPException(status_code=404, detail="Available task not found")
    campaign = db.get(Campaign, task.campaign_id)
    if not campaign or campaign.status != "active":
        raise HTTPException(status_code=409, detail="Campaign is not active")
    existing = db.scalar(select(TaskSubmission).where(TaskSubmission.task_id == task.id, TaskSubmission.worker_id == worker.id))
    if existing:
        raise HTTPException(status_code=409, detail="You have already submitted this task")
    used_slots = db.scalar(select(func.count(TaskSubmission.id)).where(
        TaskSubmission.task_id == task.id,
        TaskSubmission.status.in_(["pending_review", "approved"])
    )) or 0
    if used_slots >= task.capacity:
        raise HTTPException(status_code=409, detail="This task has reached its participant limit")
    submission = TaskSubmission(task_id=task.id, worker_id=worker.id,
                                evidence_text=data.evidence_text.strip(),
                                evidence_url=(str(data.evidence_url).strip() if data.evidence_url else None))
    db.add(submission)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Submission could not be saved; check whether you already submitted")
    db.refresh(submission)
    return {"id": submission.id, "task_id": task.id, "status": submission.status, "message": "Evidence submitted for review"}


@app.get("/api/v1/my/submissions")
def my_submissions(worker: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(TaskSubmission, Task).join(Task, TaskSubmission.task_id == Task.id)
                      .where(TaskSubmission.worker_id == worker.id).order_by(TaskSubmission.id.desc())).all()
    return [{"id": s.id, "task_id": t.id, "task_title": t.title, "status": s.status,
             "reviewer_note": s.reviewer_note, "created_at": s.created_at.isoformat()} for s, t in rows]


@app.get("/api/v1/admin/submissions")
def list_submissions(staff: User = Depends(require_roles("admin", "reviewer")), db: Session = Depends(get_db)):
    rows = db.execute(select(TaskSubmission, Task, User)
                      .join(Task, TaskSubmission.task_id == Task.id)
                      .join(User, TaskSubmission.worker_id == User.id)
                      .where(TaskSubmission.status == "pending_review")
                      .order_by(TaskSubmission.id.asc())).all()
    return [{"id": s.id, "task_id": t.id, "task_title": t.title, "worker_id": u.id,
             "worker_name": u.display_name, "evidence_text": s.evidence_text, "evidence_url": s.evidence_url,
             "submitted_at": s.created_at.isoformat()} for s, t, u in rows]


@app.post("/api/v1/admin/submissions/{submission_id}/review")
def review_submission(submission_id: int, data: SubmissionReviewInput,
                      staff: User = Depends(require_roles("admin", "reviewer")), db: Session = Depends(get_db)):
    submission = db.get(TaskSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status != "pending_review":
        raise HTTPException(status_code=409, detail="Submission has already been reviewed")
    if data.decision == "approve":
        task = db.scalar(select(Task).where(Task.id == submission.task_id).with_for_update())
        campaign = db.scalar(select(Campaign).where(Campaign.id == task.campaign_id).with_for_update())
        if campaign.escrow_balance_minor < (task.client_charge_minor or task.reward_minor):
            raise HTTPException(status_code=409, detail="Campaign escrow has insufficient funds; submission remains pending")
        worker = db.scalar(select(User).where(User.id == submission.worker_id).with_for_update())
        campaign.escrow_balance_minor -= (task.client_charge_minor or task.reward_minor)
        campaign.spent_minor += (task.client_charge_minor or task.reward_minor)
        if task.reward_minor:
            db.add(WalletEntry(user_id=worker.id, entry_type="credit", amount_minor=task.reward_minor,
                reference=f"task-submission:{submission.id}:reward",
                description=f"Approved reward for task submission #{submission.id}", created_by=staff.id))

        referral = db.scalar(select(Referral).where(Referral.referred_user_id == worker.id, Referral.status == "pending").with_for_update())
        if referral:
            settings = db.get(PricingSettings, 1)
            referral_reward = int(settings.referral_reward_minor if settings else 500)
            referrer = db.scalar(select(User).where(User.id == referral.referrer_id).with_for_update())
            if referrer and referrer.active and referral_reward > 0:
                referral.reward_minor = referral_reward
                referral.status = "credited"
                referral.credited_at = datetime.now(timezone.utc)
                db.add(WalletEntry(user_id=referrer.id, entry_type="credit", amount_minor=referral_reward,
                    reference=f"referral:{referral.id}:reward",
                    description=f"Verified referral reward for member #{worker.id}", created_by=staff.id))
            else:
                referral.status = "ineligible"
    submission.status = "approved" if data.decision == "approve" else "rejected"
    submission.reviewer_note = data.reviewer_note.strip() if data.reviewer_note else None
    submission.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": submission.id, "status": submission.status, "reviewed_by": staff.id,
            "reward_credited_minor": task.reward_minor if data.decision == "approve" else 0,
            "note": submission.reviewer_note}


class DepositInput(BaseModel):
    amount_minor: int = Field(gt=0, le=100_000_000)
    method: str = Field(min_length=2, max_length=24)
    payment_destination_id: Optional[int] = Field(default=None, gt=0)
    payment_reference: str = Field(min_length=6, max_length=120)
    proof_image_data: Optional[str] = Field(default=None, max_length=1_500_000)

class DailyHeadlineInput(BaseModel):
    headline: str = Field(min_length=3, max_length=180)
    body: str = Field(default="", max_length=1000)

class TaskPinInput(BaseModel):
    pinned: bool

class DepositReviewInput(BaseModel):
    decision: str = Field(pattern="^(verify|reject)$")
    staff_note: Optional[str] = Field(default=None, max_length=1000)

class CampaignFundingInput(BaseModel):
    amount_minor: int = Field(gt=0, le=100_000_000)

@app.post("/api/v1/deposits", status_code=201)
def request_deposit(data: DepositInput, advertiser: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    ref = data.payment_reference.strip()
    destination = db.get(PaymentDestination, data.payment_destination_id) if data.payment_destination_id else None
    if data.payment_destination_id and (not destination or not destination.active):
        raise HTTPException(status_code=400, detail="Selected payment destination is unavailable")
    if destination and destination.method.lower() != data.method.lower():
        raise HTTPException(status_code=400, detail="Payment method does not match selected destination")
    if db.scalar(select(DepositRequest.id).where(DepositRequest.payment_reference == ref)):
        raise HTTPException(status_code=409, detail="This payment reference has already been submitted")
    if data.proof_image_data and not data.proof_image_data.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
        raise HTTPException(status_code=422, detail="Payment proof must be a JPEG, PNG, or WebP image")
    item = DepositRequest(advertiser_id=advertiser.id, amount_minor=data.amount_minor, method=data.method, payment_destination_id=destination.id if destination else None, payment_reference=ref, proof_image_data=data.proof_image_data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": item.status, "message": "Awaiting independent manual verification; wallet not credited"}

@app.get("/api/v1/deposits")
def my_deposits(advertiser: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(DepositRequest).where(DepositRequest.advertiser_id == advertiser.id).order_by(DepositRequest.id.desc())).all()
    return [{"id": d.id, "amount_minor": d.amount_minor, "method": d.method, "payment_destination_id": d.payment_destination_id, "payment_reference": d.payment_reference, "proof_attached": bool(d.proof_image_data), "status": d.status, "staff_note": d.staff_note} for d in rows]

@app.get("/api/v1/admin/deposits")
def deposit_queue(staff: User = Depends(require_roles("admin", "finance")), db: Session = Depends(get_db)):
    rows = db.execute(select(DepositRequest, User).join(User, DepositRequest.advertiser_id == User.id).where(DepositRequest.status == "pending_review").order_by(DepositRequest.id.asc())).all()
    return [{"id": d.id, "advertiser_id": u.id, "advertiser_name": u.display_name, "amount_minor": d.amount_minor, "method": d.method, "payment_destination_id": d.payment_destination_id, "payment_reference": d.payment_reference, "proof_image_data": d.proof_image_data} for d, u in rows]

@app.post("/api/v1/admin/deposits/{deposit_id}/review")
def review_deposit(deposit_id: int, data: DepositReviewInput, staff: User = Depends(require_roles("admin", "finance")), db: Session = Depends(get_db)):
    item = db.scalar(select(DepositRequest).where(DepositRequest.id == deposit_id).with_for_update())
    if not item:
        raise HTTPException(status_code=404, detail="Deposit request not found")
    if item.status != "pending_review":
        raise HTTPException(status_code=409, detail="Deposit already processed")
    if data.decision == "verify":
        db.add(WalletEntry(user_id=item.advertiser_id, entry_type="credit", amount_minor=item.amount_minor, reference=f"deposit:{item.id}:verified", description=f"Verified deposit #{item.id}", created_by=staff.id))
        item.status = "verified"
    else:
        item.status = "rejected"
    item.staff_note = data.staff_note.strip() if data.staff_note else None
    item.reviewed_by = staff.id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": item.id, "status": item.status}

@app.post("/api/v1/campaigns/{campaign_id}/fund")
def fund_campaign(campaign_id: int, data: CampaignFundingInput, advertiser: User = Depends(require_roles("advertiser", "admin")), db: Session = Depends(get_db)):
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id).with_for_update())
    if not campaign or (advertiser.role != "admin" and campaign.advertiser_id != advertiser.id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in {"draft", "pending_review", "active"}:
        raise HTTPException(status_code=409, detail="Campaign cannot receive funding in this state")
    owner = db.scalar(select(User).where(User.id == campaign.advertiser_id).with_for_update())
    if wallet_totals(db, owner.id)["available_minor"] < data.amount_minor:
        raise HTTPException(status_code=409, detail="Insufficient verified wallet balance")
    db.add(WalletEntry(user_id=owner.id, entry_type="debit", amount_minor=data.amount_minor, reference=f"campaign:{campaign.id}:fund:{secrets.token_hex(8)}", description=f"Budget reserved for campaign #{campaign.id}", created_by=advertiser.id))
    campaign.escrow_balance_minor += data.amount_minor
    db.commit()
    return {"campaign_id": campaign.id, "escrow_balance_minor": campaign.escrow_balance_minor, "funded_amount_minor": data.amount_minor, "currency": "BDT"}

@app.get("/api/v1/campaigns/{campaign_id}/budget")
def campaign_budget(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or (user.role not in {"admin", "reviewer", "finance"} and campaign.advertiser_id != user.id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"campaign_id": campaign.id, "escrow_balance_minor": campaign.escrow_balance_minor, "spent_minor": campaign.spent_minor, "currency": "BDT"}

class WithdrawalInput(BaseModel):
    amount_minor: int = Field(gt=0, le=100_000_000)


class WalletAdjustmentInput(BaseModel):
    user_id: int = Field(gt=0)
    direction: str = Field(pattern="^(credit|debit)$")
    amount_minor: int = Field(gt=0, le=100_000_000)
    reference: str = Field(min_length=6, max_length=100)
    description: str = Field(min_length=5, max_length=300)


class WithdrawalDecisionInput(BaseModel):
    decision: str = Field(pattern="^(pay|reject)$")
    payout_reference: Optional[str] = Field(default=None, min_length=4, max_length=120)
    payout_proof_image: Optional[str] = Field(default=None, max_length=1_500_000)
    staff_note: Optional[str] = Field(default=None, max_length=1000)


def wallet_totals(db: Session, user_id: int):
    entries = db.scalars(select(WalletEntry).where(WalletEntry.user_id == user_id)).all()
    available = 0
    credited = 0
    reserved_or_debited = 0
    for entry in entries:
        if entry.entry_type == "credit":
            available += entry.amount_minor
            credited += entry.amount_minor
        elif entry.entry_type == "debit":
            available -= entry.amount_minor
            reserved_or_debited += entry.amount_minor
        elif entry.entry_type == "hold":
            available -= entry.amount_minor
            reserved_or_debited += entry.amount_minor
        elif entry.entry_type == "release":
            available += entry.amount_minor
            reserved_or_debited -= entry.amount_minor
    return {"available_minor": available, "credited_minor": credited, "reserved_or_debited_minor": reserved_or_debited, "currency": "BDT"}


@app.get("/api/v1/wallet")
def get_wallet(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return wallet_totals(db, user.id)


@app.get("/api/v1/wallet/transactions")
def wallet_transactions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    entries = db.scalars(select(WalletEntry).where(WalletEntry.user_id == user.id).order_by(WalletEntry.id.desc())).all()
    return [{"id": e.id, "type": e.entry_type, "amount_minor": e.amount_minor, "currency": e.currency,
             "reference": e.reference, "description": e.description, "created_at": e.created_at.isoformat()} for e in entries]


@app.post("/api/v1/withdrawals", status_code=201)
def request_withdrawal(data: WithdrawalInput, user: User = Depends(require_roles("member", "maintenance")), db: Session = Depends(get_db)):
    # Serialize balance checks on databases that support row-level locks (e.g. PostgreSQL).
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    totals = wallet_totals(db, user.id)
    if totals["available_minor"] < data.amount_minor:
        raise HTTPException(status_code=409, detail="Insufficient available balance")
    withdrawal = Withdrawal(user_id=user.id, amount_minor=data.amount_minor)
    db.add(withdrawal)
    db.flush()
    db.add(WalletEntry(user_id=user.id, entry_type="hold", amount_minor=data.amount_minor,
                       reference=f"withdrawal:{withdrawal.id}:hold",
                       description=f"Funds reserved for withdrawal request #{withdrawal.id}", created_by=user.id))
    db.commit()
    db.refresh(withdrawal)
    return {"id": withdrawal.id, "amount_minor": withdrawal.amount_minor, "currency": withdrawal.currency,
            "status": withdrawal.status, "message": "Withdrawal request submitted; funds are reserved pending manual review"}


@app.get("/api/v1/withdrawals")
def my_withdrawals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Withdrawal).where(Withdrawal.user_id == user.id).order_by(Withdrawal.id.desc())).all()
    return [{"id": w.id, "amount_minor": w.amount_minor, "currency": w.currency, "status": w.status,
             "staff_note": w.staff_note, "payout_reference": w.payout_reference if w.status == "paid" else None,
             "payout_proof_image": w.payout_proof_image if w.status == "paid" else None,
             "created_at": w.created_at.isoformat(), "processed_at": w.processed_at.isoformat() if w.processed_at else None} for w in rows]


@app.post("/api/v1/admin/wallet/adjust")
def adjust_wallet(data: WalletAdjustmentInput, staff: User = Depends(require_roles("admin", "finance")), db: Session = Depends(get_db)):
    target = db.scalar(select(User).where(User.id == data.user_id).with_for_update())
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if db.scalar(select(WalletEntry.id).where(WalletEntry.reference == data.reference)):
        raise HTTPException(status_code=409, detail="This ledger reference has already been used")
    if data.direction == "debit" and wallet_totals(db, target.id)["available_minor"] < data.amount_minor:
        raise HTTPException(status_code=409, detail="Debit exceeds available wallet balance")
    entry = WalletEntry(user_id=target.id, entry_type=data.direction, amount_minor=data.amount_minor,
                        reference=data.reference, description=data.description.strip(), created_by=staff.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "user_id": target.id, "type": entry.entry_type, "amount_minor": entry.amount_minor,
            "reference": entry.reference, "message": "Manual ledger entry recorded"}


@app.get("/api/v1/admin/withdrawals")
def withdrawal_queue(staff: User = Depends(require_roles("admin", "finance")), db: Session = Depends(get_db)):
    rows = db.execute(select(Withdrawal, User).join(User, Withdrawal.user_id == User.id)
                      .where(Withdrawal.status == "pending").order_by(Withdrawal.id.asc())).all()
    return [{"id": w.id, "user_id": u.id, "user_name": u.display_name, "amount_minor": w.amount_minor,
             "currency": w.currency, "status": w.status, "created_at": w.created_at.isoformat()} for w, u in rows]



@app.get("/api/v1/withdrawal-proof-feed")
def withdrawal_proof_feed(db: Session = Depends(get_db)):
    rows = db.scalars(select(Withdrawal).where(Withdrawal.status == "paid", Withdrawal.payout_proof_image.is_not(None)).order_by(Withdrawal.processed_at.desc()).limit(30)).all()
    return [{"id": w.id, "amount_minor": w.amount_minor, "currency": w.currency,
             "payout_proof_image": w.payout_proof_image,
             "processed_at": w.processed_at.isoformat() if w.processed_at else None}
            for w in rows]

@app.post("/api/v1/admin/withdrawals/{withdrawal_id}/process")
def process_withdrawal(withdrawal_id: int, data: WithdrawalDecisionInput,
                       staff: User = Depends(require_roles("admin", "finance")), db: Session = Depends(get_db)):
    withdrawal = db.get(Withdrawal, withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal request not found")
    if withdrawal.status != "pending":
        raise HTTPException(status_code=409, detail="Withdrawal request has already been processed")
    if data.decision == "pay":
        if not data.payout_reference:
            raise HTTPException(status_code=422, detail="A payout transaction reference is required")
        if not data.payout_proof_image:
            raise HTTPException(status_code=422, detail="Upload the withdrawal payment proof screenshot before marking paid")
        if not data.payout_proof_image.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
            raise HTTPException(status_code=422, detail="Proof must be a JPEG, PNG, or WebP image")
        withdrawal.status = "paid"
        withdrawal.payout_reference = data.payout_reference.strip()
        withdrawal.payout_proof_image = data.payout_proof_image
    else:
        withdrawal.status = "rejected"
        db.add(WalletEntry(user_id=withdrawal.user_id, entry_type="release", amount_minor=withdrawal.amount_minor,
                           reference=f"withdrawal:{withdrawal.id}:release",
                           description=f"Reserved funds released after withdrawal rejection #{withdrawal.id}",
                           created_by=staff.id))
    withdrawal.staff_note = data.staff_note.strip() if data.staff_note else None
    withdrawal.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": withdrawal.id, "status": withdrawal.status, "message": "Withdrawal request processed"}
