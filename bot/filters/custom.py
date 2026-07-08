from pyrogram import filters
from bot.config.settings import settings


def owner_only():
    return filters.user(settings.OWNER_IDS)


def sudo_only():
    return filters.user(settings.OWNER_IDS + settings.SUDO_IDS)


def not_banned():
    async def func(_, __, message):
        from bot.database.db import database
        user = await database.get_user(message.from_user.id)
        return user and not user.get("is_banned", False)
    return filters.create(func, "not_banned")


def maintenance_off():
    async def func(_, __, message):
        return not settings.MAINTENANCE_MODE
    return filters.create(func, "maintenance_off")
