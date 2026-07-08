# ☁ Python Bot Cloud — Enterprise Telegram Bot Hosting Platform

> **Deploy, manage, and scale Python Telegram bots directly from Telegram.**

---

## ✨ Features

- **🐙 GitHub Deployment** — Deploy from any public GitHub repository
- **📦 ZIP Upload** — Upload your bot as a ZIP file
- **⚡ Live Terminal** — Real-time deployment logs via WebSocket
- **🚂 Railway Integration** — Automatic Railway token management
- **🔄 Auto Token Rotation** — Zero-downtime migration between tokens
- **🔧 Variable Manager** — Full environment variable management
- **🔐 Security** — Malware scanning, rate limiting, encryption
- **📊 Analytics** — Real-time usage statistics and monitoring
- **👥 Multi-User** — Each user gets one isolated deployment
- **⚙ Admin Panel** — Full administrative control panel
- **💳 Payment System** — UPI-based plan purchases
- **🏆 Referral System** — Invite friends and earn points
- **💾 Dockerized** — Easy deployment with Docker Compose

## 🎯 Supported Frameworks

| Framework | Support |
|-----------|---------|
| Pyrogram  | ✅ Full |
| Telethon  | ✅ Full |
| Aiogram   | ✅ Full |

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- MongoDB 7+
- Redis 7+ (optional)
- Railway account with API tokens

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/python-bot-cloud.git
cd python-bot-cloud

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Run with Docker Compose
docker-compose up -d

# Or run directly
python main.py
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot Token | ✅ |
| `API_ID` | Telegram API ID | ✅ |
| `API_HASH` | Telegram API Hash | ✅ |
| `MONGO_URI` | MongoDB Connection URI | ✅ |
| `OWNER_IDS` | Comma-separated admin IDs | ✅ |
| `LOG_GROUP_ID` | Log group chat ID | ✅ |

## 📁 Project Structure

```
hosting-bot/
├── bot/
│   ├── handlers/        # Telegram command handlers
│   ├── callbacks/       # Callback query handlers
│   ├── keyboards/       # Inline keyboard layouts
│   ├── deployment/      # Deployment engine
│   ├── database/        # MongoDB operations
│   ├── workers/         # Background workers
│   ├── services/        # Logging services
│   ├── utils/           # Utilities & helpers
│   └── config/          # Configuration
├── api/                 # FastAPI + WebSocket server
├── github/              # GitHub API integration
├── railway/             # Railway API integration
├── docker/              # Docker configuration
├── nginx/               # Nginx configuration
├── main.py              # Entry point
├── Dockerfile           # Docker image
├── docker-compose.yml   # Docker Compose config
└── requirements.txt     # Python dependencies
```

## 🛠 Commands

### User Commands
- `/start` — Start the bot
- `/help` — Show help
- `/deploy` — Deploy a new bot
- `/vars` — Manage environment variables
- `/ping` — Check bot latency

### Admin Commands
- `/admin` — Open admin panel
- `/addtoken <token>` — Add Railway token
- `/removetoken <token>` — Remove Railway token
- `/addchannel <id> <link> [name]` — Add force sub channel
- `/removechannel <id>` — Remove force sub channel
- `/channels` — List force sub channels
- `/broadcast` — Broadcast to all users (reply to message)
- `/ban <user_id> [reason]` — Ban a user
- `/unban <user_id>` — Unban a user
- `/stats` — View bot statistics

## 🚂 Railway Token Management

The system supports automatic token pool management:
- Add unlimited Railway API tokens
- Automatic token rotation on failure
- Credit monitoring and alerts
- Deployment balancing across tokens
- Priority-based token selection

## 🔒 Security

- ZIP file malware scanning
- Rate limiting on all endpoints
- Environment variable encryption
- Token validation and rotation
- Admin-only sensitive commands
- Force subscribe verification
- Abuse detection system

## 📦 Deployment

### Deploying a Bot via GitHub

1. Click "Deploy Bot" → "Deploy via GitHub"
2. Send your public GitHub repository URL
3. Review the scan results
4. Confirm deployment
5. Wait for deployment to complete
6. Your bot is live! 🎉

### Deploying a Bot via ZIP

1. Click "Deploy Bot" → "Deploy via ZIP"
2. Upload your bot's ZIP file
3. System scans for security threats
4. Confirm deployment
5. Wait for deployment to complete
6. Your bot is live! 🎉

## 🐳 Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop services
docker-compose down
```

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 👨‍💻 Development

Built with:
- **[Pyrogram](https://github.com/pyrogram/pyrogram)** — Telegram MTProto API framework
- **[FastAPI](https://fastapi.tiangolo.com/)** — Modern web framework
- **[MongoDB](https://www.mongodb.com/)** — NoSQL database
- **[Motor](https://github.com/mongodb/motor)** — Async MongoDB driver
- **[Railway API](https://docs.railway.app/)** — Cloud deployment platform
- **[Docker](https://www.docker.com/)** — Containerization
