import asyncio
import logging
import os
import sys
import time
import urllib.request
import json

# --- FIX NOTIMPLEMENTEDERROR FOR SUBPROCESSES ON UNIX ---
if sys.platform != "win32":
    try:
        watcher = asyncio.ThreadedChildWatcher()
        asyncio.get_event_loop_policy().set_child_watcher(watcher)
        print("Successfully set asyncio ThreadedChildWatcher for Unix.")
    except Exception as e:
        print(f"Warning: Failed to set ThreadedChildWatcher: {e}")
# --------------------------------------------------------


# --- FIX WORKING DIRECTORY AND TIME SYNC ---
# 1. Fix cwd so Pyrogram can find plugins in bot.handlers when run from parent dir
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

# 2. Telegram strictly requires the client time to be accurate.
# Since the system clock is in 2026, we monkey-patch time.time()
# using google.com's Date header which is robust against blocking.
import email.utils
try:
    req = urllib.request.Request('https://google.com', headers={'User-Agent': 'Mozilla/5.0'}, method='HEAD')
    with urllib.request.urlopen(req, timeout=5) as response:
        date_str = response.headers.get('Date')
        real_time = email.utils.parsedate_to_datetime(date_str).timestamp()
        time_offset = real_time - time.time()
        _original_time = time.time
        time.time = lambda: _original_time() + time_offset
        print(f"Monkey-patched time.time() with offset: {time_offset} seconds to fix Telegram MTProto sync.")
except Exception as e:
    print(f"Failed to fetch real time for monkey-patch: {e}")
# ------------------------------

# Force UTF-8 encoding for stdout to prevent cp1252 charmap errors with emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
try:
    import uvloop
    has_uvloop = True
except ImportError:
    has_uvloop = False
from pyrogram import Client, idle
from pyrogram.raw.core import Message
from pyrogram.raw.core.tl_object import TLObject
from pyrogram.raw.core.primitives.int import Int, Long
from io import BytesIO

@staticmethod
def patched_message_read(data: BytesIO, *args) -> "Message":
    msg_id = Long.read(data)
    seq_no = Int.read(data)
    length = Int.read(data)
    body = data.read(length)
    try:
        parsed_body = TLObject.read(BytesIO(body), *args)
        return Message(parsed_body, msg_id, seq_no, length)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to parse message body (likely unknown constructor), using dummy: {e}")
        class DummyBody(TLObject):
            QUALNAME = "types.UpdateShort"
            __slots__ = []
        return Message(DummyBody(), msg_id, seq_no, length)

Message.read = patched_message_read

from pyrogram.types import Message as PyMessage, CallbackQuery as PyCallbackQuery

# --- PATCH MESSAGE & CALLBACK REPLY/EDIT FOR FALLBACK AND DEFAULT BUTTONS ---

_original_send_message = Client.send_message

async def _patched_send_message(self, chat_id, text, *args, **kwargs):
    try:
        chat_id = int(chat_id)
    except Exception:
        pass

    no_buttons = kwargs.pop("no_buttons", False)
    reply_markup = kwargs.get("reply_markup")

    if not no_buttons and reply_markup is None and isinstance(chat_id, int) and chat_id > 0:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])
        kwargs["reply_markup"] = reply_markup

    if reply_markup is not None and hasattr(reply_markup, "to_dict") and "telegram" in type(reply_markup).__module__:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup.to_dict(),
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage", json=payload) as resp:
                    if resp.status == 200:
                        return None
                    else:
                        err_text = await resp.text()
                        logging.getLogger(__name__).error(f"Fallback send_message failed: {resp.status} - {err_text}")
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback send_message failed with exception: {api_err}")

    try:
        return await _original_send_message(self, chat_id, text, *args, **kwargs)
    except Exception as e:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            elif isinstance(reply_markup, dict):
                payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback send_message after failure failed: {api_err}")
        raise e

Client.send_message = _patched_send_message

_original_reply_text = PyMessage.reply_text

async def _patched_reply_text(self, text, reply_markup=None, **kwargs):
    no_buttons = kwargs.pop("no_buttons", False)
    
    if not no_buttons and reply_markup is None and self.chat.id > 0:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])

    if reply_markup is not None and hasattr(reply_markup, "to_dict") and "telegram" in type(reply_markup).__module__:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.chat.id,
            "text": text,
            "reply_markup": reply_markup.to_dict(),
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback reply_text failed: {api_err}")

    try:
        return await _original_reply_text(self, text, reply_markup=reply_markup, **kwargs)
    except Exception as e:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.chat.id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            elif isinstance(reply_markup, dict):
                payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback reply_text after failure failed: {api_err}")
        raise e

PyMessage.reply_text = _patched_reply_text

_original_edit_text = PyMessage.edit_text

async def _patched_edit_text(self, text, reply_markup=None, **kwargs):
    no_buttons = kwargs.pop("no_buttons", False)

    if not no_buttons and reply_markup is None and self.chat.id > 0:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])

    if reply_markup is not None and hasattr(reply_markup, "to_dict") and "telegram" in type(reply_markup).__module__:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.chat.id,
            "message_id": self.id,
            "text": text,
            "reply_markup": reply_markup.to_dict(),
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback edit_text failed: {api_err}")

    try:
        return await _original_edit_text(self, text, reply_markup=reply_markup, **kwargs)
    except Exception as e:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.chat.id,
            "message_id": self.id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            elif isinstance(reply_markup, dict):
                payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback edit_text after failure failed: {api_err}")
        raise e

PyMessage.edit_text = _patched_edit_text

_original_edit_message_text = PyCallbackQuery.edit_message_text

async def _patched_edit_message_text(self, text, reply_markup=None, **kwargs):
    no_buttons = kwargs.pop("no_buttons", False)

    chat_id = self.message.chat.id if self.message else 0
    if not no_buttons and reply_markup is None and chat_id > 0:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])

    if reply_markup is not None and hasattr(reply_markup, "to_dict") and "telegram" in type(reply_markup).__module__:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.message.chat.id,
            "message_id": self.message.id,
            "text": text,
            "reply_markup": reply_markup.to_dict(),
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback edit_message_text failed: {api_err}")

    try:
        return await _original_edit_message_text(self, text, reply_markup=reply_markup, **kwargs)
    except Exception as e:
        import aiohttp
        from bot.config.settings import settings
        payload = {
            "chat_id": self.message.chat.id,
            "message_id": self.message.id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", False)
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            elif isinstance(reply_markup, dict):
                payload["reply_markup"] = reply_markup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText", json=payload) as resp:
                    if resp.status == 200:
                        return None
        except Exception as api_err:
            logging.getLogger(__name__).error(f"Fallback edit_message_text after failure failed: {api_err}")
        raise e

PyCallbackQuery.edit_message_text = _patched_edit_message_text


from bot.config.settings import settings
from bot.database.db import database
from bot.workers.deployment_worker import deployment_worker
from bot.services.log_service import owner_log
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def start_bot():
    logger.info("Starting Python Bot Cloud...")
    logger.info(f"DEBUG: API_ID={settings.API_ID}, API_HASH='{settings.API_HASH}', BOT_TOKEN='{settings.BOT_TOKEN[:10]}...'")

    await database.connect()
    logger.info("Database connected")

    app = Client(
        "python_bot_cloud",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        bot_token=settings.BOT_TOKEN,
        plugins={"root": "bot"},
    )



    await owner_log.set_client(app)
    await deployment_worker.start()
    logger.info("Deployment worker started")

    await app.start()
    logger.info(f"Bot started as @{settings.BOT_USERNAME}")

    if settings.LOG_GROUP_ID:
        try:
            await app.send_message(
                settings.LOG_GROUP_ID,
                f"<b>🚀 Bot Started</b>\n\n<b>Version:</b> {settings.BOT_VERSION}\n<b>Status:</b> ✅ Running",
            )
        except Exception as e:
            logger.error(f"Failed to send startup log: {e}")

    api_task = asyncio.create_task(start_api())
    logger.info("API server task created")

    await idle()

    api_task.cancel()
    try:
        await api_task
    except asyncio.CancelledError:
        pass
    await deployment_worker.stop()
    await app.stop()
    await database.close()
    logger.info("Bot stopped")


async def start_api():
    config = uvicorn.Config(
        "api.server:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    if has_uvloop:
        uvloop.install()
    try:
        await start_bot()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
