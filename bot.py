import os
import discord
import subprocess
from discord.ext import commands
from dotenv import load_dotenv

# Load env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Store VPS owners
vps_map = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    activity = discord.Game(name="!kvm-help | VPS Creator 🖥️")
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.command()
async def kvm_help(ctx):
    help_text = """
📖 **VPS Bot Help** 📖
✨ `!create-vps @user` → Create a VPS and DM tmate link  
📋 `!kvm-list` → Show all VPS with owners  
🏓 `!ping` → Test bot  
"""
    await ctx.send(help_text)

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! The bot is alive!")

@bot.command()
async def create_vps(ctx, owner: discord.Member):
    uname = owner.name.lower()
    cname = f"vps_{uname}"

    await ctx.send(f"⚙️ Creating VPS for {owner.mention} ... this may take 5–10s ⏳")

    try:
        # Run Ubuntu container
        subprocess.run(["docker", "run", "-d", "--name", cname, "ubuntu:20.04", "sleep", "infinity"], check=True)

        # Install tmate inside
        subprocess.run(["docker", "exec", cname, "apt-get", "update"], check=True)
        subprocess.run(["docker", "exec", cname, "apt-get", "install", "-y", "tmate", "openssh-client"], check=True)

        # Generate tmate session
        session = subprocess.check_output(
            ["docker", "exec", cname, "tmate", "-S", "/tmp/tmate.sock", "new-session", "-d"],
        )
        subprocess.run(["docker", "exec", cname, "tmate", "-S", "/tmp/tmate.sock", "wait", "tmate-ready"], check=True)
        ssh_link = subprocess.check_output(
            ["docker", "exec", cname, "tmate", "-S", "/tmp/tmate.sock", "display", "-p", "#{tmate_ssh}"]
        ).decode().strip()

        vps_map[cname] = owner.mention

        # DM the user
        await owner.send(f"🔑 **Your VPS is ready!**\n\n`{ssh_link}`")
        await ctx.send(f"🎉 VPS for {owner.mention} created successfully!")

    except Exception as e:
        await ctx.send(f"❌ Error creating VPS: {e}")

@bot.command()
async def kvm_list(ctx):
    if not vps_map:
        await ctx.send("📂 No VPS created yet!")
    else:
        msg = "📋 **Active VPS List** 📋\n"
        for cname, owner in vps_map.items():
            msg += f"🖥️ `{cname}` → {owner}\n"
        await ctx.send(msg)

bot.run(TOKEN)
