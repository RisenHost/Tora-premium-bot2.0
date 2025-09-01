#!/usr/bin/env bash
set -euo pipefail

BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; NC="\033[0m"
spin() { pid=$1; s='⠋⠙⠚⠞⠖⠦⠴⠲⠳⠓'; i=0; tput civis; while kill -0 $pid 2>/dev/null; do printf "\r${CYAN}⚙️  %s Installing...${NC}" "${s:i++%${#s}:1}"; sleep 0.1; done; tput cnorm; printf "\r"; }

echo -e "${BOLD}${CYAN}✨ Discord VPS Creator — !-prefix edition ✨${NC}"

# Python deps for bot
(
  apt-get update -y
  apt-get install -y python3 python3-pip jq curl git
) & spin $!

python3 -m pip install --upgrade pip >/dev/null
pip3 install -r requirements.txt >/dev/null
echo -e "${GREEN}✅ Python deps installed${NC}"

# Docker check (no systemctl)
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${YELLOW}🐳 Docker not found. Attempting non-systemd install (get.docker.com)…${NC}"
  curl -fsSL https://get.docker.com | sh
else
  echo -e "${GREEN}🐳 Docker present${NC}"
fi

# Build VPS base image
echo -e "${CYAN}🐳 Building VPS base image (Ubuntu + tmate)…${NC}"
docker build -t ubuntu-22.04-with-tmate -f Dockerfile . >/dev/null
echo -e "${GREEN}✅ Image built: ubuntu-22.04-with-tmate${NC}"

# Token
if [ ! -f ".env" ]; then
  read -p "🤖 Enter your Discord Bot Token: " TOK
  {
    echo "DISCORD_TOKEN=$TOK"
    echo "VPS_IMAGE=ubuntu-22.04-with-tmate"
    echo "DOCKER_BIN=docker"
  } > .env
  echo -e "${GREEN}✅ Saved token to .env${NC}"
else
  echo -e "${YELLOW}ℹ️ .env exists – leaving as-is${NC}"
fi

cat <<EOT

${BOLD}How to run:${NC}
  1) ${CYAN}python3 bot.py${NC}
  2) In Discord, use: ${GREEN}!kvm-help${NC}

Notes:
 • No auto-removal—containers persist.
 • Use ${GREEN}!create-vps @user${NC} to DM their tmate link.
EOT
