import os
import uuid
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv

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
from google.auth.transport import requests

class GoogleLoginRequest(BaseModel):
    token: str

@app.post("/api/creator/google-login")
def google_login(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    try:
        # Verify the token with Google (with large clock skew tolerance for testing)
        CLIENT_ID = "588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com"
        idinfo = id_token.verify_oauth2_token(
            req.token, 
            requests.Request(), 
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

def log_app_action(db: Session, app_id: int, action: str, description: str):
    new_log = AppLog(app_id=app_id, action=action, description=description)
    db.add(new_log)
    db.commit()

@app.get("/api/creator/apps")
def get_creator_apps(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    applications = db.query(Application).filter(Application.creator_id == current_creator.id).all()
    return [{"id": app.id, "app_name": app.app_name, "owner_id": app.owner_id, "secret": app.secret, "status": app.status, "webhook_url": app.webhook_url, "version": app.version, "dev_message": app.dev_message, "created_at": app.created_at, "discord_guild_id": app.discord_guild_id, "discord_channel_id": app.discord_channel_id, "discord_guild_name": app.discord_guild_name, "discord_channel_name": app.discord_channel_name} for app in applications]

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
    db.commit()
    return {"message": "Discord integration settings updated"}

@app.get("/api/creator/discord/app-by-channel/{channel_id}")
def get_app_by_discord_channel(channel_id: str, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    app = db.query(Application).filter(
        Application.creator_id == current_creator.id,
        Application.discord_channel_id == channel_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="No application linked to this channel")
    return {
        "id": app.id,
        "app_name": app.app_name,
        "owner_id": app.owner_id,
        "secret": app.secret,
        "status": app.status,
        "version": app.version,
        "dev_message": app.dev_message
    }

# --- Discord OAuth2 Endpoints ---
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", os.getenv("LEGITAUTH_API_URL", "http://localhost:8000") + "/api/creator/discord/callback")
DISCORD_BOT_PERMISSIONS = "8"  # Administrator permissions

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
    scopes = "identify guilds"
    url = (
        f"https://discord.com/oauth2/authorize?response_type=code"
        f"&client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&scope={scopes}"
    )
    return {"auth_url": url}

@app.get("/api/creator/discord/callback")
def discord_callback(code: str, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")
    
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
        raise HTTPException(status_code=400, detail="Failed to get Discord token")
    
    token_data = res.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data["expires_in"]
    
    # Get Discord user info
    user_res = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    if user_res.status_code !=200:
        raise HTTPException(status_code=400, detail="Failed to get Discord user")
    user_data = user_res.json()
    
    # Update creator
    current_creator.discord_id = user_data["id"]
    current_creator.discord_access_token = access_token
    current_creator.discord_refresh_token = refresh_token
    current_creator.discord_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    db.commit()
    
    # Redirect back to dashboard
    return RedirectResponse(url="/#discord")

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

@app.get("/api/creator/discord/invite-url")
def get_bot_invite_url(guild_id: Optional[str] = None):
    if not DISCORD_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Discord client ID not set")
    url = (
        f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&permissions={DISCORD_BOT_PERMISSIONS}"
        f"&scope=bot%20applications.commands"
    )
    if guild_id:
        url += f"&guild_id={guild_id}&disable_guild_select=true"
    return {"invite_url": url}


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
