#!/usr/bin/env python3
"""
ToraHosting VPS Creator Bot (bot.py)
- Python / discord.py v2.x
- Admin-only create, persistent Docker containers
- tmate session created inside container, SSH + Web link DM'd to owner
- Animated progress + embeds + robust error handling
- Commands: !create-vps, !kvm-list, !kvm-ssh, !kvm-start/stop/restart, !kvm-logs, !kvm-destroy, !kvm-help, !ping
"""

import os
import asyncio
import random
import string
import textwrap
import json
from typing import Optional, List, Tuple
from dataclasses import dataclass

import discord
from discord.ext import commands
from dotenv import load_dotenv

# -------------------------
# Load env
# -------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")
VPS_IMAGE = os.getenv("VPS_IMAGE", "ubuntu-22.04-with-tmate")
DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")
TMATE_WAIT_TIMEOUT = int(os.getenv("TMATE_WAIT_TIMEOUT", "120"))  # seconds to wait for tmate inside container

if not TOKEN:
    raise SystemExit("Please set DISCORD_TOKEN in .env before running.")

# -------------------------
# Bot / Intents
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# -------------------------
# Aesthetic / Emojis
# -------------------------
E_OK = "✅"
E_WARN = "⚠️"
E_WORK = "🛠️"
E_PC = "🖥️"
E_KEY = "🔑"
E_LIST = "📜"
E_TRASH = "🗑️"
E_CLOCK = "⌛"
E_SPARK = "✨"
BANNER = "🌐 ToraHosting • VPS Panel"

# -------------------------
# Simple dataclass for containers
# -------------------------
@dataclass
class VPSInfo:
    id: str
    name: str
    owner_id: int
    owner_tag: str
    image: str
    status: str

# -------------------------
# Async shell functions
# -------------------------
async def run_cmd(cmd: List[str], timeout: Optional[int] = None) -> Tuple[int, str, str]:
    """
    Run a command asynchronously and capture stdout/stderr.
    Returns (returncode, stdout, stderr)
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return 124, (stdout.decode() if stdout else ""), (stderr.decode() if stderr else "timeout")
        return proc.returncode, (stdout.decode() if stdout else ""), (stderr.decode() if stderr else "")
    except FileNotFoundError as e:
        return 127, "", str(e)
    except Exception as e:
        return 1, "", str(e)

# -------------------------
# Utilities
# -------------------------
def rand_suffix(n: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def animate_until(event: asyncio.Event, msg: discord.Message, base: str, emoji: str = "⚙️", delay: float = 0.35):
    """
    Edit message until event.is_set() with a small dot animation.
    """
    dots = ["", ".", "..", "..."]
    i = 0
    try:
        while not event.is_set():
            await asyncio.sleep(delay)
            dot = dots[i % len(dots)]
            i += 1
            try:
                await msg.edit(content=f"{emoji} {base}{dot}")
            except discord.HTTPException:
                pass
    except Exception:
        pass

# -------------------------
# Docker helper functions
# -------------------------
async def docker_image_exists(image: str) -> bool:
    rc, out, err = await run_cmd([DOCKER_BIN, "images", "-q", image])
    return rc == 0 and out.strip() != ""

async def try_build_image_if_needed(image: str, dockerfile_path: str = "Dockerfile") -> Tuple[bool, str]:
    """
    If image missing and Dockerfile exists, attempt to build it.
    Returns (success, message)
    """
    exists = await docker_image_exists(image)
    if exists:
        return True, f"Image {image} already exists."
    if not os.path.exists(dockerfile_path):
        return False, f"Dockerfile not found at {dockerfile_path}. Please build {image} manually."
    # build
    rc, out, err = await run_cmd([DOCKER_BIN, "build", "-t", image, "-f", dockerfile_path, "."])
    if rc == 0:
        return True, f"Built image {image}."
    else:
        return False, f"Failed to build image {image}. stderr:\n{err}"

async def docker_run_container(image: str, name: str, labels: List[str]) -> Tuple[bool, str, str]:
    """
    Run a container detached, with restart unless-stopped.
    labels should be list of Docker --label strings like '--label=key=val' or already formatted without flag?
    We'll pass labels as ['--label', 'k=v', ...] to avoid shell issues.
    """
    # assemble base command
    cmd = [DOCKER_BIN, "run", "-d", "--restart", "unless-stopped", "--name", name]
    # add labels
    for l in labels:
        # l expected as "key=value"
        cmd += ["--label", l]
    cmd.append(image)
    rc, out, err = await run_cmd(cmd, timeout=60)
    return (rc == 0, out.strip(), err.strip())

async def docker_exec_readfile(cid: str, path: str) -> str:
    rc, out, err = await run_cmd([DOCKER_BIN, "exec", cid, "bash", "-lc", f"cat {path} 2>/dev/null || true"], timeout=10)
    return out.strip()

async def docker_exec_cmd(cid: str, bash_cmd: str, timeout: Optional[int] = None) -> Tuple[int, str, str]:
    rc, out, err = await run_cmd([DOCKER_BIN, "exec", cid, "bash", "-lc", bash_cmd], timeout=timeout)
    return rc, out, err

# -------------------------
# tmate helpers
# -------------------------
async def ensure_tmate_in_container(cid: str) -> Tuple[bool, str]:
    """
    Ensure tmate is installed and running in the container and that /tmp/tmate-ssh.txt exists filled.
    Returns (success, message-or-tmate-text)
    """
    # 1) Check if /tmp/tmate-ssh.txt exists with content
    content = await docker_exec_readfile(cid, "/tmp/tmate-ssh.txt")
    if content:
        return True, content

    # 2) Check if tmate command exists
    rc, out, err = await docker_exec_cmd(cid, "command -v tmate || true", timeout=20)
    if not out.strip():
        # install tmate (apt-get)
        # Keep noninteractive
        install_cmd = "apt-get update -y >/dev/null 2>&1 || true; apt-get install -y tmate tmux openssh-client >/var/tmp/tmate_install.log 2>&1 || true"
        rc_i, out_i, err_i = await docker_exec_cmd(cid, install_cmd, timeout=180)
        # re-check
        rc2, out2, err2 = await docker_exec_cmd(cid, "command -v tmate || true", timeout=20)
        if not out2.strip():
            # installation failed
            logs = out_i + "\n" + err_i + "\n" + err2
            return False, f"tmate not available and installation failed. Logs:\n{logs[:2000]}"
    # 3) Start a detached tmate session and write its SSH/Web to /tmp/tmate-ssh.txt
    # Use a robust line that tries to create a new session if not present
    create_cmd = textwrap.dedent(r"""
        SOCKET=/tmp/tmate.sock
        # Try to create detached session (ignore errors)
        tmate -S "$SOCKET" new-session -d >/dev/null 2>&1 || true
        # Wait until tmate responds (max 60s)
        i=0
        while [ $i -lt 60 ]; do
          tmate -S "$SOCKET" display -p '#{tmate_ssh}' >/dev/null 2>&1 && break
          i=$((i+1))
          sleep 1
        done
        # Output links to file
        echo "SSH: $(tmate -S \"$SOCKET\" display -p '#{tmate_ssh}')" > /tmp/tmate-ssh.txt 2>/dev/null || true
        echo "Web: $(tmate -S \"$SOCKET\" display -p '#{tmate_web}')" >> /tmp/tmate-ssh.txt 2>/dev/null || true
    """)
    rc_c, out_c, err_c = await docker_exec_cmd(cid, create_cmd, timeout=90)
    # Now read file
    content2 = await docker_exec_readfile(cid, "/tmp/tmate-ssh.txt")
    if content2:
        return True, content2
    else:
        # debug logs
        logs_rc, logs_out, logs_err = await docker_exec_cmd(cid, "bash -lc 'ls -la /tmp || true; ps aux || true; whoami || true; env || true'", timeout=10)
        reason = f"tmate session file not created.\ncreate stderr: {err_c}\nextra logs: {logs_out}\n{logs_err}"
        return False, reason

# -------------------------
# Docker listing function
# -------------------------
async def docker_list_all() -> List[VPSInfo]:
    rc, out, err = await run_cmd([DOCKER_BIN, "ps", "-a", "--format", "{{.ID}};;{{.Image}};;{{.Names}};;{{.Status}}"])
    infos: List[VPSInfo] = []
    if rc != 0:
        return infos
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            cid, image, name, status = line.split(";;", 3)
        except ValueError:
            continue
        # inspect labels
        rc2, ins_out, ins_err = await run_cmd([DOCKER_BIN, "inspect", cid])
        owner_id = 0
        owner_tag = "unknown"
        if rc2 == 0 and ins_out:
            try:
                obj = json.loads(ins_out)[0]
                labels = obj.get("Config", {}).get("Labels", {}) or {}
                owner_id = int(labels.get("com.vps.owner_id", "0") or 0)
                owner_tag = labels.get("com.vps.owner_tag", "unknown")
            except Exception:
                pass
        infos.append(VPSInfo(cid.strip(), name.strip(), owner_id, owner_tag, image.strip(), status.strip()))
    return infos

# -------------------------
# Embeds + helpers for messages
# -------------------------
def make_embed(title: str, description: str = "", color: discord.Color = discord.Color.blue()) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text="ToraHosting • Powered by your bot")
    return e

# -------------------------
# Commands
# -------------------------
@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Game(f"{PREFIX}kvm-help • ToraHosting"))
    except Exception:
        pass
    print(f"[INFO] Logged in as {bot.user} (id={bot.user.id})")

@bot.command(name="kvm-help")
async def kvm_help(ctx):
    embed = make_embed(f"{E_SPARK} ToraHosting — Help", color=discord.Color.teal())
    embed.add_field(name=f"{E_WORK} Provisioning", value=f"`{PREFIX}create-vps <@user|username>` — Create a VPS and DM tmate link (Admin only)", inline=False)
    embed.add_field(name=f"{E_LIST} Management", value=f"`{PREFIX}kvm-list` `|` `{PREFIX}kvm-ssh <container>` `|` `{PREFIX}kvm-start <container>` `|` `{PREFIX}kvm-stop <container>`", inline=False)
    embed.add_field(name=f"{E_TRASH} Removal", value=f"`{PREFIX}kvm-destroy <container>` — Remove container (Admin only, confirmation required)", inline=False)
    embed.add_field(name=f"{E_CLOCK} Other", value=f"`{PREFIX}kvm-logs <container>` `|` `{PREFIX}kvm-help` `|` `{PREFIX}ping`", inline=False)
    await ctx.reply(embed=embed)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! {E_OK}")

@bot.command(name="kvm-list")
async def kvm_list(ctx):
    infos = await docker_list_all()
    if not infos:
        return await ctx.reply(f"{E_LIST} No VPS containers found.")
    lines = []
    for v in infos:
        owner = f"<@{v.owner_id}>" if v.owner_id else v.owner_tag
        lines.append(f"• **{v.name}** — {owner} — `{v.status}`")
    # use embed if many
    embed = make_embed(f"{E_LIST} Active VPS", color=discord.Color.dark_gold())
    embed.description = "\n".join(lines[:25])  # truncate if many
    await ctx.reply(embed=embed)

@bot.command(name="kvm-ssh")
async def kvm_ssh(ctx, ident: str):
    msg = await ctx.reply(f"{E_CLOCK} Fetching tmate for `{ident}`…")
    stop_event = asyncio.Event()
    spinner = asyncio.create_task(animate_until(stop_event, msg, f"Fetching tmate for {ident}", emoji="🔑", delay=0.25))
    # read file
    t = await docker_exec_readfile(ident, "/tmp/tmate-ssh.txt")
    stop_event.set()
    await spinner
    if not t:
        return await msg.edit(content=f"{E_WARN} No tmate info found for `{ident}` yet. Try again in a few seconds or check container logs.")
    # send as reply
    embed = make_embed(f"{E_KEY} tmate for `{ident}`", color=discord.Color.green())
    embed.add_field(name="Credentials", value=f"```{t}```", inline=False)
    await msg.edit(content=None, embed=embed)

@bot.command(name="kvm-start")
@commands.has_permissions(administrator=True)
async def kvm_start(ctx, ident: str):
    rc, out, err = await run_cmd([DOCKER_BIN, "start", ident])
    if rc == 0:
        await ctx.reply(f"{E_OK} Started `{ident}`.")
    else:
        await ctx.reply(f"{E_WARN} Could not start `{ident}`. Error:\n```{err.strip()}```")

@bot.command(name="kvm-stop")
@commands.has_permissions(administrator=True)
async def kvm_stop(ctx, ident: str):
    rc, out, err = await run_cmd([DOCKER_BIN, "stop", ident])
    if rc == 0:
        await ctx.reply(f"{E_OK} Stopped `{ident}`.")
    else:
        await ctx.reply(f"{E_WARN} Could not stop `{ident}`. Error:\n```{err.strip()}```")

@bot.command(name="kvm-restart")
@commands.has_permissions(administrator=True)
async def kvm_restart(ctx, ident: str):
    rc, out, err = await run_cmd([DOCKER_BIN, "restart", ident])
    if rc == 0:
        await ctx.reply(f"{E_OK} Restarted `{ident}`.")
    else:
        await ctx.reply(f"{E_WARN} Could not restart `{ident}`. Error:\n```{err.strip()}```")

@bot.command(name="kvm-logs")
async def kvm_logs(ctx, ident: str):
    rc, out, err = await run_cmd([DOCKER_BIN, "logs", "--tail", "200", ident])
    if rc != 0:
        return await ctx.reply(f"{E_WARN} Error fetching logs: ```{err.strip()}```")
    # trim output
    text = out or "No logs available."
    if len(text) > 1900:
        text = text[-1900:]
    embed = make_embed(f"📄 Logs for `{ident}`", color=discord.Color.dark_magenta())
    embed.add_field(name="Recent logs", value=f"```\n{text}\n```", inline=False)
    await ctx.reply(embed=embed)

@bot.command(name="kvm-destroy")
@commands.has_permissions(administrator=True)
async def kvm_destroy(ctx, ident: str):
    confirm_msg = await ctx.reply(f"{E_TRASH} Removing `{ident}` — type `confirm` in chat within 20s to proceed.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirm"
    try:
        await bot.wait_for("message", timeout=20.0, check=check)
    except asyncio.TimeoutError:
        return await confirm_msg.edit(content=f"{E_WARN} Cancelling destroy — no confirmation received.")
    rc, out, err = await run_cmd([DOCKER_BIN, "rm", "-f", ident], timeout=30)
    if rc == 0:
        await ctx.reply(f"{E_OK} Destroyed `{ident}`.")
    else:
        await ctx.reply(f"{E_WARN} Failed to destroy `{ident}`: ```{err.strip()}```")

@bot.command(name="create-vps")
@commands.has_permissions(administrator=True)
async def create_vps(ctx, target: str):
    """
    Usage: !create-vps @user  OR !create-vps username
    Admin-only to prevent abuse.
    """
    # Resolve member
    member = None
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    else:
        member = discord.utils.find(lambda m: str(m) == target or m.name == target or m.display_name == target, ctx.guild.members)
    if not member:
        return await ctx.reply(f"{E_WARN} Could not find `{target}`. Mention the user or provide exact username.")

    # Message + spinner
    base_text = f"Provisioning VPS for {member.mention}"
    msg = await ctx.reply(f"{E_CLOCK} {base_text} — preparing...")
    stop_evt = asyncio.Event()
    spinner_task = asyncio.create_task(animate_until(stop_evt, msg, base_text, emoji="⚙️", delay=0.35))

    # Ensure image exists or try to build it (if Dockerfile present)
    img_exists = await docker_image_exists(VPS_IMAGE)
    if not img_exists and os.path.exists("Dockerfile"):
        # attempt build (feedback to user)
        await msg.edit(content=f"🐳 Building VPS image `{VPS_IMAGE}` (this may take a while)…")
        rc_build, out_build, err_build = await run_cmd([DOCKER_BIN, "build", "-t", VPS_IMAGE, "-f", "Dockerfile", "."], timeout=1800)
        if rc_build != 0:
            stop_evt.set()
            await spinner_task
            return await msg.edit(content=f"{E_WARN} Failed to build VPS image. Error:\n```{err_build.strip()[:1500]}```")
    elif not img_exists:
        stop_evt.set()
        await spinner_task
        return await msg.edit(content=f"{E_WARN} VPS image `{VPS_IMAGE}` not found and no Dockerfile available to build it. Please build it first.")

    # Build container name and labels
    cname = f"vps_{member.id}_{rand_suffix()}"
    labels = [f"com.vps.owner_id={member.id}", f"com.vps.owner_tag={str(member)}"]

    # Run container
    await msg.edit(content=f"{E_WORK} Starting container `{cname}`…")
    ok, out, err = await docker_run_container(VPS_IMAGE, cname, labels)
    if not ok:
        stop_evt.set()
        await spinner_task
        return await msg.edit(content=f"{E_WARN} Failed to start container:\n```{err.strip() or out.strip()}```")

    cid = out.strip()  # the container id
    await msg.edit(content=f"{E_WORK} Container started. Ensuring tmate session inside the container…")

    # Ensure tmate and get the block
    success, tmate_or_reason = await ensure_tmate_in_container(cid)
    stop_evt.set()
    await spinner_task
    if not success:
        # still send container info so admin can debug
        await msg.edit(content=f"{E_WARN} tmate setup failed for `{cname}`.\nDetails:\n```{tmate_or_reason[:1500]}```\nYou can run `!kvm-logs {cname}` or check container manually.")
        return

    tmate_text = tmate_or_reason.strip()
    # DM owner
    embed = make_embed(f"{E_KEY} Your VPS is ready!", color=discord.Color.green())
    embed.add_field(name="Container", value=f"`{cname}`", inline=False)
    embed.add_field(name="tmate (SSH & Web)", value=f"```\n{tmate_text}\n```", inline=False)
    embed.set_footer(text="Use the SSH string in PuTTY (as an ssh command) or open the web link.")

    try:
        await member.send(embed=embed)
        await msg.edit(content=f"{E_OK} VPS `{cname}` created for {member.mention} — tmate link DM'd.")
    except discord.Forbidden:
        # DM failed; print link in channel (warn)
        await msg.edit(content=f"{E_WARN} Could not DM {member.mention} — DMs disabled. Showing tmate here (sensitive!).")
        await ctx.send(embed=embed)

# -------------------------
# Run the bot
# -------------------------
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print("[FATAL] Bot crashed:", e)
