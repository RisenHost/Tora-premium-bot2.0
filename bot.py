#!/usr/bin/env python3
"""
Discord VPS Creator — tmate-only, docker-based
Commands (prefix !):
 - !create-vps @user         (admin only) -> create a container with tmate, DM user the tmate SSH/Web link
 - !kvm-list                 -> list all VPS (containers) and owners
 - !kvm-ssh <container>      -> print tmate SSH/Web block from container
 - !kvm-start/stop/restart   -> manage container lifecycle
 - !kvm-logs <container>     -> tail logs
 - !kvm-destroy <container>  -> remove container (confirmation required)
 - !kvm-help                 -> help menu
"""

import os
import shlex
import subprocess
import asyncio
import textwrap
import random
import string
from typing import Optional, List
from dataclasses import dataclass

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")
VPS_IMAGE = os.getenv("VPS_IMAGE", "ubuntu-22.04-with-tmate")
DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Emojis / icons
E_OK = "✅"
E_WARN = "⚠️"
E_WORK = "🛠️"
E_PC = "🖥️"
E_KEY = "🔑"
E_LIST = "📜"
E_TRASH = "🗑️"
E_CLOCK = "⌛"
E_SPARK = "✨"

@dataclass
class VPSInfo:
    id: str
    name: str
    owner_id: int
    owner_tag: str
    image: str
    status: str

# -------------------------
# Helpers
# -------------------------
def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run command safely and return CompletedProcess (no exceptions)."""
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 124, stdout=e.stdout or "", stderr="timeout")

def rand_suffix(n: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def spinner_edit(msg: discord.Message, base: str, emoji: str = "⏳", cycles: int = 6, delay: float = 0.35):
    """Edit a message with a small dot animation."""
    dots = ["", ".", "..", "..."]
    for i in range(cycles):
        await asyncio.sleep(delay)
        try:
            await msg.edit(content=f"{emoji} {base}{dots[i % len(dots)]}")
        except Exception:
            pass

def docker_list_containers() -> List[VPSInfo]:
    proc = run([DOCKER_BIN, "ps", "-a", "--format", "{{.ID}};;{{.Image}};;{{.Names}};;{{.Status}}"])
    infos: List[VPSInfo] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            cid, image, name, status = line.split(";;", 3)
        except ValueError:
            continue
        owner_id = 0
        owner_tag = "unknown"
        insp = run([DOCKER_BIN, "inspect", cid])
        if insp.returncode == 0 and insp.stdout:
            try:
                import json
                obj = json.loads(insp.stdout)[0]
                labels = obj.get("Config", {}).get("Labels", {}) or {}
                owner_id = int(labels.get("com.vps.owner_id", "0") or 0)
                owner_tag = labels.get("com.vps.owner_tag", "unknown")
            except Exception:
                pass
        infos.append(VPSInfo(cid, name, owner_id, owner_tag, image, status))
    return infos

async def wait_for_tmate(cid: str, timeout: int = 120) -> Optional[str]:
    """Poll /tmp/tmate-ssh.txt inside the container until it has content or timeout."""
    interval = 2
    elapsed = 0
    while elapsed < timeout:
        proc = run([DOCKER_BIN, "exec", cid, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
        out = proc.stdout.strip()
        if out:
            return out
        await asyncio.sleep(interval)
        elapsed += interval
    return None

# -------------------------
# Events + Commands
# -------------------------
@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Game(f"!kvm-help • ToraHosting 🖥️"))
    except Exception:
        pass
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")

@bot.command(name="kvm-help")
async def kvm_help(ctx: commands.Context):
    text = textwrap.dedent(f"""
    {E_PC} **ToraHosting — VPS Commands** (prefix `{PREFIX}`)
    ───────────────────────────────────────
    {E_WORK} `!create-vps <@user|username>` — Create a VPS with tmate (Admin only) and DM the link
    {E_LIST} `!kvm-list` — List all VPS containers and owners
    {E_KEY} `!kvm-ssh <container>` — Show tmate SSH/Web block for a container
    ▶️ `!kvm-start <container>` — Start a stopped container
    ⏹️ `!kvm-stop <container>` — Stop a running container
    🔁 `!kvm-restart <container>` — Restart a container
    📄 `!kvm-logs <container>` — Tail recent logs
    {E_TRASH} `!kvm-destroy <container>` — Remove container (manual)
    {E_CLOCK} `!ping` — Ping the bot
    ───────────────────────────────────────
    """)
    await ctx.reply(text)

@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.reply(f"🏓 Pong! {E_OK}")

@bot.command(name="create-vps")
@commands.has_permissions(administrator=True)
async def create_vps(ctx: commands.Context, target: str):
    # Resolve member by mention, username, or display name
    member = None
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    else:
        member = discord.utils.find(lambda m: str(m) == target or m.name == target or m.display_name == target, ctx.guild.members)
    if not member:
        return await ctx.reply(f"{E_WARN} Could not find `{target}`. Mention the user or use exact username.")
    base = f"Creating VPS for {member.mention}"
    msg = await ctx.reply(f"{E_CLOCK} {base} — starting...")
    # keep animation alive while work runs
    await spinner_edit(msg, base, emoji="⚙️", cycles=6, delay=0.35)

    # build container name
    cname = f"vps_{member.id}_{rand_suffix()}"
    # docker run command with labels
    labels = [
        f"--label=com.vps.owner_id={member.id}",
        f"--label=com.vps.owner_tag={str(member)}"
    ]
    cmd = [DOCKER_BIN, "run", "-d", "--restart", "unless-stopped", "--name", cname] + labels + [VPS_IMAGE]
    proc = run(cmd, timeout=40)
    if proc.returncode != 0:
        return await msg.edit(content=f"{E_WARN} Failed to start container:\n```{proc.stderr.strip()}```")

    cid = proc.stdout.strip()
    await msg.edit(content=f"{E_WORK} Container `{cname}` started. Waiting for tmate session…")
    tmate_block = await wait_for_tmate(cid, timeout=120)
    if not tmate_block:
        await msg.edit(content=f"{E_WARN} Timed out waiting for tmate. Use `!kvm-ssh {cname}` later.")
        return

    # DM user the tmate block (SSH + Web)
    try:
        dm = await member.create_dm()
        await dm.send(f"{E_KEY} **Your VPS is ready!**\n\n{tmate_block}\n\n{E_PC} Container: `{cname}`")
    except discord.Forbidden:
        await ctx.reply(f"{E_WARN} Could not DM {member.mention} — they may have DMs disabled.")
    await msg.edit(content=f"{E_OK} VPS `{cname}` created for {member.mention} — tmate link DM'd.")

@bot.command(name="kvm-list")
async def kvm_list(ctx: commands.Context):
    infos = docker_list_containers()
    if not infos:
        return await ctx.reply(f"{E_LIST} No VPS containers found.")
    lines = []
    for v in infos:
        owner = f"<@{v.owner_id}>" if v.owner_id else v.owner_tag
        lines.append(f"• **{v.name}** — {owner} — `{v.status}`")
    await ctx.reply(f"{E_LIST} **Active VPS**\n" + "\n".join(lines))

@bot.command(name="kvm-ssh")
async def kvm_ssh(ctx: commands.Context, ident: str):
    msg = await ctx.reply(f"{E_CLOCK} Fetching tmate for `{ident}`…")
    await spinner_edit(msg, f"Fetching tmate for {ident}", emoji="🔑", cycles=4, delay=0.3)
    proc = run([DOCKER_BIN, "exec", ident, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
    out = proc.stdout.strip()
    if not out:
        return await msg.edit(content=f"{E_WARN} No tmate info found for `{ident}` yet.")
    await msg.edit(content=f"{E_KEY} {out}")

@bot.command(name="kvm-start")
@commands.has_permissions(administrator=True)
async def kvm_start(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "start", ident])
    await ctx.reply(E_OK + " Started." if proc.returncode == 0 else f"{E_WARN} {proc.stderr}")

@bot.command(name="kvm-stop")
@commands.has_permissions(administrator=True)
async def kvm_stop(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "stop", ident])
    await ctx.reply(E_OK + " Stopped." if proc.returncode == 0 else f"{E_WARN} {proc.stderr}")

@bot.command(name="kvm-restart")
@commands.has_permissions(administrator=True)
async def kvm_restart(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "restart", ident])
    await ctx.reply(E_OK + " Restarted." if proc.returncode == 0 else f"{E_WARN} {proc.stderr}")

@bot.command(name="kvm-logs")
async def kvm_logs(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "logs", "--tail", "120", ident])
    if proc.returncode != 0:
        return await ctx.reply(f"{E_WARN} {proc.stderr}")
    out = proc.stdout or ""
    if len(out) > 1800:
        out = out[-1800:]
    await ctx.reply(f"```{out}```" if out else "ℹ️ No logs available.")

@bot.command(name="kvm-destroy")
@commands.has_permissions(administrator=True)
async def kvm_destroy(ctx: commands.Context, ident: str):
    confirm_msg = await ctx.reply(f"{E_TRASH} Removing `{ident}` — type `confirm` in chat to proceed within 20s.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirm"
    try:
        await bot.wait_for("message", timeout=20.0, check=check)
    except asyncio.TimeoutError:
        return await confirm_msg.edit(content=f"{E_WARN} Cancelling destroy — no confirmation.")
    proc = run([DOCKER_BIN, "rm", "-f", ident])
    await ctx.reply(E_OK + " Destroyed." if proc.returncode == 0 else f"{E_WARN} {proc.stderr}")

# Boot
if not TOKEN:
    raise SystemExit("Set DISCORD_TOKEN in .env before running.")
bot.run(TOKEN)
        
