from pyrogram import Client, filters
from pyrogram.types import Message
from bot.config.settings import settings
from bot.database.db import database
from bot.keyboards.main import admin_keyboard, confirmation_keyboard
from bot.utils.security import validate_railway_token
from railway.token_manager import token_manager
from bot.deployment.engine import deployment_engine


@Client.on_message(filters.command("admin") & filters.private & filters.user(settings.OWNER_IDS))
async def admin_panel_handler(client: Client, message: Message):
    await message.reply_text(
        "<blockquote><b>⚙ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ</b></blockquote>\n\n"
        "<b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ.</b>\n"
        "<b>ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ᴛʜᴇ sʏsᴛᴇᴍ.</b>",
        reply_markup=admin_keyboard(),
    )


@Client.on_message(filters.command("addtoken") & filters.private & filters.user(settings.OWNER_IDS))
async def add_token_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage:</b> <code>/addtoken RAILWAY_TOKEN</code>")
        return
    token = parts[1].strip()
    if not validate_railway_token(token):
        await message.reply_text("<b>❌ Invalid Railway token format</b>")
        return
    try:
        doc = await token_manager.add_token(token, message.from_user.id)
        await message.reply_text(f"<b>✅ Token added successfully</b>\n\n<b>Token:</b> <code>{token[:8]}...</code>")
    except ValueError as e:
        await message.reply_text(f"<b>❌ {str(e)}</b>")


@Client.on_message(filters.command("removetoken") & filters.private & filters.user(settings.OWNER_IDS))
async def remove_token_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage:</b> <code>/removetoken TOKEN</code>")
        return
    token = parts[1].strip()
    await token_manager.remove_token(token)
    await message.reply_text("<b>✅ Token removed</b>")


@Client.on_message(filters.command("addchannel") & filters.private & filters.user(settings.OWNER_IDS))
async def add_channel_handler(client: Client, message: Message):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.reply_text("<b>Usage:</b> <code>/addchannel CHANNEL_ID INVITE_LINK [NAME]</code>")
        return
    try:
        channel_id = int(parts[1])
        invite_link = parts[2]
        name = parts[3] if len(parts) > 3 else ""
        await database.add_channel(channel_id, invite_link, name)
        await message.reply_text(f"<b>✅ Channel added:</b> {name or channel_id}")
    except ValueError:
        await message.reply_text("<b>❌ Invalid channel ID</b>")


@Client.on_message(filters.command("removechannel") & filters.private & filters.user(settings.OWNER_IDS))
async def remove_channel_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage:</b> <code>/removechannel CHANNEL_ID</code>")
        return
    try:
        channel_id = int(parts[1])
        await database.remove_channel(channel_id)
        await message.reply_text("<b>✅ Channel removed</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid channel ID</b>")


@Client.on_message(filters.command("channels") & filters.private & filters.user(settings.OWNER_IDS))
async def list_channels_handler(client: Client, message: Message):
    channels = await database.get_all_channels()
    if not channels:
        await message.reply_text("<b>No channels configured</b>")
        return
    text = "<blockquote><b>📢 ᴄᴏɴғɪɢᴜʀᴇᴅ ᴄʜᴀɴɴᴇʟs</b></blockquote>\n\n"
    for ch in channels:
        text += f"<b>📌 {ch.get('name', 'Unnamed')}</b>\n"
        text += f"<b>  ID:</b> <code>{ch['channel_id']}</code>\n"
        text += f"<b>  Link:</b> {ch.get('invite_link', 'N/A')}\n\n"
    await message.reply_text(text)


@Client.on_message(filters.command("broadcast") & filters.private & filters.user(settings.OWNER_IDS))
async def broadcast_handler(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("<b>Reply to a message to broadcast it to all users</b>")
        return
    users = await database.get_all_users()
    success = 0
    failed = 0
    status_msg = await message.reply_text("<b>📢 Broadcasting...</b>")
    for user in users:
        try:
            await message.reply_to_message.copy(user["user_id"])
            success += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"<b>📢 Broadcast Complete</b>\n\n"
        f"<b>✅ Sent:</b> {success}\n"
        f"<b>❌ Failed:</b> {failed}"
    )


@Client.on_message(filters.command("ban") & filters.private & filters.user(settings.OWNER_IDS))
async def ban_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage:</b> <code>/ban USER_ID [REASON]</code>")
        return
    try:
        user_id = int(parts[1])
        reason = " ".join(parts[2:]) if len(parts) > 2 else "No reason"
        await database.update_user(user_id, {"is_banned": True, "ban_reason": reason})
        await message.reply_text(f"<b>✅ User {user_id} banned</b>\n<b>Reason:</b> {reason}")
    except ValueError:
        await message.reply_text("<b>❌ Invalid user ID</b>")


@Client.on_message(filters.command("unban") & filters.private & filters.user(settings.OWNER_IDS))
async def unban_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage:</b> <code>/unban USER_ID</code>")
        return
    try:
        user_id = int(parts[1])
        await database.update_user(user_id, {"is_banned": False, "ban_reason": ""})
        await message.reply_text(f"<b>✅ User {user_id} unbanned</b>")
    except ValueError:
        await message.reply_text("<b>❌ Invalid user ID</b>")
