#!/bin/bash

echo "☁ Python Bot Cloud - Setup Script"
echo "=================================="

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "📁 Creating directories..."
mkdir -p downloads temp logs

echo "📝 Creating .env from example..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠ Please edit .env with your configuration!"
fi

echo ""
echo "✅ Setup complete!"
echo "➡ Run: python main.py"
