#!/bin/bash
set -e

echo "✨ Starting installation with animations... ✨"

apt-get update -y
apt-get install -y python3 python3-pip curl git jq docker.io docker-compose

pip3 install -r requirements.txt

if [ ! -f ".env" ]; then
  read -p "🤖 Enter your Discord Bot Token: " BOT_TOKEN
  echo "DISCORD_TOKEN=$BOT_TOKEN" > .env
  echo "✅ Token saved in .env"
else
  echo "ℹ️ .env already exists, skipping token input."
fi

echo "🎉 Installation complete!"
echo "👉 Run with: python3 bot.py OR docker-compose up -d"
