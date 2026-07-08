import functools
import logging
from bot.config.settings import settings
from bot.database.db import database

logger = logging.getLogger(__name__)


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        if message.from_user.id not in settings.OWNER_IDS:
            await message.reply_text("<b>❌ Unauthorized</b>")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def sudo_only(func):
    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        if message.from_user.id not in settings.OWNER_IDS + settings.SUDO_IDS:
            await message.reply_text("<b>❌ Unauthorized</b>")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def catch_errors(func):
    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Handler error: {e}")
            await message.reply_text(f"<b>❌ Error:</b> <code>{str(e)[:200]}</code>")
    return wrapper


def rate_limit(func):
    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        from bot.utils.security import is_rate_limited
        try:
            from redis import Redis
            cache = Redis.from_url(settings.REDIS_URI)
            if is_rate_limited(message.from_user.id, cache):
                await message.reply_text("<b>⚠ Rate limited. Please wait.</b>")
                return
        except Exception:
            pass
        return await func(client, message, *args, **kwargs)
    return wrapper
