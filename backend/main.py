import os
import uuid
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv
from urllib.parse import urlencode

# Load environment variables from both root and discord_bot directories
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "discord_bot", ".env"), override=True)
from fastapi import FastAPI, Depends, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import smtplib
from email.mime.text import MIMEText
import requests

from .database import init_db, get_db, Creator, Application, AppUser, AppLicense, AppLog, OTP, Reseller
from .auth_utils import hash_password, verify_password, create_access_token, verify_access_token

app = FastAPI(title="LegitAuth System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import subprocess
import sys

@app.on_event("startup")
def startup_event():
    init_db()

# --- Pydantic Schemas ---
class EmailRequest(BaseModel):
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str
    password: str
    full_name: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class CreatorLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AppCreateRequest(BaseModel):
    app_name: str

class AppSettingsRequest(BaseModel):
    status: str
    webhook_url: Optional[str] = None
    version: str
    dev_message: Optional[str] = None

class UserPasswordUpdateRequest(BaseModel):
    new_password: str

class UserCreateRequest(BaseModel):
    username: str
    password: str
    expires_at: Optional[datetime] = None # Fully customizable duration
    hwid_lock_enabled: bool = True

class LicenseCreateRequest(BaseModel):
    amount: int = 1
    duration_days: int = 0
    expires_at: Optional[datetime] = None
    hwid_lock_enabled: bool = True

class ClientRegisterRequest(BaseModel):
    owner_id: str
    secret: str
    app_name: str
    username: str
    password: str
    hwid: str

class ClientLoginRequest(BaseModel):
    hwid_lock: Optional[bool] = True

class UserPasswordUpdateRequest(BaseModel):
    new_password: str

class LicenseCreateRequest(BaseModel):
    amount: int
    duration_days: int
    hwid_lock: Optional[bool] = True

class DiscordConfigRequest(BaseModel):
    discord_guild_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    discord_guild_name: Optional[str] = None
    discord_channel_name: Optional[str] = None
    discord_role_id: Optional[str] = None
    discord_role_name: Optional[str] = None
    discord_log_enabled: Optional[bool] = False
    discord_welcome_enabled: Optional[bool] = False
    discord_welcome_msg: Optional[str] = "Welcome to the Server!"
    discord_role_on_register: Optional[str] = None
    discord_dm_notifications: Optional[bool] = True
    discord_member_reset_enabled: Optional[bool] = False
    discord_login_log_enabled: Optional[bool] = False
    discord_embed_color: Optional[str] = "#00FFAA"
    discord_allowed_roles: Optional[str] = None
    bot_enabled: Optional[bool] = True

class ClientRegisterRequest(BaseModel):
    owner_id: str
    secret: str
    app_name: str
    username: str
    password: str
    hwid: str

class ClientLoginRequest(BaseModel):
    owner_id: str
    secret: str
    app_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    license_key: Optional[str] = None
    hwid: str

# --- Authentication Dependency ---
def get_current_creator(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> Creator:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid Authorization Header")
        token = parts[1]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization Header")

    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired")
    
    role = payload.get("role", "creator")
    if role == "reseller":
        reseller = db.query(Reseller).filter(Reseller.id == payload.get("id")).first()
        if not reseller:
            raise HTTPException(status_code=401, detail="Reseller account not found")
        
        creator = db.query(Creator).filter(Creator.id == reseller.creator_id).first()
        if not creator:
            raise HTTPException(status_code=401, detail="Creator account not found")
        
        creator.is_reseller = True
        creator.reseller = reseller
        return creator
    else:
        creator = db.query(Creator).filter(Creator.email == payload.get("email")).first()
        if not creator:
            raise HTTPException(status_code=401, detail="Creator account not found")
        creator.is_reseller = False
        return creator

def check_reseller_access(current_creator: Creator, app_id: int, action: str):
    if not getattr(current_creator, "is_reseller", False):
        return
        
    reseller = current_creator.reseller
    if getattr(reseller, "is_admin", False):
        return
        
    allowed_ids = []
    if reseller.allowed_apps:
        allowed_ids = [int(x) for x in reseller.allowed_apps.split(",") if x.strip()]
        
    if app_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Access denied to this application")
        
    if action == "manage_users" and not reseller.can_manage_users:
        raise HTTPException(status_code=403, detail="Permission denied to manage users")
        
    if action == "manage_licenses" and not reseller.can_manage_licenses:
        raise HTTPException(status_code=403, detail="Permission denied to manage licenses")
        
    if action == "reset_hwid" and not reseller.can_reset_hwid:
        raise HTTPException(status_code=403, detail="Permission denied to reset HWID")
        
    if action == "view_logs" and not reseller.can_view_logs:
        raise HTTPException(status_code=403, detail="Permission denied to view logs")

    if action == "ban_users" and not getattr(reseller, "can_ban_users", False):
        raise HTTPException(status_code=403, detail="Permission denied to ban/unban users or keys")

    if action == "clean_banned" and not getattr(reseller, "can_clean_banned", False):
        raise HTTPException(status_code=403, detail="Permission denied to clean banned entities")

    if action == "modify_app_settings" and not getattr(reseller, "can_modify_app_settings", False):
        raise HTTPException(status_code=403, detail="Permission denied to modify application settings")

# --- Reseller Request Models ---
class ResellerLoginRequest(BaseModel):
    username: str
    password: str

class ResellerCreateRequest(BaseModel):
    username: str
    password: str
    allowed_apps: List[int]
    is_admin: bool = False
    can_view_secret: bool = False
    can_manage_users: bool = False
    can_manage_licenses: bool = False
    can_reset_hwid: bool = False
    can_view_logs: bool = False
    can_ban_users: bool = False
    can_clean_banned: bool = False
    can_modify_app_settings: bool = False

class ResellerUpdateRequest(BaseModel):
    password: Optional[str] = None
    allowed_apps: List[int]
    is_admin: bool = False
    can_view_secret: bool = False
    can_manage_users: bool = False
    can_manage_licenses: bool = False
    can_reset_hwid: bool = False
    can_view_logs: bool = False
    can_ban_users: bool = False
    can_clean_banned: bool = False
    can_modify_app_settings: bool = False

# --- Reseller Login Endpoint ---
@app.post("/api/reseller/login")
def reseller_login(req: ResellerLoginRequest, db: Session = Depends(get_db)):
    reseller = db.query(Reseller).filter(Reseller.username == req.username).first()
    if not reseller or not verify_password(req.password, reseller.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    token = create_access_token({"sub": reseller.username, "role": "reseller", "id": reseller.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "reseller",
        "permissions": {
            "is_admin": reseller.is_admin,
            "can_view_secret": reseller.can_view_secret,
            "can_manage_users": reseller.can_manage_users,
            "can_manage_licenses": reseller.can_manage_licenses,
            "can_reset_hwid": reseller.can_reset_hwid,
            "can_view_logs": reseller.can_view_logs,
            "can_ban_users": reseller.can_ban_users,
            "can_clean_banned": reseller.can_clean_banned,
            "can_modify_app_settings": reseller.can_modify_app_settings
        }
    }

# --- Creator Reseller Management ---
@app.get("/api/creator/resellers")
def get_resellers(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot manage resellers")
    resellers = db.query(Reseller).filter(Reseller.creator_id == current_creator.id).all()
    return [{
        "id": r.id,
        "username": r.username,
        "allowed_apps": [int(x) for x in r.allowed_apps.split(",") if x.strip()] if r.allowed_apps else [],
        "is_admin": r.is_admin,
        "can_view_secret": r.can_view_secret,
        "can_manage_users": r.can_manage_users,
        "can_manage_licenses": r.can_manage_licenses,
        "can_reset_hwid": r.can_reset_hwid,
        "can_view_logs": r.can_view_logs,
        "can_ban_users": r.can_ban_users,
        "can_clean_banned": r.can_clean_banned,
        "can_modify_app_settings": r.can_modify_app_settings,
        "created_at": r.created_at
    } for r in resellers]

@app.post("/api/creator/resellers")
def create_reseller(req: ResellerCreateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot manage resellers")
        
    # Check if username exists
    existing = db.query(Reseller).filter(Reseller.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Reseller username already exists")
        
    hashed = hash_password(req.password)
    apps_str = ",".join([str(x) for x in req.allowed_apps])
    
    new_reseller = Reseller(
        creator_id=current_creator.id,
        username=req.username,
        password_hash=hashed,
        allowed_apps=apps_str,
        is_admin=req.is_admin,
        can_view_secret=req.can_view_secret,
        can_manage_users=req.can_manage_users,
        can_manage_licenses=req.can_manage_licenses,
        can_reset_hwid=req.can_reset_hwid,
        can_view_logs=req.can_view_logs,
        can_ban_users=req.can_ban_users,
        can_clean_banned=req.can_clean_banned,
        can_modify_app_settings=req.can_modify_app_settings
    )
    db.add(new_reseller)
    db.commit()
    return {"message": "Reseller created successfully"}

@app.put("/api/creator/resellers/{reseller_id}")
def update_reseller(reseller_id: int, req: ResellerUpdateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot manage resellers")
        
    reseller = db.query(Reseller).filter(Reseller.id == reseller_id, Reseller.creator_id == current_creator.id).first()
    if not reseller:
        raise HTTPException(status_code=404, detail="Reseller not found")
        
    if req.password:
        reseller.password_hash = hash_password(req.password)
        
    reseller.allowed_apps = ",".join([str(x) for x in req.allowed_apps])
    reseller.is_admin = req.is_admin
    reseller.can_view_secret = req.can_view_secret
    reseller.can_manage_users = req.can_manage_users
    reseller.can_manage_licenses = req.can_manage_licenses
    reseller.can_reset_hwid = req.can_reset_hwid
    reseller.can_view_logs = req.can_view_logs
    reseller.can_ban_users = req.can_ban_users
    reseller.can_clean_banned = req.can_clean_banned
    reseller.can_modify_app_settings = req.can_modify_app_settings
    
    db.commit()
    return {"message": "Reseller updated successfully"}

@app.delete("/api/creator/resellers/{reseller_id}")
def delete_reseller(reseller_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot manage resellers")
        
    reseller = db.query(Reseller).filter(Reseller.id == reseller_id, Reseller.creator_id == current_creator.id).first()
    if not reseller:
        raise HTTPException(status_code=404, detail="Reseller not found")
        
    db.delete(reseller)
    db.commit()
    return {"message": "Reseller deleted successfully"}

# --- Creator Profile Update Endpoint ---
class CreatorProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None

@app.put("/api/creator/profile")
def update_creator_profile(req: CreatorProfileUpdateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot change creator profile details")
    
    if req.full_name is not None:
        current_creator.full_name = req.full_name
        
    if req.password:
        current_creator.password_hash = hash_password(req.password)
        
    db.commit()
    return {"message": "Creator profile updated successfully"}

@app.get("/api/creator/profile")
def get_creator_profile(current_creator: Creator = Depends(get_current_creator)):
    if getattr(current_creator, "is_reseller", False):
        return {
            "email": current_creator.reseller.username,
            "full_name": "Reseller Account",
            "is_reseller": True
        }
    return {
        "email": current_creator.email,
        "full_name": current_creator.full_name or "",
        "is_reseller": False
    }

# --- Creator API Endpoints ---

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

class GoogleLoginRequest(BaseModel):
    token: str

@app.post("/api/creator/google-login")
def google_login(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    try:
        # Verify the token with Google (with large clock skew tolerance for testing)
        CLIENT_ID = "588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com"
        idinfo = id_token.verify_oauth2_token(
            req.token, 
            google_requests.Request(), 
            CLIENT_ID,
            clock_skew_in_seconds=315360000 # 10 years tolerance
        )
        
        email = idinfo.get('email')
        google_id = idinfo.get('sub')
        
        if not email:
            raise HTTPException(status_code=400, detail="No email provided by Google")

        # Check if creator exists
        creator = db.query(Creator).filter(Creator.email == email).first()
        
        if not creator:
            # Create new creator
            creator = Creator(email=email, is_verified=True, google_id=google_id)
            db.add(creator)
            db.commit()
            db.refresh(creator)
        else:
            # Update google ID if not set
            if not creator.google_id:
                creator.google_id = google_id
                creator.is_verified = True
                db.commit()
        
        token = create_access_token(data={"email": creator.email, "id": creator.id})
        return {"token": token, "email": creator.email}
        
    except ValueError as e:
        print(f"Google Token Validation Error: {e}")
        raise HTTPException(status_code=401, detail=f"Google Token Error: {e}")

def send_discord_log(guild_id: str, channel_id: str, message: str):
    pass

def log_app_action(db: Session, app_id: int, action: str, description: str):
    new_log = AppLog(app_id=app_id, action=action, description=description)
    db.add(new_log)
    db.commit()
    
    # Send log to Discord if enabled
    app = db.query(Application).filter(Application.id == app_id).first()
    if app:
        creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
        if creator and creator.discord_channel_id:
            # Check if logs are enabled, or specifically login logs for SUCCESS/FAIL
            should_send = creator.discord_log_enabled
            if ("LOGIN" in action) and creator.discord_login_log_enabled:
                should_send = True
                
            if should_send:
                emoji = "📝"
                if "SUCCESS" in action: emoji = "🟢"
                elif "FAILED" in action or "FAIL" in action: emoji = "🔴"
                elif "BAN" in action: emoji = "🔨"
                elif "RESET" in action: emoji = "🔄"
                elif "CREATED" in action: emoji = "➕"
                
                msg = f"{emoji} **[LOG: {action}]** {description} (App: `{app.app_name}`)"
                send_discord_log(creator.discord_guild_id, creator.discord_channel_id, msg)

@app.get("/api/creator/apps")
def get_creator_apps(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    applications = db.query(Application).filter(Application.creator_id == current_creator.id).all()
    
    is_res = getattr(current_creator, "is_reseller", False)
    hide_secrets = False
    if is_res:
        reseller = current_creator.reseller
        if not getattr(reseller, "is_admin", False):
            allowed_ids = []
            if reseller.allowed_apps:
                allowed_ids = [int(x) for x in reseller.allowed_apps.split(",") if x.strip()]
            applications = [app for app in applications if app.id in allowed_ids]
            hide_secrets = not reseller.can_view_secret
        else:
            hide_secrets = False
    
    return [{
        "id": app.id,
        "app_name": app.app_name,
        "owner_id": "********" if hide_secrets else app.owner_id,
        "secret": "********" if hide_secrets else app.secret,
        "status": app.status,
        "webhook_url": app.webhook_url,
        "version": app.version,
        "dev_message": app.dev_message,
        "created_at": app.created_at,
        "discord_guild_id": app.discord_guild_id,
        "discord_channel_id": app.discord_channel_id,
        "discord_guild_name": app.discord_guild_name,
        "discord_channel_name": app.discord_channel_name,
        "discord_log_enabled": app.discord_log_enabled,
        "discord_welcome_enabled": app.discord_welcome_enabled,
        "discord_welcome_msg": app.discord_welcome_msg,
        "discord_role_on_register": app.discord_role_on_register,
        "discord_dm_notifications": app.discord_dm_notifications,
        "discord_role_id": app.discord_role_id,
        "discord_role_name": app.discord_role_name,
        "discord_section_id": app.discord_section_id,
        "discord_section_name": app.discord_section_name
    } for app in applications]

@app.post("/api/creator/apps/create")
def create_app(req: AppCreateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot create applications")
        
    if not req.app_name or req.app_name.strip() == "":
        raise HTTPException(status_code=400, detail="App name cannot be empty")
        
    owner_id = str(uuid.uuid4())
    secret = secrets.token_hex(32)
    new_app = Application(creator_id=current_creator.id, app_name=req.app_name.strip(), owner_id=owner_id, secret=secret)
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return {"message": "Application created", "app": {"id": new_app.id, "app_name": new_app.app_name, "owner_id": new_app.owner_id, "secret": new_app.secret}}

@app.delete("/api/creator/apps/{app_id}")
def delete_app(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if getattr(current_creator, "is_reseller", False):
        raise HTTPException(status_code=403, detail="Resellers cannot delete applications")
        
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    db.delete(app)
    db.commit()
    return {"message": "Application deleted successfully"}

@app.put("/api/creator/apps/{app_id}/settings")
def update_app_settings(app_id: int, req: AppSettingsRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "modify_app_settings")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = req.status
    app.webhook_url = req.webhook_url
    app.version = req.version
    app.dev_message = req.dev_message
    db.commit()
    return {"message": "Settings updated"}

@app.post("/api/creator/apps/{app_id}/users")
def add_app_user(app_id: int, req: UserCreateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="Application not found")
    
    existing = db.query(AppUser).filter(AppUser.app_id == app.id, AppUser.username == req.username).first()
    if existing: raise HTTPException(status_code=400, detail="Username already exists in this app")
    
    hashed = hash_password(req.password)
    new_user = AppUser(app_id=app.id, username=req.username, password_hash=hashed, expires_at=req.expires_at, hwid_lock_enabled=req.hwid_lock_enabled)
    db.add(new_user)
    db.commit()
    log_app_action(db, app.id, "USER_CREATED", f"Created user {req.username}")
    return {"message": "User added successfully"}

@app.get("/api/creator/apps/{app_id}/users")
def get_app_users(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    users = db.query(AppUser).filter(AppUser.app_id == app_id).order_by(AppUser.id.desc()).all()
    return [{"id": u.id, "username": u.username, "hwid": u.hwid, "last_ip": u.last_ip, "hwid_lock": u.hwid_lock_enabled, "status": u.status, "expires_at": u.expires_at.isoformat() if u.expires_at else "Lifetime", "created_at": u.created_at} for u in users]

@app.delete("/api/creator/apps/{app_id}/users/{user_id}")
def delete_app_user(app_id: int, user_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.app_id == app.id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

@app.post("/api/creator/apps/{app_id}/users/{user_id}/reset-hwid")
def reset_user_hwid(app_id: int, user_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "reset_hwid")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.app_id == app.id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    user.hwid = None
    db.commit()
    log_app_action(db, app.id, "HWID_RESET", f"Reset HWID for user {user.username}")
    return {"message": "HWID Reset Successful"}

@app.post("/api/creator/apps/{app_id}/users/{user_id}/toggle-ban")
def toggle_user_ban(app_id: int, user_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "ban_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.app_id == app.id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    user.status = "banned" if user.status == "active" else "active"
    db.commit()
    log_app_action(db, app.id, "USER_BAN_TOGGLE", f"Changed status of user {user.username} to {user.status}")
    return {"message": f"User status changed to {user.status}"}

@app.put("/api/creator/apps/{app_id}/users/{user_id}/password")
def update_user_password(app_id: int, user_id: int, req: UserPasswordUpdateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.app_id == app.id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    user.password_hash = hash_password(req.new_password)
    db.commit()
    log_app_action(db, app.id, "USER_PASSWORD_CHANGED", f"Changed password for user {user.username}")
    return {"message": "Password updated successfully"}

@app.post("/api/creator/apps/{app_id}/licenses")
def create_app_licenses(app_id: int, req: LicenseCreateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_licenses")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="Application not found")
    
    keys = []
    for _ in range(req.amount):
        # Generate format: XXXX-XXXX-XXXX-XXXX
        key_str = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
        keys.append(key_str)
        new_lic = AppLicense(
            app_id=app.id,
            license_key=key_str,
            hwid_lock_enabled=req.hwid_lock_enabled,
            expires_at=None,
            duration_days=req.duration_days
        )
        db.add(new_lic)
    db.commit()
    log_app_action(db, app.id, "LICENSE_GENERATED", f"Generated {req.amount} licenses ({req.duration_days} days)")
    return {"message": f"{req.amount} licenses generated successfully", "keys": keys}

@app.get("/api/creator/apps/{app_id}/licenses")
def get_app_licenses(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_licenses")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    licenses = db.query(AppLicense).filter(AppLicense.app_id == app_id).order_by(AppLicense.id.desc()).all()
    return [{"id": l.id, "license_key": l.license_key, "hwid": l.hwid, "last_ip": l.last_ip, "hwid_lock": l.hwid_lock_enabled, "status": l.status, "duration_days": l.duration_days, "expires_at": l.expires_at.isoformat() if l.expires_at else "Lifetime"} for l in licenses]

@app.delete("/api/creator/apps/{app_id}/licenses/{license_id}")
def delete_app_license(app_id: int, license_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "manage_licenses")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    lic = db.query(AppLicense).filter(AppLicense.id == license_id, AppLicense.app_id == app.id).first()
    if not lic: raise HTTPException(status_code=404, detail="License not found")
    db.delete(lic)
    db.commit()
    return {"message": "License deleted"}

@app.post("/api/creator/apps/{app_id}/licenses/{license_id}/reset-hwid")
def reset_license_hwid(app_id: int, license_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "reset_hwid")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    lic = db.query(AppLicense).filter(AppLicense.id == license_id, AppLicense.app_id == app.id).first()
    if not lic: raise HTTPException(status_code=404, detail="License not found")
    lic.hwid = None
    db.commit()
    log_app_action(db, app.id, "HWID_RESET", f"Reset HWID for license {lic.license_key}")
    return {"message": "HWID Reset Successful"}

@app.post("/api/creator/apps/{app_id}/licenses/{license_id}/toggle-ban")
def toggle_license_ban(app_id: int, license_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "ban_users")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    lic = db.query(AppLicense).filter(AppLicense.id == license_id, AppLicense.app_id == app.id).first()
    if not lic: raise HTTPException(status_code=404, detail="License not found")
    
    lic.status = "banned" if lic.status == "active" else "active"
    db.commit()
    log_app_action(db, app.id, "LICENSE_BAN_TOGGLE", f"Changed status of license {lic.license_key} to {lic.status}")
    return {"message": f"License status changed to {lic.status}"}

@app.get("/api/creator/apps/{app_id}/logs")
def get_app_logs(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "view_logs")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    logs = db.query(AppLog).filter(AppLog.app_id == app.id).order_by(AppLog.id.desc()).limit(50).all()
    return [{"id": l.id, "action": l.action, "description": l.description, "created_at": l.created_at.isoformat()} for l in logs]

@app.delete("/api/creator/apps/{app_id}/clean-banned")
def clean_banned_entities(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "clean_banned")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    
    banned_users = db.query(AppUser).filter(AppUser.app_id == app_id, AppUser.status == "banned").all()
    banned_lics = db.query(AppLicense).filter(AppLicense.app_id == app_id, AppLicense.status == "banned").all()
    
    user_count = len(banned_users)
    lic_count = len(banned_lics)
    
    for u in banned_users:
        db.delete(u)
    for l in banned_lics:
        db.delete(l)
        
    db.commit()
    log_app_action(db, app.id, "CLEAN_BANNED", f"Cleaned {user_count} banned users and {lic_count} banned licenses")
    return {
        "message": f"Successfully deleted {user_count} banned users and {lic_count} banned licenses",
        "users_deleted": user_count,
        "licenses_deleted": lic_count
    }

def send_discord_webhook(url: str, message: str):
    pass

# --- Client API ---
@app.post("/api/client/login")
def client_login(req: ClientLoginRequest, request: Request, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.owner_id == req.owner_id, Application.secret == req.secret, Application.app_name == req.app_name).first()
    if not app: raise HTTPException(status_code=400, detail="Invalid app credentials")
    if app.status == "paused": 
        log_app_action(db, app.id, "LOGIN_FAILED", "Failed login due to app maintenance mode")
        raise HTTPException(status_code=503, detail="Application is under maintenance")
    
    client_ip = request.client.host
    
    if req.license_key:
        # License Key Auth
        lic = db.query(AppLicense).filter(AppLicense.app_id == app.id, AppLicense.license_key == req.license_key).first()
        if not lic: 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Invalid license key {req.license_key}")
            raise HTTPException(status_code=400, detail="License key not found")
        if lic.status == "banned": 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Banned license tried to login: {req.license_key}")
            raise HTTPException(status_code=403, detail="Banned")
        
        # Check expiry
        if lic.expires_at and datetime.utcnow() > lic.expires_at: 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Expired license tried to login: {req.license_key}")
            raise HTTPException(status_code=403, detail="Expired")
            
        if not lic.hwid:
            if lic.duration_days > 0:
                lic.expires_at = datetime.utcnow() + timedelta(days=lic.duration_days)
            if lic.hwid_lock_enabled:
                lic.hwid = req.hwid
            lic.last_ip = client_ip
            db.commit()
        elif lic.hwid_lock_enabled and lic.hwid != req.hwid:
            log_app_action(db, app.id, "LOGIN_FAILED", f"HWID Mismatch for license: {req.license_key}")
            raise HTTPException(status_code=400, detail="HWID Mismatch. Key tied to another machine.")
        else:
            lic.last_ip = client_ip
            db.commit()
            
        log_app_action(db, app.id, "LOGIN_SUCCESS", f"License logged in: {lic.license_key}")
        send_discord_webhook(app.webhook_url, f"🟢 **Login Alert**\nUser: `{lic.license_key}`\nApp: `{app.app_name}`\nIP: `{client_ip}`")
            
        return {"success": True, "message": "Logged in", "user": {"username": lic.license_key, "expires_at": lic.expires_at.isoformat() if lic.expires_at else "Lifetime"}, "dev_message": app.dev_message, "version": app.version}
    
    elif req.username and req.password:
        # User/Pass Auth
        username = req.username.strip()
        user = db.query(AppUser).filter(AppUser.app_id == app.id, AppUser.username == username).first()
        if not user:
            log_app_action(db, app.id, "LOGIN_FAILED", f"Invalid user credentials: {username}")
            raise HTTPException(status_code=400, detail="Invalid username or password")
        if user.status == "banned":
            log_app_action(db, app.id, "LOGIN_FAILED", f"Banned user tried to login: {username}")
            raise HTTPException(status_code=403, detail="Banned")

        if user.expires_at and datetime.utcnow() > user.expires_at:
            log_app_action(db, app.id, "LOGIN_FAILED", f"Expired user tried to login: {username}")
            raise HTTPException(status_code=403, detail="Expired")
        if not verify_password(req.password, user.password_hash): raise HTTPException(status_code=400, detail="Invalid password")
        
        if not user.hwid:
            if user.hwid_lock_enabled:
                user.hwid = req.hwid
            user.last_ip = client_ip
            db.commit()
        elif user.hwid_lock_enabled and user.hwid != req.hwid:
            log_app_action(db, app.id, "LOGIN_FAILED", f"HWID Mismatch for user: {req.username}")
            raise HTTPException(status_code=400, detail="HWID Mismatch. Account tied to another machine.")
        else:
            user.last_ip = client_ip
            db.commit()
            
        log_app_action(db, app.id, "LOGIN_SUCCESS", f"User logged in: {user.username}")
        send_discord_webhook(app.webhook_url, f"🟢 **Login Alert**\nUser: `{user.username}`\nApp: `{app.app_name}`\nIP: `{client_ip}`")
            
        return {"success": True, "message": "Logged in", "user": {"username": user.username, "expires_at": user.expires_at.isoformat() if user.expires_at else "Lifetime"}, "dev_message": app.dev_message, "version": app.version}
    
    else:
        raise HTTPException(status_code=400, detail="Provide either username/password or license_key")

@app.get("/download/auth")
def download_auth():
    # Provide the C# SDK for download
    cs_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "Auth.cs")
    if os.path.exists(cs_file):
        return FileResponse(cs_file, filename="Auth.cs")
    return JSONResponse(status_code=404, content={"message": "Auth.cs not found"})

@app.get("/dashboard")
def get_dashboard():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "dashboard.html"))

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/")
def redirect_to_dashboard():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "dashboard.html"))



