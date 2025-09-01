#!/usr/bin/env bash
set -euo pipefail

# colors
BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; NC="\033[0m"

echo -e "${BOLD}${CYAN}→ Installing minimal dependencies...${NC}"

apt-get update -y
apt-get install -y python3 python3-pip curl git jq build-essential

# docker install if missing
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${YELLOW}Docker not found — attempting get.docker.com installer${NC}"
  curl -fsSL https://get.docker.com | sh
fi

# python deps for bot
python3 -m pip install --upgrade pip
pip3 install discord.py==2.4.0 python-dotenv

# build VPS base image
echo -e "${CYAN}→ Building VPS base image (ubuntu-22.04-with-tmate)${NC}"
docker build -t ubuntu-22.04-with-tmate -f Dockerfile .

# .env token prompt
if [ ! -f ".env" ]; then
  read -p "🤖 Enter your Discord Bot Token: " BOT_TOKEN
  cat > .env <<EOF
DISCORD_TOKEN=$BOT_TOKEN
VPS_IMAGE=ubuntu-22.04-with-tmate
DOCKER_BIN=docker
BOT_PREFIX=!
EOF
  echo -e "${GREEN}✅ Saved token to .env${NC}"
else
  echo -e "${YELLOW}ℹ️ .env exists — skipping token input${NC}"
fi

echo -e "${GREEN}All set. Start the bot with:${NC} python3 bot.py"
echo -e "Or run via docker-compose (recommended): docker-compose up -d"
