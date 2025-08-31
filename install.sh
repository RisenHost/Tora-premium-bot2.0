#!/bin/bash
set -e

echo "🚀 Installing bot dependencies..."

apt-get update -y
apt-get install -y python3 python3-pip curl git jq docker.io docker-compose tmate

pip3 install -r requirements.txt

# Ask for Bot Token
if [ ! -f ".env" ]; then
  read -p "🤖 Enter your Discord Bot Token: " BOT_TOKEN
  echo "DISCORD_TOKEN=$BOT_TOKEN" > .env
  echo "✅ Token saved in .env"
else
  echo "ℹ️ .env already exists, skipping token input."
fi

echo "✅ Setup complete!"
echo "👉 Run with: python3 bot.py"
echo "👉 Or: docker-compose up -d"
