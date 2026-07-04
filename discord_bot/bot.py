import os
import json
import asyncio
from typing import Optional
import discord
from discord import app_commands
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("LEGITAUTH_API_URL", "https://legitauth1-3.onrender.com")
DEFAULT_API_TOKEN = os.getenv("LEGITAUTH_API_TOKEN")  # Fallback for owner
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
@app_commands.describe(username="New username", password="Password", expires_at="ISO datetime or leave blank", hw_id_lock="Lock to HWID (true/false)")
async def create_user(interaction: discord.Interaction, username: str, password: str, expires_at: Optional[str] = None, hw_id_lock: bool = True):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel. Use `/select_app <app_id>` first or link this channel in the dashboard.", ephemeral=True)
        return
    
    app_id = app["id"]
    payload = {
        "username": username,
        "password": password,
        "expires_at": expires_at,
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
@app_commands.describe(amount="Number of licenses", duration_days="Duration in days (0 = lifetime)", expires_at="ISO datetime or leave blank", hw_id_lock="Lock to HWID (true/false)")
async def create_license(interaction: discord.Interaction, amount: int, duration_days: int = 0, expires_at: Optional[str] = None, hw_id_lock: bool = True):
    app = get_current_app(interaction)
    if not app:
        await interaction.response.send_message("No app selected or linked to this channel. Use `/select_app <app_id>` first or link this channel in the dashboard.", ephemeral=True)
        return
    
    app_id = app["id"]
    payload = {
        "amount": amount,
        "duration_days": duration_days,
        "expires_at": expires_at,
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

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")

# Bot token should be stored in .env as DISCORD_BOT_TOKEN
client.run(os.getenv("DISCORD_BOT_TOKEN"))
