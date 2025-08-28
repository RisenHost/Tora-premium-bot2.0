#!/usr/bin/env python3
import asyncio, json, os, shlex, subprocess
from dataclasses import dataclass
from typing import Optional, List

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
PREFIX = os.getenv("BOT_PREFIX", "!")
IMAGE = os.getenv("DEFAULT_IMAGE", "ubuntu-22.04-with-tmate")
DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None)

@dataclass
class VPSInfo:
    container_id: str
    name: str
    owner_id: int
    owner_tag: str
    image: str
    status: str

def run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

async def docker_ls() -> List[VPSInfo]:
    res = run(f"{DOCKER_BIN} ps -a --format '{{json .}}'")
    infos: List[VPSInfo] = []
    for line in res.stdout.splitlines():
        try:
            obj = json.loads(line)
        except:
            continue
        labels = {}
        insp = run(f"{DOCKER_BIN} inspect {obj['ID']}")
        try:
            arr = json.loads(insp.stdout)[0]
            labels = arr.get('Config', {}).get('Labels', {}) or {}
        except:
            pass
        owner_id = int(labels.get('com.vps.owner_id', '0'))
        owner_tag = labels.get('com.vps.owner_tag', 'unknown')
        infos.append(VPSInfo(
            container_id=obj['ID'],
            name=obj.get('Names', ''),
            owner_id=owner_id,
            owner_tag=owner_tag,
            image=obj.get('Image', ''),
            status=obj.get('Status', '')
        ))
    return infos

async def create_and_get_tmate(owner: discord.Member) -> Optional[str]:
    labels = [f"--label=com.vps.owner_id={owner.id}", f"--label=com.vps.owner_tag={owner}"]
    name = f"vps_{owner.id}"
    res = run(f"{DOCKER_BIN} run -d --restart unless-stopped --name {name} {' '.join(labels)} {IMAGE}")
    if res.returncode != 0:
        return None
    cid = res.stdout.strip()
    await asyncio.sleep(6)
    for _ in range(30):
        exec_out = run(f"{DOCKER_BIN} exec {cid} bash -lc 'cat /tmp/tmate-ssh.txt 2>/dev/null || true'")
        if exec_out.stdout.strip():
            return exec_out.stdout.strip()
        await asyncio.sleep(2)
    return None

@bot.command(name="kvm-help")
async def kvm_help(ctx):
    await ctx.reply(f"""
✨ **VPS Bot Commands (prefix `{PREFIX}`)**
- `!create-vps <@user>` → create VPS and DM tmate link
- `!kvm-list` → list all VPS with owners
- `!kvm-ssh <container>` → show tmate again
- `!kvm-start|stop|restart|logs <container>` → manage VPS
(No auto-removal, VPS stay until you delete them)
""")

@bot.command(name="create-vps")
@commands.has_permissions(administrator=True)
async def create_vps(ctx, target: str):
    member = ctx.message.mentions[0] if ctx.message.mentions else discord.utils.find(lambda m: str(m) == target or m.name == target, ctx.guild.members)
    if not member:
        return await ctx.reply(f"⚠️ Could not find user `{target}`.")
    await ctx.reply(f"🛠️ Creating VPS for {member}…")
    conn = await create_and_get_tmate(member)
    if not conn:
        return await ctx.reply(f"⚠️ Failed to create VPS.")
    await member.send(f"🖥️ Your VPS is ready!\n{conn}")
    await ctx.reply(f"✅ VPS created for {member} and DM sent.")

@bot.command(name="kvm-list")
async def kvm_list(ctx):
    infos = await docker_ls()
    if not infos: return await ctx.reply("📜 No VPS containers found.")
    lines = [f"• **{i.name}** — owner: <@{i.owner_id}> — `{i.status}`" for i in infos]
    await ctx.reply("📜 **All VPS**\n" + "\n".join(lines))

@bot.command(name="kvm-ssh")
async def kvm_ssh(ctx, ident: str):
    res = run(f"{DOCKER_BIN} exec {shlex.quote(ident)} bash -lc 'cat /tmp/tmate-ssh.txt 2>/dev/null || true'")
    if res.stdout.strip():
        await ctx.reply(f"🖥️ {res.stdout.strip()}")
    else:
        await ctx.reply("⚠️ No tmate info yet.")

@bot.command(name="kvm-start")
async def kvm_start(ctx, ident: str):
    res = run(f"{DOCKER_BIN} start {ident}")
    await ctx.reply("✅ VPS started." if res.returncode == 0 else f"⚠️ {res.stderr}")

@bot.command(name="kvm-stop")
async def kvm_stop(ctx, ident: str):
    res = run(f"{DOCKER_BIN} stop {ident}")
    await ctx.reply("✅ VPS stopped." if res.returncode == 0 else f"⚠️ {res.stderr}")

@bot.command(name="kvm-restart")
async def kvm_restart(ctx, ident: str):
    res = run(f"{DOCKER_BIN} restart {ident}")
    await ctx.reply("✅ VPS restarted." if res.returncode == 0 else f"⚠️ {res.stderr}")

@bot.command(name="kvm-logs")
async def kvm_logs(ctx, ident: str):
    res = run(f"{DOCKER_BIN} logs --tail 50 {ident}")
    await ctx.reply(f"```\n{res.stdout[-1800:]}\n```" if res.returncode == 0 else f"⚠️ {res.stderr}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    if not TOKEN: raise SystemExit("Set DISCORD_TOKEN in .env")
    bot.run(TOKEN)
