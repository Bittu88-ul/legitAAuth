import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./auth_system.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Creator(Base):
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=True) # Nullable for Google Auth
    is_verified = Column(Boolean, default=False)
    google_id = Column(String, unique=True, nullable=True)
    discord_id = Column(String, unique=True, nullable=True)
    discord_access_token = Column(String, nullable=True)
    discord_refresh_token = Column(String, nullable=True)
    discord_token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    applications = relationship("Application", back_populates="creator", cascade="all, delete-orphan")
    otps = relationship("OTP", back_populates="creator", cascade="all, delete-orphan")

class OTP(Base):
    __tablename__ = "otps"
    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    creator = relationship("Creator", back_populates="otps")

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    app_name = Column(String, nullable=False)
    owner_id = Column(String, unique=True, index=True, nullable=False)  # UUID
    secret = Column(String, nullable=False)  # Raw secure secret string
    status = Column(String, default="active") # active, paused
    webhook_url = Column(String, nullable=True) # Discord Webhook
    version = Column(String, default="1.0")
    dev_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    discord_guild_id = Column(String, nullable=True)
    discord_channel_id = Column(String, nullable=True)
    discord_guild_name = Column(String, nullable=True)
    discord_channel_name = Column(String, nullable=True)

    # Relationships
    creator = relationship("Creator", back_populates="applications")
    users = relationship("AppUser", back_populates="application", cascade="all, delete-orphan")
    licenses = relationship("AppLicense", back_populates="application", cascade="all, delete-orphan")
    logs = relationship("AppLog", back_populates="application", cascade="all, delete-orphan")

class AppLog(Base):
    __tablename__ = "app_logs"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    action = Column(String, nullable=False)  # e.g., "LOGIN", "GENERATE", "BAN", "HWID_FAIL"
    description = Column(String, nullable=True) # e.g., "User johndoe logged in from IP 1.1.1.1"
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="logs")

class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    hwid = Column(String, nullable=True)  # Nullable, set on first login
    last_ip = Column(String, nullable=True)
    hwid_lock_enabled = Column(Boolean, default=True) # Whether HWID is strictly checked
    status = Column(String, default="active")  # active, banned
    expires_at = Column(DateTime, nullable=True)  # Nullable for lifetime accounts
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    application = relationship("Application", back_populates="users")

class AppLicense(Base):
    __tablename__ = "app_licenses"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    license_key = Column(String, unique=True, nullable=False, index=True)
    hwid = Column(String, nullable=True)  # Nullable, set on first login
    last_ip = Column(String, nullable=True)
    hwid_lock_enabled = Column(Boolean, default=True)
    status = Column(String, default="active")  # active, banned
    expires_at = Column(DateTime, nullable=True) # Expiry calculated after first login, or set immediately? Usually KeyAuth uses duration, but we can stick to expires_at for simplicity for now.
    duration_days = Column(Integer, default=0) # If > 0, expires_at is set when first logged in
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    application = relationship("Application", back_populates="licenses")

def init_db():
    Base.metadata.create_all(bind=engine)
    # Ensure discord fields exist for existing sqlite database
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN discord_guild_id VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN discord_channel_id VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN discord_guild_name VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN discord_channel_name VARCHAR"))
    except Exception:
        pass
    # Add Discord OAuth fields to creators
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE creators ADD COLUMN discord_id VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE creators ADD COLUMN discord_access_token VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE creators ADD COLUMN discord_refresh_token VARCHAR"))
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE creators ADD COLUMN discord_token_expires_at DATETIME"))
    except Exception:
        pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
