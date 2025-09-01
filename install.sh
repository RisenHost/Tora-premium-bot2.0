#!/usr/bin/env bash
set -euo pipefail

BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; NC="\033[0m"
spin() { pid=$1; s='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'; i=0; tput civis; while kill -0 $pid 2>/dev/null; do printf "\r${CYAN}⚙️  %s Installing...${NC}" "${s:i++%${#s}:1}"; sleep 0.1; done; tput cnorm; printf "\r"; }

echo -e "${BOLD}${CYAN}✨ Discord VPS Creator — final edition ✨${NC}"

# Minimal OS deps
(
  apt-get update -y
  apt-get install -y python3 python3-pip curl git jq build-essential
) & spin $!

# Docker install if missing (get.docker.com)
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${YELLOW}Docker not found. Installing via get.docker.com${NC}"
  curl -fsSL https://get.docker.com | sh
else
  echo -e "${GREEN}Docker present${NC}"
fi

# Python deps
python3 -m pip install --upgrade pip >/dev/null
pip3 install discord.py==2.4.0 python-dotenv >/dev/null
echo -e "${GREEN}✅ Python deps installed${NC}"

# Build VPS base image
echo -e "${CYAN}🐳 Building VPS base image (ubuntu-22.04-with-tmate)${NC}"
docker build -t ubuntu-22.04-with-tmate -f Dockerfile . >/dev/null
echo -e "${GREEN}✅ Image built: ubuntu-22.04-with-tmate${NC}"

# .env prompt
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

echo -e "${GREEN}Setup complete. Start the bot with: python3 bot.py${NC}"
echo -e "Or run via Docker-compose (optional): docker-compose up -d"
