import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sqlite_path = os.path.join(BASE_DIR, "auth_system.db")
    # Auto-migrate/copy root auth_system.db if the backend one is uninitialized
    root_db = os.path.join(os.path.dirname(BASE_DIR), "auth_system.db")
    if os.path.exists(root_db) and (not os.path.exists(sqlite_path) or os.path.getsize(sqlite_path) == 0):
        try:
            import shutil
            shutil.copy2(root_db, sqlite_path)
        except Exception:
            pass
    DATABASE_URL = f"sqlite:///{sqlite_path}"

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
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    applications = relationship("Application", back_populates="creator", cascade="all, delete-orphan")
    otps = relationship("OTP", back_populates="creator", cascade="all, delete-orphan")
    resellers = relationship("Reseller", back_populates="creator", cascade="all, delete-orphan")

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

class Reseller(Base):
    __tablename__ = "resellers"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    allowed_apps = Column(String, nullable=True) # Comma-separated string of app IDs
    
    # Permissions
    is_admin = Column(Boolean, default=False)
    can_view_secret = Column(Boolean, default=False)
    can_manage_users = Column(Boolean, default=False)
    can_manage_licenses = Column(Boolean, default=False)
    can_reset_hwid = Column(Boolean, default=False)
    can_view_logs = Column(Boolean, default=False)
    can_ban_users = Column(Boolean, default=False)
    can_clean_banned = Column(Boolean, default=False)
    can_modify_app_settings = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("Creator", back_populates="resellers")

def init_db():
    Base.metadata.create_all(bind=engine)
    # Add new reseller columns for existing database
    for field in ["is_admin", "can_ban_users", "can_clean_banned", "can_modify_app_settings"]:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE resellers ADD COLUMN {field} BOOLEAN DEFAULT FALSE"))
        except Exception:
            pass
    # Ensure discord fields exist for existing database
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
