#!/bin/bash
set -e

echo "🚀 Installing bot dependencies..."

apt-get update -y
apt-get install -y python3 python3-pip curl git jq docker.io tmate

pip3 install -r requirements.txt

echo "✅ Done. Run with: python3 bot.py"
