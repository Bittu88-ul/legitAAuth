import discord
from discord import app_commands
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
API_BASE = os.getenv('LEGITAUTH_API_URL', 'http://localhost:8000/api/creator')
DEFAULT_API_TOKEN = os.getenv('DEFAULT_API_TOKEN', '')

# File to store user tokens
USER_TOKENS_FILE = os.path.join(os.path.dirname(__file__), "user_tokens.json")
USER_SELECTED_APP_FILE = os.path.join(os.path.dirname(__file__), "user_selected_app.json")

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

def load_user_selected_apps():
    if os.path.exists(USER_SELECTED_APP_FILE):
        try:
            with open(USER_SELECTED_APP_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading user selected apps: {e}")
            return {}
    return {}

def save_user_selected_apps(apps):
    with open(USER_SELECTED_APP_FILE, "w") as f:
        json.dump(apps, f)

# Load tokens on start
user_tokens: dict[str, str] = load_user_tokens()
user_selected_app: dict[str, dict] = load_user_selected_apps()

def api_headers_for_user(user_id: int):
    user_id_str = str(user_id)
    token = user_tokens.get(user_id_str, DEFAULT_API_TOKEN)
    return {"Authorization": f"Bearer {token}"}

def get_linked_app(channel_id: int, user_id: int):
    url = f"{API_BASE}/discord/app-by-channel/{channel_id}"
    try:
        res = requests.get(url, headers=api_headers_for_user(user_id))
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error getting linked app: {e}")
        pass
    return None

def get_current_app(interaction: discord.Interaction):
    user_id_str = str(interaction.user.id)
    # First check if user selected an app manually
    if user_id_str in user_selected_app:
        return user_selected_app[user_id_str]
    # Then check if channel is linked
    return get_linked_app(interaction.channel_id, interaction.user.id)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# List of commands that don't require an app at all
COMMANDS_NO_APP_NEEDED = ["help", "link_token", "unlink_token", "list_apps", "select_app", "ping", "info"]

def check_command_allowed(interaction: discord.Interaction):
    if not interaction.command:
        return True, None
    command_name = interaction.command.name
    if command_name in COMMANDS_NO_APP_NEEDED:
        return True, None
    
    app = get_current_app(interaction)
    if not app:
        return False, "Please use `/select_app <app_id>` to choose an app first, or link a channel in the dashboard!"
    
    # Check channel restriction only if the app has a linked channel
    if app.get("discord_channel_id"):
        if str(interaction.channel_id) != app["discord_channel_id"]:
            return False, f"This bot only works in <#{app['discord_channel_id']}> for the app **{app['app_name']}**!"
    
    return True, None

# --- Bot Events ---
@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# --- Bot Commands ---

@tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="LegitAuth Bot Help", color=0x5865F2)
    embed.add_field(name="🔑 Authentication Commands", value=(
        "/link_token [token] - Link your LegitAuth API token\n"
        "/unlink_token - Unlink your API token\n"
    ), inline=False)
    embed.add_field(name="📱 App Management", value=(
        "/list_apps - List all your apps\n"
        "/select_app [app_id] - Select an app to manage\n"
    ), inline=False)
    embed.add_field(name="👥 User Management", value=(
        "/create_user [username] [password] [expires_at(optional)] [hwid_lock(optional)] - Create a new user\n"
        "/list_users - List all users for the selected app\n"
        "/delete_user [user_id] - Delete a user\n"
        "/reset_user_hwid [user_id] - Reset a user's HWID\n"
        "/toggle_user_ban [user_id] - Ban/Unban a user\n"
    ), inline=False)
    embed.add_field(name="🔑 License Management", value=(
        "/create_license [amount] [duration_days(optional)] [expires_at(optional)] [hwid_lock(optional)] - Generate licenses\n"
        "/list_licenses - List all licenses for the selected app\n"
        "/delete_license [license_id] - Delete a license\n"
        "/reset_license_hwid [license_id] - Reset a license's HWID\n"
        "/toggle_license_ban [license_id] - Ban/Unban a license\n"
    ), inline=False)
    embed.add_field(name="📊 Other Commands", value=(
        "/list_logs - Show recent activity logs\n"
        "/ping - Check bot latency\n"
        "/info - Show bot info\n"
    ), inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping", description="Check the bot's latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓 Latency: {latency}ms")

@tree.command(name="info", description="Show information about the bot")
async def info(interaction: discord.Interaction):
    embed = discord.Embed(title="LegitAuth Bot Info", color=0x10b981)
    embed.add_field(name="Bot Name", value=client.user.name, inline=True)
    embed.add_field(name="Latency", value=f"{round(client.latency * 1000)}ms", inline=True)
    embed.add_field(name="Server Count", value=f"{len(client.guilds)}", inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="link_token", description="Link your LegitAuth API token to use the bot")
@app_commands.describe(api_token="Your API token from LegitAuth Dashboard's Discord tab")
async def link_token(interaction: discord.Interaction, api_token: str):
    # Test if token is valid
    test_url = f"{API_BASE}/apps"
    test_res = requests.get(test_url, headers={"Authorization": f"Bearer {api_token}"})
    if test_res.status_code != 200:
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
    if user_id_str in user_selected_app:
        del user_selected_app[user_id_str]
        save_user_selected_apps(user_selected_app)
    await interaction.response.send_message("✅ Token unlinked successfully.", ephemeral=True)

@tree.command(name="list_apps", description="List your LegitAuth applications")
async def list_apps(interaction: discord.Interaction):
    url = f"{API_BASE}/apps"
    res = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code != 200:
        await interaction.response.send_message("❌ Could not load apps! Did you link your token with `/link_token`?", ephemeral=True)
        return
    apps = res.json()
    if not apps:
        await interaction.response.send_message("You have no applications yet! Create one in the LegitAuth dashboard first.", ephemeral=True)
        return
    embed = discord.Embed(title="Your Applications", color=0x5865F2)
    for app in apps:
        guild_name = app.get("discord_guild_name", "Not linked")
        channel_name = app.get("discord_channel_name", "Not linked")
        embed.add_field(
            name=f"{app['app_name']} (ID: {app['id']})",
            value=f"Status: {app.get('status', 'Active')}\nLinked Discord: {guild_name} #{channel_name}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="select_app", description="Select an application to manage")
@app_commands.describe(app_id="Application ID from `/list_apps`")
async def select_app(interaction: discord.Interaction, app_id: int):
    url = f"{API_URL}/apps"
    res = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code != 200:
        await interaction.response.send_message("❌ Could not verify app! Did you link your token with `/link_token`?", ephemeral=True)
        return
    apps = res.json()
    selected = next((a for a in apps if a["id"] == app_id), None)
    if not selected:
        await interaction.response.send_message("App ID not found under your account! Use `/list_apps` to see available apps.", ephemeral=True)
        return
    user_id_str = str(interaction.user.id)
    user_selected_app[user_id_str] = selected
    save_user_selected_apps(user_selected_app)
    await interaction.response.send_message(f"✅ Selected app **{selected['app_name']}**! You can now use all management commands.", ephemeral=True)

@tree.command(name="create_user", description="Create a new user for the selected app")
@app_commands.describe(
    username="New username",
    password="Password for the user",
    expires_at="Optional: Expiry date and time (e.g. 2026-12-31 23:59)",
    hwid_lock="Optional: Lock user to HWID (True/False, default: True)"
)
async def create_user(interaction: discord.Interaction, username: str, password: str, expires_at: str = None, hwid_lock: bool = True):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    payload = {
        "username": username,
        "password": password,
        "hwid_lock_enabled": hwid_lock,
    }
    if expires_at:
        payload["expires_at"] = expires_at
    
    url = f"{API_BASE}/apps/{app_id}/users"
    res = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message(f"✅ User **{username}** created successfully for **{app['app_name']}**!", ephemeral=True)
    else:
        error_detail = res.json().get('detail', 'Unknown error') if res.content else 'Unknown error'
        await interaction.response.send_message(f"❌ Failed to create user: {error_detail}", ephemeral=True)

@tree.command(name="list_users", description="List all users for the selected app")
async def list_users(interaction: discord.Interaction):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/users"
    res = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch users.", ephemeral=True)
        return
    users = res.json()
    if not users:
        await interaction.response.send_message("No users found for this app yet!", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"Users for {app['app_name']}", color=0x38bdf8)
    for u in users[:25]:  # Limit to first 25 to avoid embed size issues
        status_badge = "🔴 BANNED" if u.get("status") == "banned" else "🟢 ACTIVE"
        hwid_text = u.get("hwid", "Not Set") if u.get("hwid") else "Not Set"
        embed.add_field(
            name=f"{u['username']} (ID: {u['id']})",
            value=f"Status: {status_badge}\nHWID: {hwid_text[:20]}{'...' if len(hwid_text) > 20 else ''}\nExpires: {u.get('expires_at', 'Lifetime')}",
            inline=False
        )
    if len(users) > 25:
        embed.set_footer(text=f"Showing 25 of {len(users)} users")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="delete_user", description="Delete a user from the selected app")
@app_commands.describe(user_id="User ID from `/list_users`")
async def delete_user(interaction: discord.Interaction, user_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/users/{user_id}"
    res = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ User deleted successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to delete user!", ephemeral=True)

@tree.command(name="reset_user_hwid", description="Reset HWID for a user")
@app_commands.describe(user_id="User ID from `/list_users`")
async def reset_user_hwid(interaction: discord.Interaction, user_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/users/{user_id}/reset-hwid"
    res = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ User HWID reset successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to reset HWID!", ephemeral=True)

@tree.command(name="toggle_user_ban", description="Ban or unban a user")
@app_commands.describe(user_id="User ID from `/list_users`")
async def toggle_user_ban(interaction: discord.Interaction, user_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/users/{user_id}/toggle-ban"
    res = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ User ban status toggled successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to toggle ban status!", ephemeral=True)

@tree.command(name="create_license", description="Generate licenses for the selected app")
@app_commands.describe(
    amount="Number of licenses to generate",
    duration_days="Optional: Number of days the license is valid (0 = lifetime)",
    expires_at="Optional: Specific expiry date (e.g. 2026-12-31 23:59)",
    hwid_lock="Optional: Lock license to HWID (True/False, default: True)"
)
async def create_license(interaction: discord.Interaction, amount: int, duration_days: int = 0, expires_at: str = None, hwid_lock: bool = True):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    payload = {
        "amount": amount,
        "duration_days": duration_days,
        "hwid_lock_enabled": hwid_lock,
    }
    if expires_at:
        payload["expires_at"] = expires_at
    
    url = f"{API_BASE}/apps/{app_id}/licenses"
    res = requests.post(url, json=payload, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        data = res.json()
        keys = data.get("keys", [])
        keys_text = "\n".join(keys)
        await interaction.response.send_message(f"✅ Generated {amount} license(s) for **{app['app_name']}**:\n```\n{keys_text}\n```", ephemeral=True)
    else:
        error_detail = res.json().get('detail', 'Unknown error') if res.content else 'Unknown error'
        await interaction.response.send_message(f"❌ Failed to generate licenses: {error_detail}", ephemeral=True)

@tree.command(name="list_licenses", description="List all licenses for the selected app")
async def list_licenses(interaction: discord.Interaction):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/licenses"
    res = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch licenses.", ephemeral=True)
        return
    licenses = res.json()
    if not licenses:
        await interaction.response.send_message("No licenses found for this app yet!", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"Licenses for {app['app_name']}", color=0xf59e0b)
    for l in licenses[:25]:  # Limit to first 25 to avoid embed size issues
        status_badge = "🔴 BANNED" if l.get("status") == "banned" else "🟢 ACTIVE"
        hwid_text = l.get("hwid", "Not Set") if l.get("hwid") else "Not Set"
        embed.add_field(
            name=f"{l['license_key']} (ID: {l['id']})",
            value=f"Status: {status_badge}\nHWID: {hwid_text[:20]}{'...' if len(hwid_text) > 20 else ''}\nExpires: {l.get('expires_at', 'Lifetime')}",
            inline=False
        )
    if len(licenses) > 25:
        embed.set_footer(text=f"Showing 25 of {len(licenses)} licenses")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="delete_license", description="Delete a license from the selected app")
@app_commands.describe(license_id="License ID from `/list_licenses`")
async def delete_license(interaction: discord.Interaction, license_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/licenses/{license_id}"
    res = requests.delete(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ License deleted successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to delete license!", ephemeral=True)

@tree.command(name="reset_license_hwid", description="Reset HWID for a license")
@app_commands.describe(license_id="License ID from `/list_licenses`")
async def reset_license_hwid(interaction: discord.Interaction, license_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/licenses/{license_id}/reset-hwid"
    res = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ License HWID reset successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to reset HWID!", ephemeral=True)

@tree.command(name="toggle_license_ban", description="Ban or unban a license")
@app_commands.describe(license_id="License ID from `/list_licenses`")
async def toggle_license_ban(interaction: discord.Interaction, license_id: int):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/licenses/{license_id}/toggle-ban"
    res = requests.post(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code == 200:
        await interaction.response.send_message("✅ License ban status toggled successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Failed to toggle ban status!", ephemeral=True)

@tree.command(name="list_logs", description="Show recent activity logs for the selected app")
async def list_logs(interaction: discord.Interaction):
    allowed, error_msg = check_command_allowed(interaction)
    if not allowed:
        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        return
    
    app = get_current_app(interaction)
    app_id = app["id"]
    
    url = f"{API_BASE}/apps/{app_id}/logs"
    res = requests.get(url, headers=api_headers_for_user(interaction.user.id))
    if res.status_code != 200:
        await interaction.response.send_message("❌ Failed to fetch logs.", ephemeral=True)
        return
    logs = res.json()
    if not logs:
        await interaction.response.send_message("No logs found for this app yet!", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"Recent Logs for {app['app_name']}", color=0xef4444)
    for log in logs[:25]:  # Limit to first 25
        embed.add_field(
            name=f"{log['action']} - {log['created_at']}",
            value=f"{log['description']}",
            inline=False
        )
    if len(logs) > 25:
        embed.set_footer(text=f"Showing 25 of {len(logs)} logs")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot
client.run(TOKEN)
