#!/usr/bin/env python3
import asyncio, json, os, random, shlex, string, subprocess, textwrap
from dataclasses import dataclass
from typing import List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")
PREFIX = "!"
VPS_IMAGE = os.getenv("VPS_IMAGE", "ubuntu-22.04-with-tmate")
DOCKER = os.getenv("DOCKER_BIN", "docker")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ---------- helpers ----------
def run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(shlex.split(cmd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def j(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def rand_suffix(n=4):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def animate(ctx_or_msg, base: str, emoji="✨", times=6, delay=0.35):
    # accepts ctx (send first) or an existing message to edit
    if isinstance(ctx_or_msg, discord.Message):
        msg = ctx_or_msg
    else:
        msg = await ctx_or_msg.send(f"{emoji} {base} …")
    dots = ["", ".", "..", "..."]
    for i in range(times):
        await asyncio.sleep(delay)
        await msg.edit(content=f"{emoji} {base}{dots[i%4]}")
    return msg

@dataclass
class VPSInfo:
    id: str
    name: str
    owner_id: int
    owner_tag: str
    image: str
    status: str

def docker_ls() -> List[VPSInfo]:
    out = j([DOCKER, "ps", "-a", "--format", "{{.ID}} {{.Image}} {{.Names}} {{.Status}}"]).stdout.strip()
    infos: List[VPSInfo] = []
    for line in out.splitlines():
        if not line.strip(): continue
        parts = line.split(maxsplit=3)
        if len(parts) < 4: continue
        cid, image, name, status = parts[0], parts[1], parts[2], parts[3]
        insp = j([DOCKER, "inspect", cid]).stdout
        try:
            obj = json.loads(insp)[0]
            labels = obj.get("Config", {}).get("Labels", {}) or {}
            owner_id = int(labels.get("com.vps.owner_id", "0"))
            owner_tag = labels.get("com.vps.owner_tag", "unknown")
        except Exception:
            owner_id, owner_tag = 0, "unknown"
        infos.append(VPSInfo(cid, name, owner_id, owner_tag, image, status))
    return infos

async def get_tmate_block(cid: str, timeout=60) -> Optional[str]:
    # First try the file we write in the container
    for _ in range(timeout // 2):
        r = j([DOCKER, "exec", cid, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
        s = r.stdout.strip()
        if s:
            return s
        await asyncio.sleep(2)
    return None

# ---------- commands ----------
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("!kvm-help • VPS Creator 🧰"))
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")

@bot.command(name="kvm-help")
async def kvm_help(ctx):
    text = textwrap.dedent(f"""
    🎛️ **KVM / VPS Commands** (prefix `{PREFIX}`)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🆕 `!create-vps <@user|username>` → Create a VPS (tmate-only) and **DM** the link
    📜 `!kvm-list` → Show **all** VPS + owners + status
    🔑 `!kvm-ssh <container|name>` → Show the tmate link again
    ▶️ `!kvm-start <container>` • ⏹️ `!kvm-stop <container>` • 🔁 `!kvm-restart <container>`
    📄 `!kvm-logs <container>` → Tail recent logs
    🗑️ `!kvm-destroy <container>` → Remove VPS (manual only, no auto-removal!)
    🆘 `!kvm-help` → This menu
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)
    await ctx.reply(text)

@bot.command(name="create-vps")
@commands.has_permissions(manage_guild=True)
async def create_vps(ctx, target: str):
    # resolve member
    member = ctx.message.mentions[0] if ctx.message.mentions else discord.utils.find(
        lambda m: str(m) == target or m.name == target or m.display_name == target, ctx.guild.members
    )
    if not member:
        return await ctx.reply(f"⚠️ I can’t find `{target}`. Mention the user or type exact username.")

    base = f"Booting VPS for {member.mention}"
    msg = await animate(ctx, base, "⚙️", times=6, delay=0.3)

    # unique name + labels
    name = f"vps_{member.id}_{rand_suffix()}"
    labels = [
        f"--label=com.vps.owner_id={member.id}",
        f"--label=com.vps.owner_tag={str(member)}",
        f"--label=com.vps.created_by=discord-bot",
    ]
    # run container
    r = j([DOCKER, "run", "-d", "--restart", "unless-stopped", "--name", name, *labels, VPS_IMAGE])
    if r.returncode != 0:
        return await msg.edit(content=f"❌ Failed to start container:\n```{r.stderr.strip()}```")

    cid = r.stdout.strip()
    await msg.edit(content=f"🧰 Installing tmate inside `{name}`…")
    # start script will already run tmate; just wait for link
    link = await get_tmate_block(cid, timeout=90)

    if not link:
        return await msg.edit(content="⚠️ Timed out waiting for tmate link. Run `!kvm-ssh {name}` later.")

    # DM user
    try:
        await member.send(f"🔑 **Your VPS is ready!**\n\n{link}")
    except discord.Forbidden:
        await ctx.reply(f"⚠️ Could not DM {member.mention}. They may have DMs closed.")
    await msg.edit(content=f"🎉 VPS `{name}` created for {member.mention}! Link sent via DM.")

@bot.command(name="kvm-list")
async def kvm_list(ctx):
    infos = docker_ls()
    if not infos:
        return await ctx.reply("📭 No VPS containers yet.")
    lines = []
    for i in infos:
        owner = f"<@{i.owner_id}>" if i.owner_id else i.owner_tag
        lines.append(f"• **{i.name}** — {owner} — `{i.status}`")
    await ctx.reply("📜 **All VPS**\n" + "\n".join(lines))

@bot.command(name="kvm-ssh")
async def kvm_ssh(ctx, ident: str):
    await animate(ctx, f"Fetching tmate for `{ident}`", "🔑", times=3, delay=0.25)
    r = j([DOCKER, "exec", ident, "bash", "-lc", "cat /tmp/tmate-ssh.txt 2>/dev/null || true"])
    s = r.stdout.strip()
    if not s:
        return await ctx.reply("⚠️ No tmate link yet. The session might still be initializing.")
    await ctx.reply(f"🔗 {s}")

@bot.command(name="kvm-start")
async def kvm_start(ctx, ident: str):
    r = j([DOCKER, "start", ident])
    await ctx.reply("▶️ Started." if r.returncode == 0 else f"❌ {r.stderr}")

@bot.command(name="kvm-stop")
async def kvm_stop(ctx, ident: str):
    r = j([DOCKER, "stop", ident])
    await ctx.reply("⏹️ Stopped." if r.returncode == 0 else f"❌ {r.stderr}")

@bot.command(name="kvm-restart")
async def kvm_restart(ctx, ident: str):
    r = j([DOCKER, "restart", ident])
    await ctx.reply("🔁 Restarted." if r.returncode == 0 else f"❌ {r.stderr}")

@bot.command(name="kvm-logs")
async def kvm_logs(ctx, ident: str):
    r = j([DOCKER, "logs", "--tail", "80", ident])
    if r.returncode != 0:
        return await ctx.reply(f"❌ {r.stderr}")
    out = r.stdout[-1800:] if r.stdout else ""
    await ctx.reply(f"```txt\n{out}\n```" if out else "ℹ️ No logs.")

@bot.command(name="kvm-destroy")
@commands.has_permissions(manage_guild=True)
async def kvm_destroy(ctx, ident: str):
    await animate(ctx, f"Removing `{ident}`", "🗑️", times=4, delay=0.25)
    r1 = j([DOCKER, "rm", "-f", ident])
    await ctx.reply("✅ Destroyed." if r1.returncode == 0 else f"❌ {r1.stderr}")

# run
if not TOKEN:
    raise SystemExit("Set DISCORD_TOKEN in .env")
bot.run(TOKEN)
