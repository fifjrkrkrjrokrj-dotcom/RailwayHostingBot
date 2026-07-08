import datetime
import math
import re
import os


def format_uptime(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_size(bytes_: int) -> str:
    if bytes_ == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(bytes_, 1024)))
    size = round(bytes_ / (1024 ** i), 2)
    return f"{size} {units[i]}"


def format_timestamp(dt=None) -> str:
    if dt is None:
        dt = datetime.datetime.utcnow()
    return dt.strftime("%H:%M:%S")


def parse_env_content(content: str) -> dict:
    variables = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                variables[key] = value
    return variables


def format_variables_for_display(vars_dict: dict, hide_sensitive: bool = True) -> str:
    sensitive_keys = ["BOT_TOKEN", "API_HASH", "API_ID", "MONGO_URI", "MONGO_URL", "STRING_SESSION", "SESSION_STRING", "SECRET_KEY"]
    lines = []
    for key, value in vars_dict.items():
        if hide_sensitive and key.upper() in sensitive_keys:
            value = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"
        lines.append(f"<b>{key}</b> = <code>{value}</code>")
    return "\n".join(lines)


def detect_framework(files: list) -> str:
    content = "\n".join(files).lower()
    if "from pyrogram" in content or "import pyrogram" in content:
        return "Pyrogram"
    if "from telethon" in content or "import telethon" in content:
        return "Telethon"
    if "from aiogram" in content or "import aiogram" in content:
        return "Aiogram"
    return "Unknown"


def detect_startup_file(files: list) -> str:
    starters = ["main.py", "bot.py", "app.py", "run.py", "start.py"]
    for file in files:
        fname = os.path.basename(file)
        if fname in starters:
            return fname
    return "main.py"


def is_python_project(files: list) -> bool:
    for f in files:
        if f.endswith(".py"):
            return True
    return False


def sanitize_filename(filename: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", filename)


def mask_sensitive(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def generate_progress_bar(percentage: float, length: int = 10) -> str:
    filled = int(percentage * length / 100)
    bar = "▓" * filled + "░" * (length - filled)
    return f"{bar} {percentage:.1f}%"
