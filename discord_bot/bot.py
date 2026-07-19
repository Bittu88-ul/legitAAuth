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
intents.members = True # Ensure members intent is active for join events
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

def get_linked_app(channel_id: int, user_id: int):
    url = f"{API_BASE}/api/creator/discord/app-by-channel/{channel_id}"
    try:
        resp = requests.get(url, headers=api_headers_for_user(user_id))
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def get_current_app(interaction: discord.Interaction):
    app = user_selected_app.get(interaction.user.id)
    if not app:
        app = get_linked_app(interaction.channel_id, interaction.user.id)
    return app

def is_token_linked(user_id: int) -> bool:
    user_id_str = str(user_id)
    return user_id_str in user_tokens or DEFAULT_API_TOKEN is not None

def resolve_app_for_user(user_id: int, app_identifier: Optional[str] = None, channel_id: Optional[int] = None):
    headers = api_headers_for_user(user_id)
    url = f"{API_BASE}/api/creator/apps"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            apps = resp.json()
            if app_identifier:
                ident = app_identifier.strip().lower()
                for app in apps:
                    if str(app["id"]) == ident or app["app_name"].lower() == ident:
                        return app
            else:
                # Fallback to selected
                curr_app = user_selected_app.get(user_id)
                if curr_app:
                    match = next((a for a in apps if a["id"] == curr_app["id"]), None)
                    if match:
                        return match
                if channel_id:
                    linked = get_linked_app(channel_id, user_id)
                    if linked:
                        match = next((a for a in apps if a["id"] == linked["id"]), None)
                        if match:
                            return match
        else:
            return None
    except Exception as e:
        print(f"Error in resolve_app_for_user: {e}")
    return None

def find_license_across_apps(user_id: int, key: str):
    headers = api_headers_for_user(user_id)
    url = f"{API_BASE}/api/creator/apps"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            apps = resp.json()
            for app in apps:
                lic_url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses"
                lic_resp = requests.get(lic_url, headers=headers)
                if lic_resp.status_code == 200:
                    for lic in lic_resp.json():
                        if lic["license_key"].lower() == key.strip().lower():
                            return app, lic
    except Exception as e:
        print(f"Error in find_license_across_apps: {e}")
    return None, None

def find_user_across_apps(user_id: int, username: str):
    headers = api_headers_for_user(user_id)
    matches = []
    url = f"{API_BASE}/api/creator/apps"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            apps = resp.json()
            for app in apps:
                users_url = f"{API_BASE}/api/creator/apps/{app['id']}/users"
                users_resp = requests.get(users_url, headers=headers)
                if users_resp.status_code == 200:
                    for u in users_resp.json():
                        if u["username"].lower() == username.strip().lower():
                            matches.append((app, u))
    except Exception as e:
        print(f"Error in find_user_across_apps: {e}")
    return matches

def resolve_user_across_apps(user_id: int, username: str, app_identifier: Optional[str] = None):
    headers = api_headers_for_user(user_id)
    if app_identifier:
        app = resolve_app_for_user(user_id, app_identifier)
        if not app:
            return None, None, f"❌ App `{app_identifier}` nahi mila."
        users_url = f"{API_BASE}/api/creator/apps/{app['id']}/users"
        resp = requests.get(users_url, headers=headers)
        if resp.status_code == 200:
            user = next((u for u in resp.json() if u["username"].lower() == username.strip().lower()), None)
            if user:
                return app, user, None
            else:
                return app, None, f"❌ App `{app['app_name']}` mein User `{username}` nahi mila."
        else:
            return None, None, "❌ Failed to fetch users list for the specified app."
    else:
        matches = find_user_across_apps(user_id, username)
        if len(matches) == 1:
            return matches[0][0], matches[0][1], None
        elif len(matches) > 1:
            app_names = ", ".join([m[0]["app_name"] for m in matches])
            return None, None, f"⚠️ Multiple apps mein `{username}` mila ({app_names}). Kripya `app` parameter specifying karein."
        else:
            return None, None, f"❌ User `{username}` kisi bhi application mein nahi mila."


# --- Create Command Groups ---
class AppGroup(app_commands.Group, name="app", description="Application management commands"):
    pass

class LicenseGroup(app_commands.Group, name="license", description="License key management commands"):
    pass

class UserGroup(app_commands.Group, name="user", description="User management commands"):
    pass

app_group = AppGroup()
license_group = LicenseGroup()
user_group = UserGroup()


# --- root commands ---
@tree.command(name="link_token", description="Link your LegitAuth API token to use the bot")
@app_commands.describe(api_token="Your API token from LegitAuth Settings tab")
async def link_token(interaction: discord.Interaction, api_token: str):
    test_url = f"{API_BASE}/api/creator/apps"
    test_resp = requests.get(test_url, headers={"Authorization": f"Bearer {api_token}"})
    if test_resp.status_code != 200:
        await interaction.response.send_message("❌ Invalid token! Please check and try again.", ephemeral=True)
        return
    
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

@tree.command(name="select_app", description="Select an application to work with")
@app_commands.describe(app_id="Application ID")
async def select_app(interaction: discord.Interaction, app_id: int):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai. Pehle `/link_token` use karein.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Unable to verify app. Did you link your token?", ephemeral=True)
        return
    apps = resp.json()
    selected = next((a for a in apps if a["id"] == app_id), None)
    if not selected:
        await interaction.response.send_message("App ID not found under your account.", ephemeral=True)
        return
    user_selected_app[interaction.user.id] = selected
    await interaction.response.send_message(f"Selected app **{selected['app_name']}** (ID: {app_id}).", ephemeral=True)

@tree.command(name="register", description="Register the current channel with an app")
@app_commands.describe(app_id="Application ID")
async def register(interaction: discord.Interaction, app_id: int):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai. Pehle `/link_token` use karein.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_id}/discord"
    payload = {
        "discord_channel_id": str(interaction.channel_id),
        "discord_channel_name": interaction.channel.name if hasattr(interaction.channel, 'name') else "unknown",
        "discord_guild_id": str(interaction.guild_id) if interaction.guild_id else None,
        "discord_guild_name": interaction.guild.name if interaction.guild else None
    }
    resp = requests.put(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message("Channel registered successfully.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Registration failed: {resp.json().get('detail', 'unknown error')}", ephemeral=True)

@tree.command(name="help", description="Show available bot commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Help - LegitAuth Bot Commands", color=0x00FFAA)
    
    embed.add_field(
        name="📦 App Commands",
        value=(
            "`/app list` - Sabhi applications ki list dikhaye\n"
            "`/app create <name>` - Naya application create kare\n"
            "`/app delete <app>` - Selected app aur uska data delete kare\n"
            "`/app info [app]` - App ki basic information dikhaye\n"
            "`/app rename <old> <new>` - App ka naam change kare\n"
            "`/app reset-secret [app]` - App ka naya Secret generate kare\n"
            "`/app stats [app]` - App ke statistics dikhaye\n"
            "`/app credentials [app]` - App credentials dikhaye\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔑 License Commands",
        value=(
            "`/license create <duration> <count> [app]` - Ek/multiple licenses generate kare\n"
            "`/license delete <key>` - License key delete kare\n"
            "`/license info <key>` - License ki details dikhaye\n"
            "`/license extend <key> <days>` - License validity badhaye\n"
            "`/license ban <key>` - License ban kare\n"
            "`/license unban <key>` - License unban kare\n"
            "`/license reset-hwid <key>` - License HWID reset kare\n"
            "`/license reset-ip <key>` - License saved IP reset kare\n"
            "`/license search <query>` - User ya key se license search kare\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👤 User Commands",
        value=(
            "`/user create <username> <password> [app] [duration] [hwid_lock]` - User create kare\n"
            "`/user delete <username> [app]` - User delete kare\n"
            "`/user info <username> [app]` - User details dikhaye\n"
            "`/user ban <username> [app]` - User ban kare\n"
            "`/user unban <username> [app]` - User unban kare\n"
            "`/user reset-hwid <username> [app]` - User HWID reset kare\n"
            "`/user reset-password <username> <new_password> [app]` - User password reset kare\n"
            "`/user list [app]` - Registered users list dikhaye\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Configuration Commands",
        value=(
            "`/link_token <api_token>` - Link your LegitAuth API token\n"
            "`/unlink_token` - Unlink your LegitAuth API token\n"
            "`/select_app <app_id>` - Select active app manually\n"
            "`/register <app_id>` - Link this channel to an app\n"
        ),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Group: App (/app) ---
@app_group.command(name="create", description="Naya application create kare")
@app_commands.describe(name="App ka naam")
async def app_create(interaction: discord.Interaction, name: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai. Pehle `/link_token` use karein.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/create"
    resp = requests.post(url, json={"app_name": name}, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        data = resp.json()["app"]
        embed = discord.Embed(title="✅ Application Created", color=0x00FFAA)
        embed.add_field(name="Name", value=data["app_name"], inline=True)
        embed.add_field(name="App ID", value=str(data["id"]), inline=True)
        embed.add_field(name="Owner ID", value=f"`{data['owner_id']}`", inline=False)
        embed.add_field(name="Secret", value=f"`{data['secret']}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        detail = resp.json().get('detail', 'Unknown error')
        await interaction.response.send_message(f"❌ Failed: {detail}", ephemeral=True)

@app_group.command(name="delete", description="Selected app aur uska data delete kare")
@app_commands.describe(app="App name ya App ID")
async def app_delete(interaction: discord.Interaction, app: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app)
    if not matched_app:
        await interaction.response.send_message(f"❌ App `{app}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ App **{matched_app['app_name']}** (ID: {matched_app['id']}) aur uska data delete ho gaya.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@app_group.command(name="info", description="App ki basic information dikhaye")
@app_commands.describe(app="App name ya App ID (optional)")
async def app_info_cmd(interaction: discord.Interaction, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
    embed = discord.Embed(title=f"ℹ️ App Info: {matched_app['app_name']}", color=0x00AAFF)
    embed.add_field(name="App ID", value=str(matched_app['id']), inline=True)
    embed.add_field(name="Status", value=matched_app.get('status', 'active').capitalize(), inline=True)
    embed.add_field(name="Version", value=matched_app.get('version', '1.0'), inline=True)
    embed.add_field(name="Dev Message", value=matched_app.get('dev_message') or "None", inline=False)
    embed.add_field(name="Webhook URL", value=matched_app.get('webhook_url') or "None", inline=False)
    guild_name = matched_app.get("discord_guild_name") or "Not Linked"
    channel_name = matched_app.get("discord_channel_name") or "Not Linked"
    embed.add_field(name="Discord Link", value=f"Guild: {guild_name}\nChannel: {channel_name}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_group.command(name="list", description="Sabhi applications ki list dikhaye")
async def app_list(interaction: discord.Interaction):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch apps.", ephemeral=True)
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

@app_group.command(name="rename", description="App ka naam change kare")
@app_commands.describe(old="Puraana app name ya App ID", new="Naya app name")
async def app_rename(interaction: discord.Interaction, old: str, new: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, old)
    if not matched_app:
        await interaction.response.send_message(f"❌ App `{old}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}/rename?new_name={new}"
    resp = requests.put(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ App renamed successfully to **{new}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@app_group.command(name="reset-secret", description="App ka naya Secret generate kare")
@app_commands.describe(app="App name ya App ID (optional)")
async def app_reset_secret(interaction: discord.Interaction, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}/reset-secret"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        new_secret = resp.json()["secret"]
        await interaction.response.send_message(f"✅ App **{matched_app['app_name']}** ka Secret successfully reset ho gaya hai:\n`{new_secret}`", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@app_group.command(name="stats", description="App ke users, licenses aur usage statistics dikhaye")
@app_commands.describe(app="App name ya App ID (optional)")
async def app_stats(interaction: discord.Interaction, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
    
    app_id = matched_app["id"]
    headers = api_headers_for_user(interaction.user.id)
    users_url = f"{API_BASE}/api/creator/apps/{app_id}/users"
    lics_url = f"{API_BASE}/api/creator/apps/{app_id}/licenses"
    
    users_resp = requests.get(users_url, headers=headers)
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
    
    embed = discord.Embed(title=f"📊 Statistics: {matched_app['app_name']}", color=0x00FF88)
    embed.add_field(name="App Status", value=f"• **Status:** {matched_app.get('status', 'Unknown').capitalize()}\n• **Version:** {matched_app.get('version', '1.0')}", inline=False)
    embed.add_field(name="Users", value=f"• **Total:** {total_users}\n• **Active:** {active_users_count}\n• **Banned:** {banned_users_count}", inline=True)
    embed.add_field(name="Licenses", value=f"• **Total:** {total_lics}\n• **Active:** {active_lics_count}\n• **Banned:** {banned_lics_count}\n• **Unused:** {unused_lics_count}", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_group.command(name="credentials", description="App Name, App ID, Owner ID aur Secret dikhaye")
@app_commands.describe(app="App name ya App ID (optional)")
async def app_credentials(interaction: discord.Interaction, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ Application not found. Please provide a valid app ID or name.", ephemeral=True)
        return
        
    embed = discord.Embed(title="🔐 App Credentials (LegitAuth)", color=0x00FFAA)
    embed.add_field(name="App Name", value=matched_app['app_name'], inline=True)
    embed.add_field(name="App ID", value=str(matched_app['id']), inline=True)
    embed.add_field(name="Owner ID (UUID)", value=f"`{matched_app['owner_id']}`", inline=False)
    embed.add_field(name="App Secret", value=f"`{matched_app['secret']}`", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Group: License (/license) ---
@license_group.command(name="create", description="Ek ya multiple license keys generate kare")
@app_commands.describe(duration="Validity (e.g. 30, 7d, lifetime)", count="Kitne keys generate karne hai", app="App name ya App ID (optional)")
async def license_create(interaction: discord.Interaction, duration: str, count: int, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
    
    duration_days = 0
    expires_at = None
    if duration.strip().isdigit():
        duration_days = int(duration.strip())
    elif duration.strip().lower() in ("lifetime", "never", "0"):
        duration_days = 0
    else:
        expires_at = parse_expiry(duration)
        
    payload = {
        "amount": count,
        "duration_days": duration_days,
        "expires_at": expires_at,
        "hwid_lock_enabled": True
    }
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}/licenses"
    resp = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        data = resp.json()
        keys = "\n".join([f"`{k}`" for k in data.get("keys", [])])
        await interaction.response.send_message(f"✅ Generated {count} license(s) for **{matched_app['app_name']}**:\n\n{keys}\n", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="delete", description="License key delete kare")
@app_commands.describe(key="License key")
async def license_delete(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` kisi bhi app mein nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ License `{key}` successfully delete ho gaya (App: {app['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="info", description="License ki details dikhaye")
@app_commands.describe(key="License key")
async def license_info(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    embed = discord.Embed(title="🔑 License Details", color=0xFFBB00)
    embed.add_field(name="App Name", value=app['app_name'], inline=True)
    embed.add_field(name="Key", value=f"`{lic['license_key']}`", inline=False)
    embed.add_field(name="License ID", value=str(lic['id']), inline=True)
    embed.add_field(name="Status", value=lic['status'].capitalize(), inline=True)
    embed.add_field(name="Locked HWID", value=lic.get('hwid') or "Not Set", inline=False)
    embed.add_field(name="Last IP", value=lic.get('last_ip') or "None", inline=True)
    embed.add_field(name="Duration (Days)", value=str(lic.get('duration_days', 0)), inline=True)
    embed.add_field(name="Expires At", value=lic.get('expires_at') or "Lifetime", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@license_group.command(name="extend", description="License ki validity badhaye")
@app_commands.describe(key="License key", days="Kitne din se extend karna hai")
async def license_extend(interaction: discord.Interaction, key: str, days: int):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}/extend?days={days}"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        data = resp.json()
        await interaction.response.send_message(f"✅ License `{key}` successfully extend ho gaya by {days} days (Naya Expiry: {data.get('new_expiry')}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="ban", description="License ko ban kare")
@app_commands.describe(key="License key")
async def license_ban(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}/ban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ License `{key}` ko ban kar diya gaya hai.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="unban", description="Banned license ko unban kare")
@app_commands.describe(key="License key")
async def license_unban(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}/unban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ License `{key}` ko unban kar diya gaya hai.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="reset-hwid", description="License ka HWID reset kare")
@app_commands.describe(key="License key")
async def license_reset_hwid(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}/reset-hwid"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ License `{key}` ka HWID reset ho gaya hai.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="reset-ip", description="License ki saved IP reset kare")
@app_commands.describe(key="License key")
async def license_reset_ip(interaction: discord.Interaction, key: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app, lic = find_license_across_apps(interaction.user.id, key)
    if not lic:
        await interaction.response.send_message(f"❌ License key `{key}` nahi mila.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app['id']}/licenses/{lic['id']}/reset-ip"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ License `{key}` ki saved IP reset ho gayi hai.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@license_group.command(name="search", description="User ya key se license search kare")
@app_commands.describe(query="License Key ya User ka username")
async def license_search(interaction: discord.Interaction, query: str):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    
    app_lic, lic = find_license_across_apps(interaction.user.id, query)
    if lic:
        embed = discord.Embed(title="🔑 License Found by Key", color=0x00FF55)
        embed.add_field(name="App", value=app_lic['app_name'], inline=True)
        embed.add_field(name="Key", value=f"`{lic['license_key']}`", inline=False)
        embed.add_field(name="Status", value=lic['status'].capitalize(), inline=True)
        embed.add_field(name="HWID", value=lic.get('hwid') or "Not Set", inline=False)
        embed.add_field(name="Last IP", value=lic.get('last_ip') or "None", inline=True)
        embed.add_field(name="Expires", value=lic.get('expires_at') or "Lifetime", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
        
    user_matches = find_user_across_apps(interaction.user.id, query)
    if user_matches:
        app_usr, usr = user_matches[0]
        embed = discord.Embed(title=f"👤 User Found by Username: {usr['username']}", color=0x00AAFF)
        embed.add_field(name="App", value=app_usr['app_name'], inline=True)
        embed.add_field(name="User ID", value=str(usr['id']), inline=True)
        embed.add_field(name="Status", value=usr['status'].capitalize(), inline=True)
        embed.add_field(name="HWID", value=usr.get('hwid') or "Not Set", inline=False)
        embed.add_field(name="Last IP", value=usr.get('last_ip') or "None", inline=True)
        embed.add_field(name="Expires", value=usr.get('expires_at') or "Lifetime", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
        
    await interaction.response.send_message(f"❌ No licenses or users found matching `{query}`.", ephemeral=True)


# --- Group: User (/user) ---
@user_group.command(name="create", description="Naya user manually create kare")
@app_commands.describe(username="Username", password="Password", app="App name ya App ID (optional)", duration="Validity (e.g. 30d, 7d, lifetime)", hwid_lock="Lock to HWID (True/False)")
async def user_create(interaction: discord.Interaction, username: str, password: str, app: Optional[str] = None, duration: Optional[str] = None, hwid_lock: bool = True):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
        
    parsed_expiry = parse_expiry(duration)
    payload = {
        "username": username,
        "password": password,
        "expires_at": parsed_expiry,
        "hwid_lock_enabled": hwid_lock,
    }
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}/users"
    resp = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User **{username}** created successfully for application **{matched_app['app_name']}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="delete", description="User account delete kare")
@app_commands.describe(username="Username", app="App name ya App ID (optional)")
async def user_delete(interaction: discord.Interaction, username: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_obj['id']}/users/{user['id']}"
    resp = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User `{username}` successfully delete ho gaya (App: {app_obj['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="info", description="User ki profile aur account details dikhaye")
@app_commands.describe(username="Username", app="App name ya App ID (optional)")
async def user_info(interaction: discord.Interaction, username: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    embed = discord.Embed(title=f"👤 User Details: {user['username']}", color=0x00FF55)
    embed.add_field(name="App Name", value=app_obj['app_name'], inline=True)
    embed.add_field(name="User ID", value=str(user['id']), inline=True)
    embed.add_field(name="Status", value=user['status'].capitalize(), inline=True)
    embed.add_field(name="Locked HWID", value=user.get('hwid') or "Not Set", inline=False)
    embed.add_field(name="Last IP", value=user.get('last_ip') or "None", inline=True)
    embed.add_field(name="Expires At", value=user.get('expires_at') or "Lifetime", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@user_group.command(name="ban", description="User account ban kare")
@app_commands.describe(username="Username", app="App name ya App ID (optional)")
async def user_ban(interaction: discord.Interaction, username: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_obj['id']}/users/{user['id']}/ban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User `{username}` successfully ban ho gaya (App: {app_obj['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="unban", description="User account se ban remove kare")
@app_commands.describe(username="Username", app="App name ya App ID (optional)")
async def user_unban(interaction: discord.Interaction, username: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_obj['id']}/users/{user['id']}/unban"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User `{username}` successfully unban ho gaya (App: {app_obj['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="reset-hwid", description="User ka HWID reset kare")
@app_commands.describe(username="Username", app="App name ya App ID (optional)")
async def user_reset_hwid(interaction: discord.Interaction, username: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_obj['id']}/users/{user['id']}/reset-hwid"
    resp = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User `{username}` ka HWID reset ho gaya (App: {app_obj['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="reset-password", description="User ka password reset kare")
@app_commands.describe(username="Username", new_password="Naya password", app="App name ya App ID (optional)")
async def user_reset_password(interaction: discord.Interaction, username: str, new_password: str, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    app_obj, user, err = resolve_user_across_apps(interaction.user.id, username, app)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{app_obj['id']}/users/{user['id']}/password"
    resp = requests.put(url, json={"new_password": new_password}, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code == 200:
        await interaction.response.send_message(f"✅ User `{username}` ka password reset ho gaya (App: {app_obj['app_name']}).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed: {resp.json().get('detail', 'Unknown error')}", ephemeral=True)

@user_group.command(name="list", description="Sabhi registered users ki list dikhaye")
@app_commands.describe(app="App name ya App ID (optional)")
async def user_list(interaction: discord.Interaction, app: Optional[str] = None):
    if not is_token_linked(interaction.user.id):
        await interaction.response.send_message("❌ Token link nahi hai.", ephemeral=True)
        return
    matched_app = resolve_app_for_user(interaction.user.id, app, interaction.channel_id)
    if not matched_app:
        await interaction.response.send_message("❌ App nahi mila. Kripya app specify karein ya `/select_app` use karein.", ephemeral=True)
        return
    url = f"{API_BASE}/api/creator/apps/{matched_app['id']}/users"
    resp = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if resp.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users.", ephemeral=True)
        return
    users = resp.json()
    if not users:
        await interaction.response.send_message(f"App **{matched_app['app_name']}** mein koi user nahi mila.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Users for {matched_app['app_name']}", color=0x00AAFF)
    for u in users[:25]:
        embed.add_field(
            name=f"{u['username']} (ID: {u['id']})",
            value=f"Status: {u['status']}\nHWID: {u['hwid'] or 'Not set'}\nExpires: {u['expires_at']}",
            inline=False
        )
    if len(users) > 25:
        embed.set_footer(text=f"Showing 25 of {len(users)} users.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Register Groups inside CommandTree ---
tree.add_command(app_group)
tree.add_command(license_group)
tree.add_command(user_group)


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
