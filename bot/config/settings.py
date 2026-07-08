import os
from typing import Optional, List
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    API_ID: int = int(os.getenv("API_ID", 0))
    API_HASH: str = os.getenv("API_HASH", "")
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "hosting_bot")
    REDIS_URI: str = os.getenv("REDIS_URI", "redis://localhost:6379/0")
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))

    OWNER_IDS: List[int] = [int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x]
    SUDO_IDS: List[int] = [int(x) for x in os.getenv("SUDO_IDS", "").split(",") if x]
    LOG_GROUP_ID: int = int(os.getenv("LOG_GROUP_ID", 0))
    ERROR_LOG_ID: int = int(os.getenv("ERROR_LOG_ID", 0))

    DOMAIN: str = os.getenv("DOMAIN", "localhost")
    PORT: int = int(os.getenv("PORT", 8000))
    WS_PORT: int = int(os.getenv("WS_PORT", 8765))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-change-me")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "encryption-key-change-me")

    DEFAULT_RAM: int = int(os.getenv("DEFAULT_RAM", 256))
    DEFAULT_CPU: int = int(os.getenv("DEFAULT_CPU", 1))
    MAX_DEPLOY_TIMEOUT: int = int(os.getenv("MAX_DEPLOY_TIMEOUT", 300))
    MAX_RUNTIME_HOURS: int = int(os.getenv("MAX_RUNTIME_HOURS", 24))

    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN", None)
    RAILWAY_API_BASE: str = "https://backboard.railway.app/graphql/v2"

    RATE_LIMIT: int = int(os.getenv("RATE_LIMIT", 5))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", 60))
    MAX_ZIP_SIZE: int = int(os.getenv("MAX_ZIP_SIZE", 50 * 1024 * 1024))
    ALLOWED_EXTENSIONS: List[str] = ["py", "txt", "env", "yml", "yaml", "json", "cfg", "ini", "sh", "toml"]

    FORCE_SUB_INTERVAL: int = int(os.getenv("FORCE_SUB_INTERVAL", 300))
    REFERRAL_BONUS: int = int(os.getenv("REFERRAL_BONUS", 10))
    DAILY_REWARD: int = int(os.getenv("DAILY_REWARD", 5))

    UPSTREAM_REPO: str = os.getenv("UPSTREAM_REPO", "")
    UPSTREAM_BRANCH: str = os.getenv("UPSTREAM_BRANCH", "main")

    BOT_NAME: str = "Python Bot Cloud"
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "PythonBotCloudBot")
    BOT_VERSION: str = "7.0.0"
    START_VIDEO: str = os.getenv("START_VIDEO", "")

    MAINTENANCE_MODE: bool = os.getenv("MAINTENANCE_MODE", "False").lower() == "true"

    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
    DOWNLOADS_DIR: str = os.getenv("DOWNLOADS_DIR", "downloads")


settings = Settings()
