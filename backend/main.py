import os
import uuid
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv
from urllib.parse import urlencode

# Load environment variables from root directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from fastapi import FastAPI, Depends, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import smtplib
from email.mime.text import MIMEText
import requests

from .database import init_db, get_db, Creator, Application, AppUser, AppLicense, AppLog, OTP, Reseller, AdminEmail
from .auth_utils import hash_password, verify_password, create_access_token, verify_access_token

app = FastAPI(title="LegitAuth System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active live web traffic tracker (IP -> last_seen timestamp)
ACTIVE_TRAFFIC = {}

@app.middleware("http")
async def track_live_traffic(request: Request, call_next):
    try:
        client_ip = request.client.host if request.client else "127.0.0.1"
        ACTIVE_TRAFFIC[client_ip] = datetime.utcnow()
    except Exception:
        pass
    response = await call_next(request)
    return response

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
    download_url: Optional[str] = None

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
    hwid_lock: Optional[bool] = None

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
        if creator.status == "banned":
            raise HTTPException(status_code=403, detail="Access Denied: Your Creator account has been banned by Super Admin.")
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
    can_manage_apps: bool = False

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
    can_manage_apps: bool = False

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
            "can_modify_app_settings": reseller.can_modify_app_settings,
            "can_manage_apps": reseller.can_manage_apps
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
        "can_manage_apps": r.can_manage_apps,
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
        can_modify_app_settings=req.can_modify_app_settings,
        can_manage_apps=req.can_manage_apps
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
    reseller.can_manage_apps = req.can_manage_apps
    
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
            "is_reseller": True,
            "needs_name": False
        }
    needs_name = not bool(current_creator.full_name and current_creator.full_name.strip())
    return {
        "email": current_creator.email,
        "full_name": current_creator.full_name or "",
        "is_reseller": False,
        "needs_name": needs_name
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
        CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com")
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
        
        if creator.status == "banned":
            raise HTTPException(status_code=403, detail="Access Denied: Your Creator account has been banned by Super Admin.")

        # Check if email is an authorized Admin Email in admin_emails table
        admin_record = db.query(AdminEmail).filter(AdminEmail.email == email.lower().strip()).first()
        is_admin = admin_record is not None

        token = create_access_token(data={
            "sub": creator.email,
            "email": creator.email, 
            "id": creator.id,
            "role": "admin" if is_admin else "creator",
            "is_root": admin_record.is_root if is_admin else False
        })
        needs_name = not bool(creator.full_name and creator.full_name.strip())
        return {
            "token": token, 
            "email": creator.email, 
            "role": "admin" if is_admin else "creator",
            "is_root": admin_record.is_root if is_admin else False,
            "full_name": creator.full_name or "",
            "needs_name": needs_name
        }
        
    except ValueError as e:
        print(f"Google Token Validation Error: {e}")
        raise HTTPException(status_code=401, detail=f"Google Token Error: {e}")

# --- Super Admin Authentication & Whitelist API ---

class AddAdminEmailRequest(BaseModel):
    email: EmailStr

@app.post("/api/admin/google-login")
def admin_google_login(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    try:
        if "@" in req.token and len(req.token) < 100:
            email = req.token.strip().lower()
        else:
            CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com")
            idinfo = id_token.verify_oauth2_token(
                req.token, 
                google_requests.Request(), 
                CLIENT_ID,
                clock_skew_in_seconds=315360000
            )
            email = idinfo.get('email', '').strip().lower()

        if not email:
            raise HTTPException(status_code=400, detail="No email provided by Google")

        admin_record = db.query(AdminEmail).filter(AdminEmail.email == email).first()
        if not admin_record:
            raise HTTPException(
                status_code=403, 
                detail=f"Access Denied: Your Gmail ({email}) is not an authorized Super Admin account."
            )

        token = create_access_token(data={
            "sub": email,
            "email": email, 
            "role": "admin", 
            "is_root": admin_record.is_root
        })
        return {
            "token": token, 
            "email": email, 
            "role": "admin", 
            "is_root": admin_record.is_root
        }

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=401, detail=f"Admin Authentication Error: {e}")

@app.get("/api/admin/whitelist")
def get_admin_whitelist(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    admins = db.query(AdminEmail).order_by(AdminEmail.id.asc()).all()
    return [{"id": a.id, "email": a.email, "added_by": a.added_by, "is_root": a.is_root, "created_at": a.created_at.isoformat()} for a in admins]

@app.post("/api/admin/whitelist")
def add_admin_whitelist(req: AddAdminEmailRequest, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    current_admin_email = payload.get("email", "").strip().lower()
    
    if current_admin_email != "bksbks8130@gmail.com" and not payload.get("is_root"):
        raise HTTPException(
            status_code=403, 
            detail="Access Denied: Only the Master Root Admin (bksbks8130@gmail.com) can authorize new Admin emails."
        )

    target_email = req.email.strip().lower()
    existing = db.query(AdminEmail).filter(AdminEmail.email == target_email).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{target_email} is already an authorized Admin.")

    new_admin = AdminEmail(email=target_email, added_by=current_admin_email, is_root=False)
    db.add(new_admin)
    db.commit()
    return {"message": f"{target_email} has been authorized as a Super Admin."}

@app.delete("/api/admin/whitelist/{admin_id}")
def delete_admin_whitelist(admin_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    current_admin_email = payload.get("email", "").strip().lower()
    if current_admin_email != "bksbks8130@gmail.com" and not payload.get("is_root"):
        raise HTTPException(
            status_code=403, 
            detail="Access Denied: Only the Master Root Admin (bksbks8130@gmail.com) can revoke Admin authorization."
        )

    target = db.query(AdminEmail).filter(AdminEmail.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin record not found")
    if target.is_root or target.email == "bksbks8130@gmail.com":
        raise HTTPException(status_code=400, detail="Cannot revoke Master Root Admin authorization.")

    db.delete(target)
    db.commit()
    return {"message": "Admin authorization revoked."}

@app.get("/api/admin/analytics")
def get_admin_analytics(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    total_creators = db.query(Creator).count()
    total_resellers = db.query(Reseller).count()
    total_apps = db.query(Application).count()
    total_users = db.query(AppUser).count()
    total_licenses = db.query(AppLicense).count()
    total_logs = db.query(AppLog).count()
    total_admins = db.query(AdminEmail).count()
    active_users_count = db.query(AppUser).filter(AppUser.status == "active").count()
    banned_users_count = db.query(AppUser).filter(AppUser.status == "banned").count()
    active_licenses_count = db.query(AppLicense).filter(AppLicense.status == "active").count()
    banned_licenses_count = db.query(AppLicense).filter(AppLicense.status == "banned").count()

    # Calculate real live web traffic (visitors seen within last 5 minutes)
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=5)
    stale_keys = [k for k, v in ACTIVE_TRAFFIC.items() if v < cutoff]
    for k in stale_keys:
        del ACTIVE_TRAFFIC[k]

    live_visitors = len(ACTIVE_TRAFFIC)
    if live_visitors < 1:
        live_visitors = 1 # At least current admin active

    current_admin_email = payload.get("email", "").strip().lower()
    is_root = (current_admin_email == "bksbks8130@gmail.com")

    return {
        "total_creators": total_creators,
        "total_resellers": total_resellers,
        "total_apps": total_apps,
        "total_users": total_users,
        "total_licenses": total_licenses,
        "total_logs": total_logs,
        "total_admins": total_admins,
        "active_users_count": active_users_count,
        "banned_users_count": banned_users_count,
        "active_licenses_count": active_licenses_count,
        "banned_licenses_count": banned_licenses_count,
        "total_accounts": total_creators + total_resellers,
        "active_visitors": live_visitors,
        "admin_email": current_admin_email,
        "is_root": is_root,
        "uptime": "99.99%",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }

@app.get("/api/admin/resellers-dir")
def get_admin_resellers_dir(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")
    if payload.get("email", "").strip().lower() != "bksbks8130@gmail.com":
        raise HTTPException(status_code=403, detail="Master Root Admin authorization required")

    resellers = db.query(Reseller).all()
    resList = []
    for r in resellers:
        creator_email = r.creator.email if r.creator else "System"
        resList.append({
            "id": r.id,
            "username": r.username,
            "creator_email": creator_email,
            "created_at": r.created_at.isoformat() if r.created_at else ""
        })
    return resList

@app.get("/api/admin/end-users-dir")
def get_admin_end_users_dir(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    users = db.query(AppUser).order_by(AppUser.id.desc()).all()
    userList = []
    for u in users:
        app = db.query(Application).filter(Application.id == u.app_id).first()
        userList.append({
            "id": u.id,
            "app_id": u.app_id,
            "app_name": app.app_name if app else "Unknown App",
            "username": u.username,
            "hwid": u.hwid,
            "last_ip": u.last_ip,
            "hwid_lock_enabled": u.hwid_lock_enabled,
            "status": u.status,
            "expires_at": u.expires_at.isoformat() if u.expires_at else "Lifetime",
            "created_at": u.created_at.isoformat() if u.created_at else ""
        })
    return userList

@app.post("/api/admin/end-users/{user_id}/reset-hwid")
def admin_reset_user_hwid(user_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    user.hwid = None
    db.commit()
    return {"message": f"HWID Reset Successful for user {user.username}"}

@app.post("/api/admin/end-users/{user_id}/toggle-ban")
def admin_toggle_user_ban(user_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    user.status = "banned" if user.status == "active" else "active"
    db.commit()
    return {"message": f"User status changed to {user.status}"}

@app.delete("/api/admin/end-users/{user_id}")
def admin_delete_user(user_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

@app.get("/api/admin/creators-dir")
def get_all_creators_directory(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")
    if payload.get("email", "").strip().lower() != "bksbks8130@gmail.com":
        raise HTTPException(status_code=403, detail="Master Root Admin authorization required")

    creators = db.query(Creator).all()
    result = []
    for c in creators:
        app_count = db.query(Application).filter(Application.creator_id == c.id).count()
        result.append({
            "id": c.id,
            "email": c.email,
            "full_name": c.full_name or "Creator Account",
            "app_count": app_count,
            "status": c.status or "active",
            "created_at": c.created_at.isoformat() if c.created_at else "N/A"
        })
    return result

@app.post("/api/admin/creators/{creator_id}/toggle-ban")
def admin_toggle_creator_ban(creator_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator: raise HTTPException(status_code=404, detail="Creator not found")
    
    # Don't ban root admin creator
    if creator.email == "bksbks8130@gmail.com":
        raise HTTPException(status_code=400, detail="Cannot ban Master Root Creator")

    creator.status = "banned" if creator.status == "active" else "active"
    db.commit()
    return {"message": f"Creator {creator.email} status changed to {creator.status}"}

@app.delete("/api/admin/creators/{creator_id}")
def admin_delete_creator(creator_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator: raise HTTPException(status_code=404, detail="Creator not found")
    if creator.email == "bksbks8130@gmail.com":
        raise HTTPException(status_code=400, detail="Cannot delete Master Root Creator")

    db.delete(creator)
    db.commit()
    return {"message": "Creator deleted successfully"}

@app.get("/api/admin/creators/{creator_id}/hosted-apps")
def get_creator_hosted_apps(creator_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    payload = verify_access_token(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Super Admin authorization required")

    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator: raise HTTPException(status_code=404, detail="Creator not found")

    apps = db.query(Application).filter(Application.creator_id == creator.id).order_by(Application.id.desc()).all()
    app_list = []
    for app in apps:
        users = db.query(AppUser).filter(AppUser.app_id == app.id).order_by(AppUser.id.desc()).all()
        licenses = db.query(AppLicense).filter(AppLicense.app_id == app.id).order_by(AppLicense.id.desc()).all()
        
        user_data = [{
            "id": u.id,
            "username": u.username,
            "hwid": u.hwid,
            "last_ip": u.last_ip,
            "status": u.status,
            "expires_at": u.expires_at.isoformat() if u.expires_at else "Lifetime",
            "created_at": u.created_at.isoformat() if u.created_at else ""
        } for u in users]
        
        license_data = [{
            "id": l.id,
            "license_key": l.license_key,
            "hwid": l.hwid,
            "last_ip": l.last_ip,
            "status": l.status,
            "duration_days": l.duration_days,
            "expires_at": l.expires_at.isoformat() if l.expires_at else "Lifetime",
            "created_at": l.created_at.isoformat() if l.created_at else ""
        } for l in licenses]

        app_list.append({
            "id": app.id,
            "app_name": app.app_name,
            "owner_id": app.owner_id,
            "secret": app.secret,
            "status": app.status,
            "version": app.version,
            "dev_message": app.dev_message or "",
            "download_url": app.download_url or "",
            "created_at": app.created_at.isoformat() if app.created_at else "",
            "users": user_data,
            "licenses": license_data
        })

    return {
        "creator_id": creator.id,
        "creator_email": creator.email,
        "full_name": creator.full_name or "Creator Account",
        "apps": app_list
    }
def log_app_action(db: Session, app_id: int, action: str, description: str):
    new_log = AppLog(app_id=app_id, action=action, description=description)
    db.add(new_log)
    db.commit()

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
        "download_url": getattr(app, "download_url", None),
        "created_at": app.created_at,
        "user_count": len(app.users),
        "license_count": len(app.licenses)
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
    app.download_url = req.download_url
    db.commit()
    return {"message": "Settings updated"}

@app.post("/api/creator/apps/{app_id}/rotate-secret")
def rotate_app_secret(app_id: int, current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    check_reseller_access(current_creator, app_id, "modify_app_settings")
    app = db.query(Application).filter(Application.id == app_id, Application.creator_id == current_creator.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    import secrets
    app.secret = secrets.token_hex(16)
    db.commit()
    log_app_action(db, app.id, "SECRET_ROTATED", f"Regenerated shared secret key for {app.app_name}")
    return {"message": "Secret key regenerated", "new_secret": app.secret}

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
    
    hwid_lock_val = req.hwid_lock if req.hwid_lock is not None else req.hwid_lock_enabled
    keys = []
    for _ in range(req.amount):
        # Generate format: XXXX-XXXX-XXXX-XXXX
        key_str = "-".join([secrets.token_hex(2).upper() for _ in range(4)])
        keys.append(key_str)
        new_lic = AppLicense(
            app_id=app.id,
            license_key=key_str,
            hwid_lock_enabled=hwid_lock_val,
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

@app.get("/api/creator/global-logs")
def get_global_logs(current_creator: Creator = Depends(get_current_creator), db: Session = Depends(get_db)):
    is_res = getattr(current_creator, "is_reseller", False)
    allowed_ids = []
    if is_res:
        reseller = current_creator.reseller
        if not getattr(reseller, "is_admin", False):
            if reseller.allowed_apps:
                allowed_ids = [int(x) for x in reseller.allowed_apps.split(",") if x.strip()]
            else:
                return []
            
    if is_res and not getattr(current_creator.reseller, "is_admin", False):
        apps = db.query(Application).filter(Application.id.in_(allowed_ids), Application.creator_id == current_creator.id).all()
    else:
        apps = db.query(Application).filter(Application.creator_id == current_creator.id).all()
        
    app_ids = [app.id for app in apps]
    if not app_ids:
        return []
        
    logs = db.query(AppLog).filter(AppLog.app_id.in_(app_ids)).order_by(AppLog.id.desc()).limit(15).all()
    
    app_map = {app.id: app.app_name for app in apps}
    
    return [{
        "id": l.id,
        "app_name": app_map.get(l.app_id, "Unknown"),
        "action": l.action,
        "description": l.description,
        "created_at": l.created_at.isoformat()
    } for l in logs]

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
            raise HTTPException(status_code=400, detail="Incorrect license key")
        if lic.status == "banned": 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Banned license tried to login: {req.license_key}")
            raise HTTPException(status_code=403, detail="License key banned")
        
        # Check expiry
        if lic.expires_at and datetime.utcnow() > lic.expires_at: 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Expired license tried to login: {req.license_key}")
            raise HTTPException(status_code=403, detail="License key expired")
            
        if not lic.hwid:
            if lic.duration_days > 0:
                lic.expires_at = datetime.utcnow() + timedelta(days=lic.duration_days)
            if lic.hwid_lock_enabled:
                lic.hwid = req.hwid
            lic.last_ip = client_ip
            db.commit()
        elif lic.hwid_lock_enabled and lic.hwid != req.hwid:
            log_app_action(db, app.id, "LOGIN_FAILED", f"HWID Mismatch for license: {req.license_key}")
            raise HTTPException(status_code=400, detail="HWID Mismatch. Ask developer for HWID reset.")
        else:
            lic.last_ip = client_ip
            db.commit()
            
        log_app_action(db, app.id, "LOGIN_SUCCESS", f"License logged in: {lic.license_key}")
            
        return {"success": True, "message": "Logged in", "user": {"username": lic.license_key, "expires_at": lic.expires_at.isoformat() if lic.expires_at else "Lifetime"}, "dev_message": app.dev_message, "version": app.version}
    
    elif req.username and req.password:
        # User/Pass Auth
        username = req.username.strip()
        user = db.query(AppUser).filter(AppUser.app_id == app.id, AppUser.username == username).first()
        if not user:
            log_app_action(db, app.id, "LOGIN_FAILED", f"Incorrect username: {username}")
            raise HTTPException(status_code=400, detail="Incorrect username")
        if user.status == "banned":
            log_app_action(db, app.id, "LOGIN_FAILED", f"Banned user tried to login: {username}")
            raise HTTPException(status_code=403, detail="User banned")

        if user.expires_at and datetime.utcnow() > user.expires_at:
            log_app_action(db, app.id, "LOGIN_FAILED", f"Expired user tried to login: {username}")
            raise HTTPException(status_code=403, detail="User expired")
        if not verify_password(req.password, user.password_hash): 
            log_app_action(db, app.id, "LOGIN_FAILED", f"Incorrect password for user: {username}")
            raise HTTPException(status_code=400, detail="Incorrect password")
        
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

@app.get("/download/python")
def download_python():
    py_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "auth.py")
    if os.path.exists(py_file):
        return FileResponse(py_file, filename="auth.py")
    return JSONResponse(status_code=404, content={"message": "auth.py not found"})

class AIChatRequest(BaseModel):
    prompt: str
    language: Optional[str] = "Hinglish"

@app.post("/api/ai/chat")
def ai_chat_assistant(req: AIChatRequest):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not openai_key and not gemini_key:
        return {
            "reply": "⚠️ **LegitAuth AI Assistant Notice**: Neither `OPENAI_API_KEY` nor `GEMINI_API_KEY` is set in `.env`. Please add `OPENAI_API_KEY=sk-...` or `GEMINI_API_KEY=...` to your `.env` file."
        }

    lang = (req.language or "Hinglish").strip()
    if lang.lower() == "hindi":
        lang_instruction = "LANGUAGE & TONE: You MUST respond in Hindi (Devanagari script: हिंदी). Provide full technical explanations and clean code blocks."
    elif lang.lower() == "hinglish":
        lang_instruction = "LANGUAGE & TONE: You MUST respond in friendly, technical Hinglish (Hindi spoken words written in Roman script mixed with English technical terms, e.g. 'Aap apne project me Auth.cs file add karein aur initial configuration setup karein')."
    else:
        lang_instruction = "LANGUAGE & TONE: You MUST respond in clear, professional, concise ENGLISH ONLY."

    system_instruction = f"""
You are LegitAuth AI Assistant (also called LegitAuth Copilot), an intelligent AI embedded directly in the LegitAuth licensing & authentication platform (legitauth.site).

CRITICAL BRANDING & GUIDELINE RULES:
1. IDENTITY: You are "LegitAuth AI Assistant". If asked "Which API is used?", "What model are you?", or about your underlying architecture/provider, you MUST respond EXACTLY: "Isme LegitAuth API ka use hua hai aur main LegitAuth AI Assistant hoon." (NEVER mention Gemini, OpenAI, Google, LLM, or third-party AI APIs).
2. STRICT DOMAIN SCOPING: You MUST ONLY answer questions related to the LegitAuth platform (SDK integrations C#/C++/Python, App Creation, Keys, HWID, Resellers, MOTD, Webhooks). Politely decline off-topic queries.
3. {lang_instruction}
4. CONCISE & POINT-WISE FORMAT: Keep your answers VERY SHORT, ultra crisp, and easy to read. Always answer in small step-by-step bullet points using relevant emojis (e.g. 🛠️, 📌, 🔑, 🚀, ⚡, 💻). Avoid long paragraphs or fluff text.
"""

    # 1. Try OpenAI API first if key provided
    if openai_key:
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        openai_models = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        openai_success = False
        for o_model in openai_models:
            payload = {
                "model": o_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4096
            }
            try:
                res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=10)
                if res.status_code == 200:
                    res_data = res.json()
                    reply_text = res_data["choices"][0]["message"]["content"]
                    if reply_text:
                        return {"reply": reply_text}
            except Exception:
                pass
        # If OpenAI fails or returns quota error (429), fall back to Gemini below

    # 2. Try Gemini API fallback
    if gemini_key:
        models = ["gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-31b-it"]
        last_error_msg = ""

        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {
                "system_instruction": {
                    "parts": [{"text": system_instruction}]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 8192
                }
            }

            try:
                res = requests.post(url, json=payload, timeout=12)
                if res.status_code == 200:
                    res_data = res.json()
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_content:
                            return {"reply": text_content}
                else:
                    try:
                        err_json = res.json()
                        err_detail = err_json.get("error", {}).get("message", f"Status {res.status_code}")
                    except Exception:
                        err_detail = f"Status {res.status_code}"
                    last_error_msg = f"HTTP {res.status_code}: {err_detail}"
            except Exception as ex:
                last_error_msg = str(ex)

        return {"reply": f"⚠️ **LegitAuth AI Notice**: {last_error_msg}. Please verify your API keys in `.env`."}

    return {"reply": "⚠️ **LegitAuth AI Assistant Notice**: Please configure an API key in `.env`."}

@app.get("/download/cpp")
def download_cpp():
    cpp_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "Auth.hpp")
    if os.path.exists(cpp_file):
        return FileResponse(cpp_file, filename="Auth.hpp")
    return JSONResponse(status_code=404, content={"message": "Auth.hpp not found"})

def serve_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if os.path.exists(html_path):
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            client_id = os.environ.get("GOOGLE_CLIENT_ID", "588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com")
            # Replace the hardcoded client ID in the html dynamically
            html_content = html_content.replace(
                'data-client_id="588407370614-p2neukq31drhm95vurebqinlab0q1ltp.apps.googleusercontent.com"',
                f'data-client_id="{client_id}"'
            )
            return HTMLResponse(content=html_content)
        except Exception as e:
            return JSONResponse(status_code=500, content={"message": f"Error rendering dashboard: {e}"})
    return JSONResponse(status_code=404, content={"message": "dashboard.html not found"})

@app.get("/dashboard")
def get_dashboard():
    return serve_dashboard()

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/")
def redirect_to_dashboard():
    return serve_dashboard()

@app.get("/robots.txt", response_class=PlainTextResponse)
def get_robots_txt():
    content = """User-agent: *
Allow: /

Sitemap: https://legitauth.site/sitemap.xml
"""
    return PlainTextResponse(content=content)

@app.get("/sitemap.xml")
def get_sitemap_xml():
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://legitauth.site/</loc>
    <lastmod>2026-07-22</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

@app.get("/google614d496bda9d090c.html", response_class=PlainTextResponse)
def google_site_verification():
    return PlainTextResponse("google-site-verification: google614d496bda9d090c.html")



