import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Fake in-memory VPS storage
vps_list = []

async def loading_message(ctx, text, emoji="⏳"):
    """Send animated loading message"""
    msg = await ctx.send(f"{emoji} {text}.")
    for i in range(3):
        await asyncio.sleep(0.5)
        await msg.edit(content=f"{emoji} {text}{'.'*(i+1)}")
    return msg

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    activity = discord.Game(name="!kvm-help")
    await bot.change_presence(activity=activity)

# -----------------------------------
# HELP
# -----------------------------------
@bot.command(name="kvm-help")
async def kvm_help(ctx):
    help_text = """
📖 **KVM Bot Commands**
------------------------------------
⚡ `!create-vps <@user>` → Create a VPS for someone & DM them details  
📋 `!kvm-list` → Show all VPS and their owners  
🏓 `!ping` → Check if bot is alive  
❓ `!kvm-help` → Show this help message
------------------------------------
"""
    await ctx.send(help_text)

# -----------------------------------
# PING
# -----------------------------------
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! I'm alive 🚀")

# -----------------------------------
# CREATE VPS
# -----------------------------------
@bot.command(name="create-vps")
async def create_vps(ctx, owner: str):
    msg = await loading_message(ctx, "Creating VPS", "🖥️")

    # Fake VPS info
    vps_info = {
        "owner": owner,
        "ssh": "ssh user@127.0.0.1 -p 22",
        "tmate": "tmate ssh session link here"
    }
    vps_list.append(vps_info)

    await msg.edit(content=f"✅ VPS created for **{owner}**!")

    # DM user with details
    try:
        await ctx.author.send(
            f"🔑 **Your VPS Details:**\n"
            f"```bash\n{vps_info['ssh']}\n```\n"
            f"🔗 Tmate: {vps_info['tmate']}"
        )
    except:
        await ctx.send("⚠️ Couldn’t DM VPS details.")

# -----------------------------------
# LIST VPS
# -----------------------------------
@bot.command(name="kvm-list")
async def kvm_list(ctx):
    if not vps_list:
        await ctx.send("📋 No VPS instances exist yet.")
        return

    text = "📋 **All VPS Instances:**\n"
    for i, vps in enumerate(vps_list, start=1):
        text += f"{i}. 🖥️ Owner: **{vps['owner']}** | SSH: `{vps['ssh']}`\n"

    await ctx.send(text)

# Run bot
bot.run(TOKEN)
