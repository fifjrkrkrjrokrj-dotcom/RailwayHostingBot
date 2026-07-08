from pyrogram import Client, filters
from pyrogram.types import Message
from bot.config.constants import START_CAPTION
from bot.config.settings import settings
from bot.database.db import database
from bot.keyboards.main import start_keyboard, force_sub_keyboard
from bot.utils.formatters import format_timestamp


@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    user_id = user.id

    db_user = await database.get_user(user_id)
    if not db_user:
        referred_by = None
        if len(message.text.split()) > 1:
            try:
                ref_data = message.text.split()[1]
                if ref_data.startswith("ref_"):
                    ref_code = ref_data[4:]
                    ref_doc = await database.get_referral_by_code(ref_code)
                    if ref_doc and ref_doc["user_id"] != user_id:
                        referred_by = ref_doc["user_id"]
            except Exception:
                pass
        await database.create_user(user_id, user.username or "", user.first_name or "", referred_by)

    is_owner = user_id in settings.OWNER_IDS

    await message.reply_text(
        START_CAPTION.format(user=user.first_name or "user"),
        reply_markup=start_keyboard(is_owner),
        disable_web_page_preview=True,
    )

    if is_owner:
        return

    channels = await database.get_all_channels()
    if channels:
        not_joined = []
        for ch in channels:
            try:
                member = await client.get_chat_member(ch["channel_id"], user_id)
                if member.status in ("left", "kicked"):
                    not_joined.append(ch)
            except Exception:
                not_joined.append(ch)
        if not_joined:
            await message.reply_text(
                "⚠ Join Required Channels",
                reply_markup=force_sub_keyboard(not_joined),
            )


@Client.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    from bot.config.constants import HELP_TEXT
    await message.reply_text(
        HELP_TEXT,
        reply_markup=start_keyboard(message.from_user.id in settings.OWNER_IDS),
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("ping") & filters.private)
async def ping_handler(client: Client, message: Message):
    import time
    start = time.time()
    msg = await message.reply_text("🏓 Pong!")
    end = time.time()
    ping = round((end - start) * 1000, 2)
    await msg.edit_text(f"🏓 Pong! `{ping}ms`")


@Client.on_message(filters.command("stats") & filters.private & filters.user(settings.OWNER_IDS))
async def stats_handler(client: Client, message: Message):
    total_users = await database.count_users()
    active_deployments = await database.count_active_deployments()
    total_deployments = await database.count_total_deployments()
    active_tokens = await database.count_active_tokens()
    await message.reply_text(
        f"**📊 Bot Statistics**\n\n"
        f"👥 **Users:** {total_users}\n"
        f"🤖 **Active Deployments:** {active_deployments}\n"
        f"📦 **Total Deployments:** {total_deployments}\n"
        f"🚂 **Active Tokens:** {active_tokens}",
        reply_markup=start_keyboard(True),
    )
