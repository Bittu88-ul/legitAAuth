import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional
import discord
from discord import app_commands
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("LEGITAUTH_API_URL", "https://legitauth1-3.onrender.com")
DEFAULT_API_TOKEN = os.getenv("LEGITAUTH_API_TOKEN")  # Fallback for owner

def parse_expiry(expiry_str: Optional[str]) -> Optional[str]:
    if not expiry_str or expiry_str.strip().lower() in ("none", "never", "lifetime", "null", "0", ""):
        return None
    
    # Check if they just wrote a plain number of days, e.g. "30"
    if expiry_str.strip().isdigit():
        days_val = int(expiry_str.strip())
        if days_val <= 0:
            return None
        dt = datetime.utcnow() + timedelta(days=days_val)
        return dt.isoformat()
    
    # Try parsing format like 1d, 12h, 30m, 1y, etc.
    pattern = re.compile(r"^(\d+)([dhmwy]?)$", re.IGNORECASE)
    match = pattern.match(expiry_str.strip())
    if match:
        val = int(match.group(1))
        unit = match.group(2).lower() if match.group(2) else "d"
        
        now = datetime.utcnow()
        if unit == "d":
            dt = now + timedelta(days=val)
        elif unit == "h":
            dt = now + timedelta(hours=val)
        elif unit == "m":
            dt = now + timedelta(minutes=val)
        elif unit == "w":
            dt = now + timedelta(weeks=val)
        elif unit == "y":
            dt = now + timedelta(days=val * 365)
        else:
            return None
        return dt.isoformat()
    
    # Check if they wrote it as a plain ISO date already, just in case
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(expiry_str.strip(), fmt)
            return dt.isoformat()
        except ValueError:
            continue
            
    return None

intents = discord.Intents.default()
client = discord.Client(intents=intents)

tree = app_commands.CommandTree(client)

# File to store user tokens
USER_TOKENS_FILE = "user_tokens.json"

# Load existing tokens if file exists
def load_user_tokens():
    if os.path.exists(USER_TOKENS_FILE):
        try:
            with open(USER_TOKENS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading user tokens: {e}")
            return {}
    return {}

def save_user_tokens(tokens):
    with open(USER_TOKENS_FILE, "w") as f:
        json.dump(tokens, f)

# Load tokens on start
user_tokens: dict[str, str] = load_user_tokens()  # key: str(user_id), value: api_token
user_selected_app: dict[int, dict] = {}

def api_headers_for_user(user_id: int):
    user_id_str = str(user_id)
    token = user_tokens.get(user_id_str, DEFAULT_API_TOKEN)
    return {"Authorization": f"Bearer {token}"}

def api_headers():
    return {"Authorization": f"Bearer {DEFAULT_API_TOKEN}"}

def get_embed_color(app: Optional[dict] = None) -> int:
    color_str = "#00FFAA"
    if app and app.get("discord_embed_color"):
        color_str = app.get("discord_embed_color")
    try:
        color_str = color_str.replace("#", "")
        return int(color_str, 16)
    except Exception:
        return 0x00FFAA

def get_current_app(interaction: discord.Interaction):
    # 1. Check user session selection
    app = user_selected_app.get(interaction.user.id)
    if app:
        return app
        
    # 2. Check by guild ID (if in server)
    if interaction.guild_id:
        url = f"{API_BASE}/api/creator/discord/app-by-guild/{interaction.guild_id}"
        try:
            resp = requests.get(url, headers=api_headers())
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
            
    # 3. Fallback: check creator's apps (if exactly one app, auto-select it)
    try:
        url = f"{API_BASE}/api/creator/apps"
        resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
        if resp.status_code == 200:
            apps = resp.json()
            if len(apps) == 1:
                user_selected_app[interaction.user.id] = apps[0]
                return apps[0]
    except Exception:
        pass
        
    return None

@tree.interaction_check
async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # Setup / system linking commands are bypassed
    bypass_commands = ["link_token", "unlink_token"]
    if interaction.command and interaction.command.name in bypass_commands:
        return True
        
    if not interaction.guild_id:
        # In DMs, allow commands to run
        return True
        
    # Query app/creator settings by guild id
    url = f"{API_BASE}/api/creator/discord/app-by-guild/{interaction.guild_id}"
    try:
        resp = requests.get(url, headers=api_headers())
        if resp.status_code == 200:
            app = resp.json()
            chan_id = app.get("discord_channel_id")
            role_id = app.get("discord_role_id")
            
            # Channel restriction check
            if chan_id and str(interaction.channel_id) != str(chan_id):
                await interaction.response.send_message("❌ This bot is restricted to a specific channel and cannot reply here.", ephemeral=True)
                return False
                
            # Role restriction check
            if role_id:
                if not isinstance(interaction.user, discord.Member):
                    await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                    return False
                user_role_ids = [str(r.id) for r in interaction.user.roles]
                if str(role_id) not in user_role_ids:
                    await interaction.response.send_message("❌ You do not have the required role to use this bot.", ephemeral=True)
                    return False
    except Exception as e:
        print(f"Error during global checks: {e}")
        
    return True

def validate_bot_access(interaction: discord.Interaction, app: dict) -> tuple[bool, str]:
    # Check channel/section restriction
    chan_id = app.get("discord_channel_id")
    sect_id = app.get("discord_section_id")
    role_id = app.get("discord_role_id")
    
    # If either channel or section is restricted, interaction must be inside that channel or section
    if chan_id or sect_id:
        channel_matched = (chan_id and str(interaction.channel_id) == str(chan_id))
        category_id = getattr(interaction.channel, "category_id", None)
        section_matched = (sect_id and category_id and str(category_id) == str(sect_id))
        
        if not (channel_matched or section_matched):
            return False, "This bot is not active in this channel/section."
            
    # Check role restriction
    if role_id:
        if not isinstance(interaction.user, discord.Member):
            return False, "This command can only be used in a server."
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        if str(role_id) not in user_role_ids:
            return False, f"Only users with the role '{app.get('discord_role_name', 'Authorized Role')}' can run commands."
            
    return True, ""

@tree.interaction_check
async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # Skip checks for non-app management setup commands
    bypass_commands = ["link_token", "unlink_token", "list_apps", "select_app", "register", "help"]
    if interaction.command and interaction.command.name in bypass_commands:
        return True
    
    app = get_current_app(interaction)
    if not app:
        # If no app linked, let the command execute so it returns its default error message
        return True
        
    allowed, msg = validate_bot_access(interaction, app)
    if not allowed:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return False
        
    return True

# New commands for linking/unlinking token
@tree.command(name="link_token", description="Link your LegitAuth API token to use the bot")
@app_commands.describe(api_token="Your API token from LegitAuth Settings tab")
async def link_token(interaction: discord.Interaction, api_token: str):
    # Test if token is valid
    test_url = f"{API_BASE}/api/creator/apps"
    test_resp = requests.get(test_url, headers={"Authorization": f"Bearer {api_token}"})
    if test_resp.status_code != 200:
        await interaction.response.send_message("❌ Invalid token! Please check and try again.", ephemeral=True)
        return
    
    # Save token
    user_id_str = str(interaction.user.id)
    user_tokens[user_id_str] = api_token
    save_user_tokens(user_tokens)
    await interaction.response.send_message("✅ Token linked successfully! You can now use the bot commands.", ephemeral=True)

@tree.command(name="unlink_token", description="Unlink your LegitAuth API token from the bot")
async def unlink_token(interaction: discord.Interaction):
    user_id_str = str(interaction.user.id)
    if user_id_str in user_tokens:
        del user_tokens[user_id_str]
        save_user_tokens(user_tokens)
    await interaction.response.send_message("✅ Token unlinked successfully.", ephemeral=True)

@tree.command(name="list_apps", description="List your LegitAuth applications")
async def list_apps(interaction: discord.Interaction):
    url = f"{API_BASE}/api/creator/apps"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch apps. Did you link your token with /link_token?", ephemeral=True)
        return
    apps = resp.json()
    if not apps:
        await interaction.response.send_message("No applications found.", ephemeral=True)
        return
    embed = discord.Embed(title="Your Applications", color=0x00FFAA)
    for app in apps:
        guild_name = app.get("discord_guild_name") or "None"
        channel_name = app.get("discord_channel_name") or "None"
        embed.add_field(
            name=app["app_name"],
            value=f"ID: {app['id']}\nLinked Discord: {guild_name} (#{channel_name})",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="select_app", description="Select an application to work with")
@app_commands.describe(app_id="Application ID from /list_apps")
async def select_app(interaction: discord.Interaction, app_id: int):
    url = f"{API_BASE}/api/creator/apps"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Unable to verify app. Did you link your token with /link_token?", ephemeral=True)
        return
    apps = resp.json()
    selected = next((a for a in apps if a["id"] == app_id), None)
    if not selected:
        await interaction.response.send_message("App ID not found under your account.", ephemeral=True)
        return
    user_selected_app[interaction.user.id] = selected
    await interaction.response.send_message(f"Selected app **{selected['app_name']}** (ID: {app_id}).", ephemeral=True)

@tree.command(name="create_user", description="Create a new user/password for the selected app")
@app_commands.describe(username="New username", password="Password", expires_at="Duration (e.g. 7d, 24h, 30) or leave blank for lifetime", hw_id_lock="Lock to HWID (true/false)")
async def create_user(interaction: discord.Interaction, username: str, password: str, expires_at: Optional[str] = None, hw_id_lock: bool = True):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel. Use `/select_app <app_id>` first or link this channel in the dashboard.", ephemeral=True)
        return
    
    app_id = app["id"]
    parsed_expiry = parse_expiry(expires_at)
    
    payload = {
        "username": username,
        "password": password,
        "expires_at": parsed_expiry,
        "hwid_lock_enabled": hw_id_lock,
    }
    url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    resp = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"User **{username}** created successfully for application **{app['app_name']}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="list_users", description="List all users for the selected app")
async def list_users(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users.", ephemeral=True)
        return
    users = resp.json()
    if not users:
        await interaction.response.send_message("No users found for this app.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Users for {app['app_name']}", color=0x00AAFF)
    for user in users:
        embed.add_field(
            name=f"{user['username']} (ID: {user['id']})",
            value=f"Status: {user['status']}\nHWID: {user['hwid'] or 'Not set'}\nExpires: {user['expires_at']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="delete_user", description="Delete a user from the selected app")
@app_commands.describe(user_id="User ID from /list_users")
async def delete_user(interaction: discord.Interaction, user_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users/{user_id}"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("User deleted successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="reset_user_hwid", description="Reset HWID for a user")
@app_commands.describe(user_id="User ID from /list_users")
async def reset_user_hwid(interaction: discord.Interaction, user_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users/{user_id}/reset-hwid"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("User HWID reset successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="toggle_user_ban", description="Ban/unban a user")
@app_commands.describe(user_id="User ID from /list_users")
async def toggle_user_ban(interaction: discord.Interaction, user_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users/{user_id}/toggle-ban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("User ban status toggled successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="create_license", description="Generate licenses for the selected app")
@app_commands.describe(amount="Number of licenses", duration_days="Duration in days (0 = lifetime)", expires_at="Duration (e.g. 7d, 24h, 30) or leave blank", hw_id_lock="Lock to HWID (true/false)")
async def create_license(interaction: discord.Interaction, amount: int, duration_days: int = 0, expires_at: Optional[str] = None, hw_id_lock: bool = True):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel. Use `/select_app <app_id>` first or link this channel in the dashboard.", ephemeral=True)
        return
    
    app_id = app["id"]
    parsed_expiry = parse_expiry(expires_at)
    
    payload = {
        "amount": amount,
        "duration_days": duration_days,
        "expires_at": parsed_expiry,
        "hwid_lock_enabled": hw_id_lock,
    }
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses"
    resp = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        data = resp.json()
        keys = "\n".join(data.get("keys", []))
        await interaction.response.send_message(f"Generated {amount} license(s) for **{app['app_name']}**:\n\n{keys}\n", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="list_licenses", description="List all licenses for the selected app")
async def list_licenses(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch licenses.", ephemeral=True)
        return
    licenses = resp.json()
    if not licenses:
        await interaction.response.send_message("No licenses found for this app.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Licenses for {app['app_name']}", color=0xFFAA00)
    for lic in licenses:
        embed.add_field(
            name=f"Key: {lic['license_key']} (ID: {lic['id']})",
            value=f"Status: {lic['status']}\nHWID: {lic['hwid'] or 'Not set'}\nExpires: {lic['expires_at']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="delete_license", description="Delete a license from the selected app")
@app_commands.describe(license_id="License ID from /list_licenses")
async def delete_license(interaction: discord.Interaction, license_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses/{license_id}"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("License deleted successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="reset_license_hwid", description="Reset HWID for a license")
@app_commands.describe(license_id="License ID from /list_licenses")
async def reset_license_hwid(interaction: discord.Interaction, license_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses/{license_id}/reset-hwid"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("License HWID reset successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="toggle_license_ban", description="Ban/unban a license")
@app_commands.describe(license_id="License ID from /list_licenses")
async def toggle_license_ban(interaction: discord.Interaction, license_id: int):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses/{license_id}/toggle-ban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("License ban status toggled successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="list_logs", description="List recent logs for the selected app")
async def list_logs(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/logs"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch logs.", ephemeral=True)
        return
    logs = resp.json()
    if not logs:
        await interaction.response.send_message("No logs found for this app.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Recent Logs for {app['app_name']}", color=0xFF00AA)
    for log in logs:
        embed.add_field(
            name=log["action"],
            value=f"{log['description']}\n{log['created_at']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# New help command
@tree.command(name="help", description="Show available bot commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Help - Available Commands", color=0x00FFAA)
    commands = [
        ("/help", "Show this help message"),
        ("/list_apps", "List your LegitAuth applications"),
        ("/select_app", "Select an application to work with"),
        ("/create_user", "Create a new user/password for the selected app"),
        ("/list_users", "List all users for the selected app"),
        ("/list_licenses", "List all licenses for the selected app"),
        ("/stats", "Show statistics for the selected app"),
        ("/app_info", "Show detailed information about the selected app"),
        ("/search_user", "Search for a user by username"),
        ("/search_key", "Search for a license key"),
        ("/change_password", "Change password for a user"),
        ("/active_users", "List active users"),
        ("/banned_users", "List banned users"),
        ("/clean_banned", "Remove all banned users and licenses"),
        ("/give_cread", "Show Owner ID, Secret, and Name for an app"),
        ("/register", "Register the current channel with an app")
    ]
    for name, desc in commands:
        embed.add_field(name=name, value=desc, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="stats", description="Show statistics for the selected app")
async def stats(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    headers = api_headers_for_user(interaction.user.id)
    
    # Fetch users
    users_url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    users_resp = requests.get(users_url, headers=headers)
    
    # Fetch licenses
    lics_url = f"{API_BASE}/api/creator/apps/{app_id}/licenses"
    lics_resp = requests.get(lics_url, headers=headers)
    
    if users_resp.status_code != 200 or lics_resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch app statistics.", ephemeral=True)
        return
        
    users = users_resp.json()
    licenses = lics_resp.json()
    
    total_users = len(users)
    active_users_count = sum(1 for u in users if u.get("status") == "active")
    banned_users_count = sum(1 for u in users if u.get("status") == "banned")
    
    total_lics = len(licenses)
    active_lics_count = sum(1 for l in licenses if l.get("status") == "active")
    banned_lics_count = sum(1 for l in licenses if l.get("status") == "banned")
    unused_lics_count = sum(1 for l in licenses if not l.get("hwid") and l.get("status") == "active")
    
    embed = discord.Embed(title=f"📊 Statistics: {app['app_name']}", color=0x00FF88)
    embed.add_field(name="App Status", value=f"• **Status:** {app.get('status', 'Unknown').capitalize()}\n• **Version:** {app.get('version', '1.0')}", inline=False)
    embed.add_field(name="Users", value=f"• **Total:** {total_users}\n• **Active:** {active_users_count}\n• **Banned:** {banned_users_count}", inline=True)
    embed.add_field(name="Licenses", value=f"• **Total:** {total_lics}\n• **Active:** {active_lics_count}\n• **Banned:** {banned_lics_count}\n• **Unused:** {unused_lics_count}", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="app_info", description="Show detailed information about the selected app")
async def app_info(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"ℹ️ App Info: {app['app_name']}", color=0x00AAFF)
    embed.add_field(name="App ID", value=str(app['id']), inline=True)
    embed.add_field(name="Status", value=app.get('status', 'active').capitalize(), inline=True)
    embed.add_field(name="Version", value=app.get('version', '1.0'), inline=True)
    embed.add_field(name="Dev Message", value=app.get('dev_message') or "None", inline=False)
    embed.add_field(name="Webhook URL", value=app.get('webhook_url') or "None", inline=False)
    
    guild_name = app.get("discord_guild_name") or "Not Linked"
    channel_name = app.get("discord_channel_name") or "Not Linked"
    embed.add_field(name="Discord Link", value=f"Guild: {guild_name}\nChannel: {channel_name}", inline=False)
    
    log_status = "Enabled" if app.get("discord_log_enabled") else "Disabled"
    welcome_status = "Enabled" if app.get("discord_welcome_enabled") else "Disabled"
    embed.add_field(name="Bot Config", value=f"• Console Logs: {log_status}\n• Welcome System: {welcome_status}\n• Welcome MSG: {app.get('discord_welcome_msg') or 'None'}\n• DM Notifications: {'Enabled' if app.get('discord_dm_notifications') else 'Disabled'}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="search_user", description="Search for a user by username")
@app_commands.describe(username="Username to search for")
async def search_user(interaction: discord.Interaction, username: str):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users list.", ephemeral=True)
        return
        
    users = resp.json()
    user = next((u for u in users if u['username'].lower() == username.lower()), None)
    if not user:
        await interaction.response.send_message(f"❌ User `{username}` not found.", ephemeral=True)
        return
        
    embed = discord.Embed(title=f"👤 User Details: {user['username']}", color=0x00FF55)
    embed.add_field(name="User ID", value=str(user['id']), inline=True)
    embed.add_field(name="Status", value=user['status'].capitalize(), inline=True)
    embed.add_field(name="Locked HWID", value=user.get('hwid') or "Not Set", inline=False)
    embed.add_field(name="Last IP", value=user.get('last_ip') or "None", inline=True)
    embed.add_field(name="Expires At", value=user.get('expires_at') or "Lifetime", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="search_key", description="Search for a license key")
@app_commands.describe(key="License key to search for")
async def search_key(interaction: discord.Interaction, key: str):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/licenses"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch licenses list.", ephemeral=True)
        return
        
    licenses = resp.json()
    lic = next((l for l in licenses if l['license_key'].lower() == key.lower()), None)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` not found.", ephemeral=True)
        return
        
    embed = discord.Embed(title=f"🔑 License Details", color=0xFFBB00)
    embed.add_field(name="Key", value=f"`{lic['license_key']}`", inline=False)
    embed.add_field(name="License ID", value=str(lic['id']), inline=True)
    embed.add_field(name="Status", value=lic['status'].capitalize(), inline=True)
    embed.add_field(name="Locked HWID", value=lic.get('hwid') or "Not Set", inline=False)
    embed.add_field(name="Last IP", value=lic.get('last_ip') or "None", inline=True)
    embed.add_field(name="Duration (Days)", value=str(lic.get('duration_days', 0)), inline=True)
    embed.add_field(name="Expires At", value=lic.get('expires_at') or "Lifetime", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="change_password", description="Change password for a user")
@app_commands.describe(username="Username", new_password="New password")
async def change_password(interaction: discord.Interaction, username: str, new_password: str):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
        
    app_id = app["id"]
    headers = api_headers_for_user(interaction.user.id)
    
    # Look up user by username to get ID
    users_url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    users_resp = requests.get(users_url, headers=headers)
    if users_resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users list.", ephemeral=True)
        return
        
    users = users_resp.json()
    user = next((u for u in users if u['username'].lower() == username.lower()), None)
    if not user:
        await interaction.response.send_message(f"❌ User `{username}` not found.", ephemeral=True)
        return
        
    # Update password
    user_id = user['id']
    pwd_url = f"{API_BASE}/api/creator/apps/{app_id}/users/{user_id}/password"
    resp = requests.put(pwd_url, json={"new_password": new_password}, headers=headers)
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ Successfully updated password for user **{user['username']}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to change password: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="active_users", description="List active users")
async def active_users(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users.", ephemeral=True)
        return
        
    users = [u for u in resp.json() if u.get('status') == 'active']
    if not users:
        await interaction.response.send_message("No active users found for this app.", ephemeral=True)
        return
        
    embed = discord.Embed(title=f"🟢 Active Users for {app['app_name']}", color=0x00FF55)
    description = ""
    for u in users[:25]:
        description += f"• **{u['username']}** (Expires: {u.get('expires_at') or 'Lifetime'})\n"
    if len(users) > 25:
        description += f"\n*And {len(users) - 25} more...*"
        
    embed.description = description
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="banned_users", description="List banned users")
async def banned_users(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
    
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users.", ephemeral=True)
        return
        
    users = [u for u in resp.json() if u.get('status') == 'banned']
    if not users:
        await interaction.response.send_message("No banned users found for this app.", ephemeral=True)
        return
        
    embed = discord.Embed(title=f"🔴 Banned Users for {app['app_name']}", color=0xFF3333)
    description = ""
    for u in users[:25]:
        description += f"• **{u['username']}** (Expires: {u.get('expires_at') or 'Lifetime'})\n"
    if len(users) > 25:
        description += f"\n*And {len(users) - 25} more...*"
        
    embed.description = description
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="clean_banned", description="Remove all banned users and licenses")
async def clean_banned(interaction: discord.Interaction):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel.", ephemeral=True)
        return
        
    app_id = app["id"]
    url = f"{API_BASE}/api/creator/apps/{app_id}/clean-banned"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        data = resp.json()
        await interaction.response.send_message(f"✅ Cleaned banned users and licenses successfully!\n• Users Deleted: {data.get('users_deleted', 0)}\n• Licenses Deleted: {data.get('licenses_deleted', 0)}", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to clean banned: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="give_cread", description="Show Owner ID, Secret, and Name for an app")
@app_commands.describe(app_identifier="App Name or App ID (optional)")
async def give_cread(interaction: discord.Interaction, app_identifier: Optional[str] = None):
    url = f"{API_BASE}/api/creator/apps"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch apps list.", ephemeral=True)
        return
        
    apps = resp.json()
    selected_app = None
    
    if app_identifier:
        if app_identifier.isdigit():
            selected_app = next((a for a in apps if a['id'] == int(app_identifier)), None)
        if not selected_app:
            selected_app = next((a for a in apps if a['app_name'].lower() == app_identifier.lower()), None)
    else:
        current = get_current_app(interaction)
        if current:
            selected_app = next((a for a in apps if a['id'] == current['id']), None)
            
    if not selected_app:
        await interaction.response.send_message("❌ Application not found. Please provide a valid app ID or name.", ephemeral=True)
        return
        
    embed = discord.Embed(title="🔐 App Credentials (LegitAuth)", color=get_embed_color(selected_app))
    embed.add_field(name="App Name", value=selected_app['app_name'], inline=True)
    embed.add_field(name="App ID", value=str(selected_app['id']), inline=True)
    embed.add_field(name="Owner ID (UUID)", value=f"`{selected_app['owner_id']}`", inline=False)
    embed.add_field(name="App Secret", value=f"`{selected_app['secret']}`", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="register", description="Register this channel to receive logs and listen to commands")
async def register(interaction: discord.Interaction):
    token = user_tokens.get(str(interaction.user.id))
    if not token:
        await interaction.response.send_message("❌ Please link your LegitAuth API token first using `/link_token`.", ephemeral=True)
        return
        
    url_get = f"{API_BASE}/api/creator/discord/config"
    resp_get = requests.get(url_get, headers={"Authorization": f"Bearer {token}"})
    if resp_get.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch Discord configuration.", ephemeral=True)
        return
        
    config = resp_get.json()
    config["discord_channel_id"] = str(interaction.channel_id)
    config["discord_channel_name"] = interaction.channel.name
    config["discord_guild_id"] = str(interaction.guild_id)
    config["discord_guild_name"] = interaction.guild.name
    
    url_put = f"{API_BASE}/api/creator/discord/config"
    resp_put = requests.put(url_put, json=config, headers={"Authorization": f"Bearer {token}"})
    if resp_put.status_code == 200:
        await interaction.response.send_message("✅ This channel has been successfully registered to listen to bot commands and receive logs.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to register channel: {resp_put.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="hwid_reset", description="Reset your own user credentials HWID (if allowed by administrator)")
@app_commands.describe(username="Your username", password="Your password", app_id="Target application ID (optional)")
async def hwid_reset(interaction: discord.Interaction, username: str, password: str, app_id: Optional[int] = None):
    payload = {
        "username": username,
        "password": password,
        "app_id": app_id
    }
    url = f"{API_BASE}/api/creator/discord/reset-member-hwid"
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        app = get_current_app(interaction)
        embed = discord.Embed(
            title="🔄 HWID Reset Successful",
            description=f"Your HWID has been successfully reset. You can now login on your new machine.",
            color=get_embed_color(app)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        err = resp.json().get("detail", "Failed to reset HWID. Please check credentials or contact administrator.")
        await interaction.response.send_message(f"❌ {err}", ephemeral=True)

@tree.command(name="license_reset", description="Reset your license key HWID (if allowed by administrator)")
@app_commands.describe(license_key="Your license key", app_id="Target application ID (optional)")
async def license_reset(interaction: discord.Interaction, license_key: str, app_id: Optional[int] = None):
    payload = {
        "license_key": license_key,
        "app_id": app_id
    }
    url = f"{API_BASE}/api/creator/discord/reset-member-license"
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        app = get_current_app(interaction)
        embed = discord.Embed(
            title="🔄 HWID Reset Successful",
            description=f"Your license key **{license_key}** HWID has been successfully reset. You can now login.",
            color=get_embed_color(app)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        err = resp.json().get("detail", "Failed to reset HWID. Please check key or contact administrator.")
        await interaction.response.send_message(f"❌ {err}", ephemeral=True)


# Welcome new members handler
@client.event
async def on_member_join(member: discord.Member):
    """Welcome new members if enabled in the app configuration."""
    try:
        url = f"{API_BASE}/api/creator/discord/app-by-guild/{member.guild.id}"
        resp = requests.get(url, headers=api_headers())
        if resp.status_code == 200:
            app = resp.json()
            if app.get("discord_welcome_enabled"):
                # Send welcome message
                channel_id = app.get("discord_welcome_channel_id")
                if channel_id:
                    channel = member.guild.get_channel(int(channel_id))
                    if channel:
                        await channel.send(app.get("discord_welcome_msg", "Welcome to the server!"))
                # Assign role
                role_id = app.get("discord_role_on_register")
                if role_id:
                    role = member.guild.get_role(int(role_id))
                    if role:
                        await member.add_roles(role)
    except Exception as e:
        print(f"Error in welcome handler: {e}")

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# Bot token should be stored in .env as DISCORD_BOT_TOKEN
if __name__ == "__main__":
    client.run(os.getenv("DISCORD_BOT_TOKEN"))
