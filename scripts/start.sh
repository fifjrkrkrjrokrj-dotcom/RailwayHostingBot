#!/bin/bash

echo "☁ Starting Python Bot Cloud..."
echo "=============================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "cp .env.example .env and edit it first."
    exit 1
fi

# Create directories
mkdir -p downloads temp logs

# Start the bot
echo "🚀 Starting bot..."
python main.py
