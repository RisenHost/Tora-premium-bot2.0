#!/usr/bin/env bash
set -euo pipefail

echo "⚙️ Installing requirements…"
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip git docker.io docker-compose curl jq
sudo systemctl enable --now docker

echo "📦 Installing Python deps…"
pip3 install -r requirements.txt

echo "🐳 Building base image…"
docker build -t ubuntu-22.04-with-tmate -f Dockerfile .

echo "✅ Done! Configure .env and run python3 bot.py"
