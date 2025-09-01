#!/usr/bin/env python3
"""
Discord VPS Creator (tmate-only) — ! prefix
Requirements: docker CLI available on host and the bot container or host has access to Docker socket.
"""

import os
import shlex
import shutil
import asyncio
import subprocess
import textwrap
import random
import string
from typing import Optional, List
from dataclasses import dataclass

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")
VPS_IMAGE = os.getenv("VPS_IMAGE", "ubuntu-22.04-with-tmate")
DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

EMOJI_OK = "✅"
EMOJI_WARN = "⚠️"
EMOJI_WORK = "🛠️"
EMOJI_PC = "🖥️"
EMOJI_KEY = "🔑"
EMOJI_LIST = "📜"
EMOJI_TRASH = "🗑️"
EMOJI_CLOCK = "⌛"

@dataclass
class VPSInfo:
    id: str
    name: str
    owner_id: int
    owner_tag: str
    image: str
    status: str

# -------------------------
# Helper utilities
# -------------------------
def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a shell command and return CompletedProcess (no exceptions)."""
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 124, stdout=e.stdout or "", stderr="timeout")

def rand_suffix(n=5):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def spinner_edit(msg: discord.Message, base: str, emoji: str = "⏳", cycles: int = 6, delay: float = 0.35):
    dots = ["", ".", "..", "..."]
    for i in range(cycles):
        await asyncio.sleep(delay)
        try:
            await msg.edit(content=f"{emoji} {base}{dots[i % len(dots)]}")
        except:
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
        # get labels
        insp = run([DOCKER_BIN, "inspect", cid])
        owner_id = 0
        owner_tag = "unknown"
        if insp.returncode == 0 and insp.stdout:
            import json
            try:
                obj = json.loads(insp.stdout)[0]
                labels = obj.get("Config", {}).get("Labels", {}) or {}
                owner_id = int(labels.get("com.vps.owner_id", "0") or 0)
                owner_tag = labels.get("com.vps.owner_tag", "unknown")
            except Exception:
                pass
        infos.append(VPSInfo(cid, name, owner_id, owner_tag, image, status))
    return infos

async def wait_for_tmate(cid: str, timeout: int = 90) -> Optional[str]:
    """Wait for /tmp/tmate-ssh.txt inside container and return content."""
    elapsed = 0
    interval = 2
    while elapsed < timeout:
        proc = run([DOCKER_BIN, "exec", cid, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
        out = proc.stdout.strip()
        if out:
            return out
        await asyncio.sleep(interval)
        elapsed += interval
    return None

# -------------------------
# Bot events + commands
# -------------------------
@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Game(f"!kvm-help • ToraHosting 🖥️"))
    except:
        pass
    print(f"Logged in as {bot.user} (id={bot.user.id})")

@bot.command(name="kvm-help")
async def kvm_help(ctx: commands.Context):
    text = textwrap.dedent(f"""
    {EMOJI_PC} **ToraHosting — KVM / VPS Commands** (prefix `{PREFIX}`)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {EMOJI_WORK} `!create-vps <@user|username>` — Create a VPS (tmate-only) and DM the tmate link
    {EMOJI_LIST} `!kvm-list` — List all VPS containers with owners
    {EMOJI_KEY} `!kvm-ssh <container>` — Re-send tmate SSH/Web link from container
    ▶️ `!kvm-start <container>` — Start a container
    ⏹️ `!kvm-stop <container>` — Stop a container
    🔁 `!kvm-restart <container>` — Restart a container
    📄 `!kvm-logs <container>` — Show last logs
    {EMOJI_TRASH} `!kvm-destroy <container>` — Remove container (manual)
    {EMOJI_CLOCK} `!ping` — Ping
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)
    await ctx.reply(text)

@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.reply(f"🏓 Pong! ({EMOJI_OK})")

@bot.command(name="create-vps")
@commands.has_permissions(manage_guild=True)
async def create_vps(ctx: commands.Context, target: str):
    # resolve member (mention preferred)
    member = None
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    else:
        member = discord.utils.find(lambda m: str(m) == target or m.name == target or m.display_name == target, ctx.guild.members)
    if not member:
        return await ctx.reply(f"{EMOJI_WARN} Could not find user `{target}`.")

    base_text = f"Creating VPS for {member.mention}"
    msg = await ctx.reply(f"{EMOJI_CLOCK} {base_text} — starting...")
    await spinner_edit(msg, base_text, emoji="⚙️", cycles=6, delay=0.35)

    # unique container name
    cname = f"vps_{member.id}_{rand_suffix:=(''.join(random.choices(string.ascii_lowercase+string.digits, k=4)))}"
    # safer approach for name (no spaces)
    cname = f"vps_{member.id}_{rand_suffix()}"

    # docker run options: labels to map owner
    labels = [
        f"--label=com.vps.owner_id={member.id}",
        f"--label=com.vps.owner_tag={str(member)}"
    ]

    cmd = [DOCKER_BIN, "run", "-d", "--restart", "unless-stopped", "--name", cname] + labels + [VPS_IMAGE]
    proc = run(cmd, timeout=30)
    if proc.returncode != 0:
        return await msg.edit(content=f"{EMOJI_WARN} Failed to launch container:\n```{proc.stderr.strip()}```")

    cid = proc.stdout.strip()
    await msg.edit(content=f"{EMOJI_WORK} Container `{cname}` started — waiting for tmate…")

    # wait for tmate file inside container
    tmate_text = await wait_for_tmate(cid, timeout=120)
    if not tmate_text:
        await msg.edit(content=f"{EMOJI_WARN} Timed out while waiting for tmate link. Use `!kvm-ssh {cname}` later.")
        return

    # send DM to member with the tmate block (SSH + Web lines)
    try:
        dm = await member.create_dm()
        await dm.send(f"{EMOJI_KEY} **Your VPS is ready!**\n\n{tmate_text}\n\n{EMOJI_PC} Container: `{cname}`")
    except discord.Forbidden:
        await ctx.reply(f"{EMOJI_WARN} Could not DM {member.mention}. They may have DMs disabled.")

    await msg.edit(content=f"{EMOJI_OK} VPS `{cname}` created for {member.mention} — tmate link DM'd.")

@bot.command(name="kvm-list")
async def kvm_list(ctx: commands.Context):
    infos = docker_list_containers()
    if not infos:
        return await ctx.reply(f"{EMOJI_LIST} No VPS containers found.")
    lines = []
    for v in infos:
        owner = f"<@{v.owner_id}>" if v.owner_id else v.owner_tag
        lines.append(f"• **{v.name}** — {owner} — `{v.status}`")
    out = "\n".join(lines)
    await ctx.reply(f"{EMOJI_LIST} **Active VPS**\n{out}")

@bot.command(name="kvm-ssh")
async def kvm_ssh(ctx: commands.Context, ident: str):
    msg = await ctx.reply(f"{EMOJI_CLOCK} Fetching tmate for `{ident}`…")
    await spinner_edit(msg, f"Fetching tmate for {ident}", emoji="🔑", cycles=4, delay=0.3)
    proc = run([DOCKER_BIN, "exec", ident, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
    out = proc.stdout.strip()
    if not out:
        return await msg.edit(content=f"{EMOJI_WARN} No tmate info found for `{ident}` yet.")
    await msg.edit(content=f"{EMOJI_KEY} {out}")

@bot.command(name="kvm-start")
@commands.has_permissions(manage_guild=True)
async def kvm_start(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "start", ident])
    await ctx.reply(EMOJI_OK + " Started." if proc.returncode == 0 else EMOJI_WARN + " " + proc.stderr)

@bot.command(name="kvm-stop")
@commands.has_permissions(manage_guild=True)
async def kvm_stop(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "stop", ident])
    await ctx.reply(EMOJI_OK + " Stopped." if proc.returncode == 0 else EMOJI_WARN + " " + proc.stderr)

@bot.command(name="kvm-restart")
@commands.has_permissions(manage_guild=True)
async def kvm_restart(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "restart", ident])
    await ctx.reply(EMOJI_OK + " Restarted." if proc.returncode == 0 else EMOJI_WARN + " " + proc.stderr)

@bot.command(name="kvm-logs")
async def kvm_logs(ctx: commands.Context, ident: str):
    proc = run([DOCKER_BIN, "logs", "--tail", "120", ident])
    if proc.returncode != 0:
        return await ctx.reply(f"{EMOJI_WARN} {proc.stderr}")
    out = proc.stdout or ""
    if len(out) > 1800:
        out = out[-1800:]
    await ctx.reply(f"```{out}```" if out else "ℹ️ No logs available.")

@bot.command(name="kvm-destroy")
@commands.has_permissions(manage_guild=True)
async def kvm_destroy(ctx: commands.Context, ident: str):
    confirm_msg = await ctx.reply(f"{EMOJI_TRASH} Removing `{ident}` — this is permanent. Type `confirm` in chat to proceed within 20s.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirm"
    try:
        reply = await bot.wait_for("message", timeout=20.0, check=check)
    except asyncio.TimeoutError:
        return await confirm_msg.edit(content=f"{EMOJI_WARN} Cancelling destroy — no confirmation received.")
    proc = run([DOCKER_BIN, "rm", "-f", ident])
    await ctx.reply(EMOJI_OK + " Destroyed." if proc.returncode == 0 else EMOJI_WARN + " " + proc.stderr)

# -------------------------
# Boot
# -------------------------
if not TOKEN:
    raise SystemExit("Set DISCORD_TOKEN in .env before running.")
bot.run(TOKEN)
