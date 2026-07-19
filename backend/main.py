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

from .database import init_db, get_db, Creator, Application, AppUser, AppLicense, AppLog, OTP
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
    
    # Start the Discord Bot in the background
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if bot_token and "YOUR_DISCORD_BOT_TOKEN_HERE" not in bot_token:
        try:
            bot_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "discord_bot", "bot.py")
            print(f"Starting Discord Bot in the background: {bot_path}")
            subprocess.Popen(
                [sys.executable, bot_path],
                cwd=os.path.dirname(bot_path),
                env=os.environ.copy()
            )
        except Exception as e:
            print(f"Failed to start Discord Bot: {e}")

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
    owner_id: str
    secret: str
    app_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    license_key: Optional[str] = None
    hwid: str

class DiscordConfigRequest(BaseModel):
    discord_guild_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    discord_guild_name: Optional[str] = None
    discord_channel_name: Optional[str] = None
    discord_log_enabled: Optional[bool] = False
    discord_welcome_enabled: Optional[bool] = False
    discord_welcome_msg: Optional[str] = "Welcome to the Server!"
    discord_role_on_register: Optional[str] = None
    discord_dm_notifications: Optional[bool] = True
    discord_role_id: Optional[str] = None
    discord_role_name: Optional[str] = None
    discord_section_id: Optional[str] = None
    discord_section_name: Optional[str] = None
    discord_member_reset_enabled: Optional[bool] = False
    discord_login_log_enabled: Optional[bool] = False
    discord_embed_color: Optional[str] = "#00FFAA"
    discord_allowed_roles: Optional[str] = None
    bot_enabled: Optional[bool] = True

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
    
    creator = db.query(Creator).filter(Creator.email == payload.get("email")).first()
    if not creator:
        raise HTTPException(status_code=401, detail="Creator account not found")
    return creator

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
    if not DISCORD_BOT_TOKEN or not channel_id:
        return
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"content": message}
    try:
        requests.post(url, json=payload, headers=headers, timeout=3)
    except Exception as e:
        print(f"Error sending Discord log: {e}")

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
    return [{"id": app.id, "app_name": app.app_name, "owner_id": app.owner_id, "secret": app.secret, "status": app.status, "webhook_url": app.webhook_url, "version": app.version, "dev_message": app.dev_message, "created_at": app.created_at, "discord_guild_id": app.discord_guild_id, "discord_channel_id": app.discord_channel_id, "discord_guild_name": app.discord_guild_name, "discord_channel_name": app.discord_channel_name, "discord_log_enabled": app.discord_log_enabled, "discord_welcome_enabled": app.discord_welcome_enabled, "discord_welcome_msg": app.discord_welcome_msg, "discord_role_on_register": app.discord_role_on_register, "discord_dm_notifications": app.discord_dm_notifications, "discord_role_id": app.discord_role_id, "discord_role_name": app.discord_role_name, "discord_section_id": app.discord_section_id, "discord_section_name": app.discord_section_name} for app in applications]

@app.post("/api/creator/apps/create")
def create_app(req: AppCreateRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
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
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    db.delete(app)
    db.commit()
    return {"message": "Application deleted successfully"}

@app.put("/api/creator/apps/{app_id}/settings")
def update_app_settings(app_id: int, req: AppSettingsRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
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
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    users = db.query(AppUser).filter(AppUser.app_id == app_id).order_by(AppUser.id.desc()).all()
    return [{"id": u.id, "username": u.username, "hwid": u.hwid, "last_ip": u.last_ip, "hwid_lock": u.hwid_lock_enabled, "status": u.status, "expires_at": u.expires_at.isoformat() if u.expires_at else "Lifetime", "created_at": u.created_at} for u in users]

@app.delete("/api/creator/apps/{app_id}/users/{user_id}")
def delete_app_user(app_id: int, user_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.app_id == app.id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

@app.post("/api/creator/apps/{app_id}/users/{user_id}/reset-hwid")
def reset_user_hwid(app_id: int, user_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
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
            expires_at=req.expires_at,
            duration_days=req.duration_days
        )
        db.add(new_lic)
    db.commit()
    log_app_action(db, app.id, "LICENSE_GENERATED", f"Generated {req.amount} licenses ({req.duration_days} days)")
    return {"message": f"{req.amount} licenses generated successfully", "keys": keys}

@app.get("/api/creator/apps/{app_id}/licenses")
def get_app_licenses(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    licenses = db.query(AppLicense).filter(AppLicense.app_id == app_id).order_by(AppLicense.id.desc()).all()
    return [{"id": l.id, "license_key": l.license_key, "hwid": l.hwid, "last_ip": l.last_ip, "hwid_lock": l.hwid_lock_enabled, "status": l.status, "duration_days": l.duration_days, "expires_at": l.expires_at.isoformat() if l.expires_at else "Lifetime"} for l in licenses]

@app.delete("/api/creator/apps/{app_id}/licenses/{license_id}")
def delete_app_license(app_id: int, license_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    lic = db.query(AppLicense).filter(AppLicense.id == license_id, AppLicense.app_id == app.id).first()
    if not lic: raise HTTPException(status_code=404, detail="License not found")
    db.delete(lic)
    db.commit()
    return {"message": "License deleted"}

@app.post("/api/creator/apps/{app_id}/licenses/{license_id}/reset-hwid")
def reset_license_hwid(app_id: int, license_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
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
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app: raise HTTPException(status_code=404, detail="App not found")
    logs = db.query(AppLog).filter(AppLog.app_id == app.id).order_by(AppLog.id.desc()).limit(50).all()
    return [{"id": l.id, "action": l.action, "description": l.description, "created_at": l.created_at.isoformat()} for l in logs]

@app.delete("/api/creator/apps/{app_id}/clean-banned")
def clean_banned_entities(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
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

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

@app.get("/api/creator/discord/resolve-invite")
def resolve_discord_invite(invite: str, current_creator: Creator = Depends(get_current_creator)):
    code = invite.strip().split("/")[-1]
    res = requests.get(f"https://discord.com/api/v9/invites/{code}")
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid Discord invite link or code")
    data = res.json()
    guild = data.get("guild")
    if not guild:
        raise HTTPException(status_code=400, detail="Invite is not for a server (guild)")
    return {"guild_id": guild.get("id"), "guild_name": guild.get("name")}

@app.get("/api/creator/discord/channels")
def get_discord_channels(guild_id: str, current_creator: Creator = Depends(get_current_creator)):
    if not DISCORD_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="DISCORD_BOT_TOKEN not configured on server")
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    res = requests.get(f"https://discord.com/api/v9/guilds/{guild_id}/channels", headers=headers)
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not fetch channels. Make sure the bot is invited to the server first.")
    channels = res.json()
    text_channels = [
        {"id": c.get("id"), "name": c.get("name")}
        for c in channels
        if c.get("type") == 0
    ]
    return text_channels

@app.put("/api/creator/apps/{app_id}/discord")
def update_app_discord_config(app_id: int, req: DiscordConfigRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.discord_guild_id = req.discord_guild_id
    app.discord_channel_id = req.discord_channel_id
    app.discord_guild_name = req.discord_guild_name
    app.discord_channel_name = req.discord_channel_name
    app.discord_log_enabled = req.discord_log_enabled
    app.discord_welcome_enabled = req.discord_welcome_enabled
    app.discord_welcome_msg = req.discord_welcome_msg
    app.discord_role_on_register = req.discord_role_on_register
    app.discord_dm_notifications = req.discord_dm_notifications
    app.discord_role_id = req.discord_role_id
    app.discord_role_name = req.discord_role_name
    app.discord_section_id = req.discord_section_id
    app.discord_section_name = req.discord_section_name
    db.commit()
    return {"message": "Discord integration settings updated"}

@app.get("/api/creator/discord/config")
def get_creator_discord_config(current_creator: Creator = Depends(get_current_creator)):
    return {
        "discord_guild_id": current_creator.discord_guild_id,
        "discord_channel_id": current_creator.discord_channel_id,
        "discord_guild_name": current_creator.discord_guild_name,
        "discord_channel_name": current_creator.discord_channel_name,
        "discord_role_id": current_creator.discord_role_id,
        "discord_role_name": current_creator.discord_role_name,
        "discord_log_enabled": current_creator.discord_log_enabled,
        "discord_welcome_enabled": current_creator.discord_welcome_enabled,
        "discord_welcome_msg": current_creator.discord_welcome_msg,
        "discord_role_on_register": current_creator.discord_role_on_register,
        "discord_dm_notifications": current_creator.discord_dm_notifications,
        "discord_member_reset_enabled": current_creator.discord_member_reset_enabled,
        "discord_login_log_enabled": current_creator.discord_login_log_enabled,
        "discord_embed_color": current_creator.discord_embed_color or "#00FFAA",
        "discord_allowed_roles": current_creator.discord_allowed_roles,
        "bot_enabled": current_creator.bot_enabled
    }

@app.put("/api/creator/discord/config")
def update_creator_discord_config(req: DiscordConfigRequest, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    current_creator.discord_guild_id = req.discord_guild_id
    current_creator.discord_channel_id = req.discord_channel_id
    current_creator.discord_guild_name = req.discord_guild_name
    current_creator.discord_channel_name = req.discord_channel_name
    current_creator.discord_role_id = req.discord_role_id
    current_creator.discord_role_name = req.discord_role_name
    current_creator.discord_log_enabled = req.discord_log_enabled
    current_creator.discord_welcome_enabled = req.discord_welcome_enabled
    current_creator.discord_welcome_msg = req.discord_welcome_msg
    current_creator.discord_role_on_register = req.discord_role_on_register
    current_creator.discord_dm_notifications = req.discord_dm_notifications
    current_creator.discord_member_reset_enabled = req.discord_member_reset_enabled
    current_creator.discord_login_log_enabled = req.discord_login_log_enabled
    current_creator.discord_embed_color = req.discord_embed_color
    current_creator.discord_allowed_roles = req.discord_allowed_roles
    current_creator.bot_enabled = req.bot_enabled
    
    # Sync to all apps of this creator
    apps = db.query(Application).filter(Application.creator_id == current_creator.id).all()
    for app in apps:
        app.discord_guild_id = req.discord_guild_id
        app.discord_channel_id = req.discord_channel_id
        app.discord_guild_name = req.discord_guild_name
        app.discord_channel_name = req.discord_channel_name
        app.discord_role_id = req.discord_role_id
        app.discord_role_name = req.discord_role_name
        app.discord_log_enabled = req.discord_log_enabled
        app.discord_welcome_enabled = req.discord_welcome_enabled
        app.discord_welcome_msg = req.discord_welcome_msg
        app.discord_role_on_register = req.discord_role_on_register
        app.discord_dm_notifications = req.discord_dm_notifications
        app.discord_allowed_roles = req.discord_allowed_roles
        app.bot_enabled = req.bot_enabled
        
    db.commit()
    return {"message": "Global Discord configuration updated successfully"}

@app.get("/api/creator/discord/config-by-guild/{guild_id}")
def get_config_by_guild(guild_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.discord_guild_id == guild_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Guild not linked to any application")
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
        
    return {
        "discord_guild_id": creator.discord_guild_id,
        "discord_guild_name": creator.discord_guild_name,
        "discord_channel_id": creator.discord_channel_id,
        "discord_channel_name": creator.discord_channel_name,
        "discord_role_id": creator.discord_role_id,
        "discord_role_name": creator.discord_role_name,
        "discord_log_enabled": creator.discord_log_enabled,
        "discord_welcome_enabled": creator.discord_welcome_enabled,
        "discord_welcome_msg": creator.discord_welcome_msg,
        "discord_role_on_register": creator.discord_role_on_register,
        "discord_dm_notifications": creator.discord_dm_notifications,
        "discord_member_reset_enabled": creator.discord_member_reset_enabled,
        "discord_login_log_enabled": creator.discord_login_log_enabled,
        "discord_embed_color": creator.discord_embed_color or "#00FFAA",
        "discord_allowed_roles": creator.discord_allowed_roles,
        "bot_enabled": creator.bot_enabled
    }

@app.put("/api/creator/discord/config-by-guild/{guild_id}")
def update_config_by_guild(guild_id: str, req: DiscordConfigRequest, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.discord_guild_id == guild_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Guild not linked to any application")
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
        
    creator.discord_guild_id = req.discord_guild_id
    creator.discord_guild_name = req.discord_guild_name
    creator.discord_channel_id = req.discord_channel_id
    creator.discord_channel_name = req.discord_channel_name
    creator.discord_role_id = req.discord_role_id
    creator.discord_role_name = req.discord_role_name
    creator.discord_log_enabled = req.discord_log_enabled
    creator.discord_welcome_enabled = req.discord_welcome_enabled
    creator.discord_welcome_msg = req.discord_welcome_msg
    creator.discord_role_on_register = req.discord_role_on_register
    creator.discord_dm_notifications = req.discord_dm_notifications
    creator.discord_member_reset_enabled = req.discord_member_reset_enabled
    creator.discord_login_log_enabled = req.discord_login_log_enabled
    creator.discord_embed_color = req.discord_embed_color
    creator.discord_allowed_roles = req.discord_allowed_roles
    creator.bot_enabled = req.bot_enabled
    
    # Sync to all apps of this creator
    apps = db.query(Application).filter(Application.creator_id == creator.id).all()
    for a in apps:
        a.discord_guild_id = req.discord_guild_id
        a.discord_channel_id = req.discord_channel_id
        a.discord_guild_name = req.discord_guild_name
        a.discord_channel_name = req.discord_channel_name
        a.discord_role_id = req.discord_role_id
        a.discord_role_name = req.discord_role_name
        a.discord_log_enabled = req.discord_log_enabled
        a.discord_welcome_enabled = req.discord_welcome_enabled
        a.discord_welcome_msg = req.discord_welcome_msg
        a.discord_role_on_register = req.discord_role_on_register
        a.discord_dm_notifications = req.discord_dm_notifications
        a.discord_allowed_roles = req.discord_allowed_roles
        a.bot_enabled = req.bot_enabled
        
    db.commit()
    return {"message": "Config updated successfully for guild"}

@app.get("/api/creator/discord/app-by-channel/{channel_id}")
def get_app_by_discord_channel(channel_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(
        Application.discord_channel_id == channel_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="No application linked to this channel")
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    return {
        "id": app.id,
        "app_name": app.app_name,
        "owner_id": app.owner_id,
        "secret": app.secret,
        "status": app.status,
        "version": app.version,
        "dev_message": app.dev_message,
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
        "discord_section_name": app.discord_section_name,
        "discord_member_reset_enabled": creator.discord_member_reset_enabled if creator else False,
        "discord_login_log_enabled": creator.discord_login_log_enabled if creator else False,
        "discord_embed_color": (creator.discord_embed_color if creator else "#00FFAA") or "#00FFAA",
        "discord_allowed_roles": app.discord_allowed_roles,
        "bot_enabled": app.bot_enabled
    }

@app.get("/api/creator/discord/app-by-section/{section_id}")
def get_app_by_discord_section(section_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(
        Application.discord_section_id == section_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="No application linked to this section")
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    return {
        "id": app.id,
        "app_name": app.app_name,
        "owner_id": app.owner_id,
        "secret": app.secret,
        "status": app.status,
        "version": app.version,
        "dev_message": app.dev_message,
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
        "discord_section_name": app.discord_section_name,
        "discord_member_reset_enabled": creator.discord_member_reset_enabled if creator else False,
        "discord_login_log_enabled": creator.discord_login_log_enabled if creator else False,
        "discord_embed_color": (creator.discord_embed_color if creator else "#00FFAA") or "#00FFAA",
        "discord_allowed_roles": app.discord_allowed_roles,
        "bot_enabled": app.bot_enabled
    }

@app.get("/api/creator/discord/app-by-guild/{guild_id}")
def get_app_by_discord_guild(guild_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(
        Application.discord_guild_id == guild_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="No application linked to this server")
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    return {
        "id": app.id,
        "app_name": app.app_name,
        "owner_id": app.owner_id,
        "secret": app.secret,
        "status": app.status,
        "version": app.version,
        "dev_message": app.dev_message,
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
        "discord_section_name": app.discord_section_name,
        "discord_member_reset_enabled": creator.discord_member_reset_enabled if creator else False,
        "discord_login_log_enabled": creator.discord_login_log_enabled if creator else False,
        "discord_embed_color": (creator.discord_embed_color if creator else "#00FFAA") or "#00FFAA",
        "discord_allowed_roles": app.discord_allowed_roles,
        "bot_enabled": app.bot_enabled
    }

# --- Discord OAuth2 Endpoints ---
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", os.getenv("LEGITAUTH_API_URL", "http://localhost:8000") + "/api/creator/discord/callback")
DISCORD_BOT_PERMISSIONS = "8"  # Administrator permissions
FRONTEND_URL = os.getenv("LEGITAUTH_API_URL", "http://localhost:8000")

def build_bot_invite_url(guild_id: Optional[str] = None) -> str:
    client_id = DISCORD_CLIENT_ID or "1522600480662880347"
    params = {
        "client_id": client_id,
        "permissions": DISCORD_BOT_PERMISSIONS,
        "scope": "bot applications.commands",
        "response_type": "code",
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    if guild_id:
        params["guild_id"] = guild_id
        params["disable_guild_select"] = "true"
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

def refresh_discord_token(creator: Creator, db: Session):
    # Check if token needs refresh
    if not creator.discord_refresh_token:
        raise HTTPException(status_code=400, detail="No Discord refresh token available")
    
    now = datetime.utcnow()
    if creator.discord_token_expires_at and now < creator.discord_token_expires_at - timedelta(minutes=5):
        return creator.discord_access_token
    
    # Refresh the token
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": creator.discord_refresh_token,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    res = requests.post("https://discord.com/api/v10/oauth2/token", data=data, headers=headers)
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to refresh Discord token")
    token_data = res.json()
    
    creator.discord_access_token = token_data["access_token"]
    creator.discord_refresh_token = token_data.get("refresh_token", creator.discord_refresh_token)
    creator.discord_token_expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
    db.commit()
    return creator.discord_access_token

@app.get("/api/creator/discord/login")
def discord_login(current_creator: Creator = Depends(get_current_creator)):
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")
    # Get user's token so we can pass it in state
    user_token = create_access_token(data={"email": current_creator.email, "id": current_creator.id})
    scopes = "identify guilds"
    params = {
        "response_type": "code",
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": scopes,
        "state": user_token,
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return {"auth_url": url}

@app.get("/api/creator/discord/callback")
def discord_callback(code: Optional[str] = None, state: Optional[str] = None, guild_id: Optional[str] = None, permissions: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        # Bot invite callback (no state) — bot was added to the server
        if not state:
            return RedirectResponse(url=f"{FRONTEND_URL}/#discord")
        
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Discord OAuth not configured")
        
        # Verify the token from state to get current creator
        payload = verify_access_token(state)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid state token")
        
        # Get creator from payload
        creator = db.query(Creator).filter(Creator.email == payload.get("email")).first()
        if not creator:
            raise HTTPException(status_code=401, detail="Creator not found")
        
        # Exchange code for access token
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        res = requests.post("https://discord.com/api/v10/oauth2/token", data=data, headers=headers)
        if res.status_code != 200:
            print(f"Discord token exchange error: {res.status_code} {res.text}")
            raise HTTPException(status_code=400, detail="Failed to get Discord token")
        
        token_data = res.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data["expires_in"]
        
        # Get Discord user info
        user_res = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        if user_res.status_code !=200:
            print(f"Discord user info error: {user_res.status_code} {user_res.text}")
            raise HTTPException(status_code=400, detail="Failed to get Discord user")
        user_data = user_res.json()
        
        # Update creator
        creator.discord_id = user_data["id"]
        creator.discord_access_token = access_token
        creator.discord_refresh_token = refresh_token
        creator.discord_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        db.commit()
        
        # Redirect back to dashboard
        return RedirectResponse(url=f"{FRONTEND_URL}/#discord")
    except Exception as e:
        print(f"Discord callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/#discord")

@app.get("/api/creator/discord/me")
def get_discord_me(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if not current_creator.discord_id or not current_creator.discord_access_token:
        raise HTTPException(status_code=404, detail="Discord not linked")
    
    token = refresh_discord_token(current_creator, db)
    res = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {token}"})
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get Discord user")
    return res.json()

@app.get("/api/creator/discord/guilds")
def get_discord_guilds(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if not current_creator.discord_id or not current_creator.discord_access_token:
        raise HTTPException(status_code=404, detail="Discord not linked")
    
    token = refresh_discord_token(current_creator, db)
    res = requests.get("https://discord.com/api/v10/users/@me/guilds", headers={"Authorization": f"Bearer {token}"})
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get guilds")
    
    # Filter guilds where user has MANAGE_GUILD or ADMINISTRATOR
    # Permissions bit: 0x20 is MANAGE_GUILD, 0x8 is ADMINISTRATOR
    guilds = []
    for guild in res.json():
        permissions = int(guild["permissions"])
        if (permissions & 0x20) or (permissions & 0x8):
            guilds.append(guild)
    return guilds

@app.get("/api/creator/discord/guilds/{guild_id}/channels")
def get_discord_guild_channels(guild_id: str, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    # First get channels using bot token (since user might not have access, but bot does if in server)
    if not DISCORD_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Discord bot token missing")
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
    if res.status_code !=200:
        raise HTTPException(status_code=400, detail="Could not get channels from bot, make sure bot is in the server")
    channels = [c for c in res.json() if c["type"] ==0] # Only text channels
    return channels

@app.get("/api/creator/discord/guilds/{guild_id}/sections")
def get_discord_guild_sections(guild_id: str, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if not DISCORD_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Discord bot token missing")
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not get sections from bot, make sure bot is in the server")
    sections = [{"id": c.get("id"), "name": c.get("name")} for c in res.json() if c.get("type") == 4]
    return sections

@app.get("/api/creator/discord/guilds/{guild_id}/roles")
def get_discord_guild_roles(guild_id: str, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if not DISCORD_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Discord bot token missing")
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers)
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not get roles from bot, make sure bot is in the server")
    roles = [{"id": r.get("id"), "name": r.get("name")} for r in res.json()]
    return roles

@app.get("/api/creator/discord/invite-url")
def get_bot_invite_url(guild_id: Optional[str] = None):
    return {
        "invite_url": build_bot_invite_url(guild_id),
        "redirect_uri": DISCORD_REDIRECT_URI,
    }


def send_discord_webhook(url: str, message: str):
    if not url: return
    try:
        requests.post(url, json={"content": message}, timeout=3)
    except:
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

# --- Customer Self-Service HWID Reset Endpoints ---
class MemberResetHWIDRequest(BaseModel):
    username: str
    password: str
    app_id: Optional[int] = None

@app.post("/api/creator/discord/reset-member-hwid")
def reset_member_hwid(req: MemberResetHWIDRequest, db: Session = Depends(get_db)):
    user = None
    app = None
    if req.app_id:
        app = db.query(Application).filter(Application.id == req.app_id).first()
        if app:
            user = db.query(AppUser).filter(AppUser.app_id == app.id, AppUser.username == req.username).first()
    else:
        users = db.query(AppUser).filter(AppUser.username == req.username).all()
        if len(users) == 1:
            user = users[0]
            app = db.query(Application).filter(Application.id == user.app_id).first()
        elif len(users) > 1:
            raise HTTPException(status_code=400, detail="Multiple users found with this name. Please specify App ID.")
    
    if not user or not app:
        raise HTTPException(status_code=404, detail="User not found")
        
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    if not creator or not creator.discord_member_reset_enabled:
        raise HTTPException(status_code=403, detail="Member self HWID reset is disabled by the administrator.")
        
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
        
    user.hwid = None
    db.commit()
    log_app_action(db, app.id, "MEMBER_HWID_RESET", f"User {user.username} reset their own HWID via Discord Bot")
    return {"success": True, "message": f"HWID reset successfully for user **{user.username}**."}

class MemberResetLicenseRequest(BaseModel):
    license_key: str
    app_id: Optional[int] = None

@app.post("/api/creator/discord/reset-member-license")
def reset_member_license(req: MemberResetLicenseRequest, db: Session = Depends(get_db)):
    lic = None
    app = None
    if req.app_id:
        app = db.query(Application).filter(Application.id == req.app_id).first()
        if app:
            lic = db.query(AppLicense).filter(AppLicense.app_id == app.id, AppLicense.license_key == req.license_key).first()
    else:
        lics = db.query(AppLicense).filter(AppLicense.license_key == req.license_key).all()
        if len(lics) == 1:
            lic = lics[0]
            app = db.query(Application).filter(Application.id == lic.app_id).first()
        elif len(lics) > 1:
            raise HTTPException(status_code=400, detail="Multiple license records found. Please specify App ID.")
    
    if not lic or not app:
        raise HTTPException(status_code=404, detail="License key not found")
        
    creator = db.query(Creator).filter(Creator.id == app.creator_id).first()
    if not creator or not creator.discord_member_reset_enabled:
        raise HTTPException(status_code=403, detail="Member self HWID reset is disabled by the administrator.")
        
    lic.hwid = None
    db.commit()
    log_app_action(db, app.id, "MEMBER_HWID_RESET", f"License {lic.license_key} reset their own HWID via Discord Bot")
    return {"success": True, "message": "License HWID reset successfully."}

