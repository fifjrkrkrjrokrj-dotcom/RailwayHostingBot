import os
import uuid
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.config.settings import settings
from bot.database.db import database
from bot.keyboards.main import deploy_keyboard, my_bot_keyboard, variable_keyboard, confirmation_keyboard
from bot.deployment.engine import deployment_engine
from bot.utils.formatters import parse_env_content, format_variables_for_display, format_uptime
from bot.utils.security import scan_zip_for_threats
from github.client import github_client


@Client.on_message(filters.command("deploy") & filters.private)
async def deploy_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        await database.create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")

    existing = await database.get_user_deployment(user_id)
    if existing:
        await message.reply_text(
            "<b>⚠ You already have an active deployment!</b>\n\n"
            "<b>You can only have one deployment at a time.</b>\n"
            "<b>Please stop or delete your current bot first.</b>",
            reply_markup=my_bot_keyboard(True),
        )
        return

    await message.reply_text(
        "<blockquote><b>🚀 ᴅᴇᴘʟᴏʏ ᴍᴇɴᴜ</b></blockquote>\n\n"
        "<b>ᴄʜᴏᴏsᴇ ʏᴏᴜʀ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴍᴇᴛʜᴏᴅ:</b>\n\n"
        "<b>🐙 ɢɪᴛʜᴜʙ</b> — ᴅᴇᴘʟᴏʏ ғʀᴏᴍ ᴘᴜʙʟɪᴄ ʀᴇᴘᴏsɪᴛᴏʀʏ\n"
        "<b>📦 ᴢɪᴘ</b> — ᴜᴘʟᴏᴀᴅ ᴢɪᴘ ғɪʟᴇ\n\n"
        "<b>ᴏɴʟʏ ᴘʏᴛʜᴏɴ ᴛᴇʟᴇɢʀᴀᴍ ʙᴏᴛs ᴀʀᴇ sᴜᴘᴘᴏʀᴛᴇᴅ.</b>",
        reply_markup=deploy_keyboard(),
    )


@Client.on_message(filters.text & filters.private & filters.regex(r"^https?://(www\.)?github\.com/"))
async def handle_github_url(client: Client, message: Message):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        return

    existing = await database.get_user_deployment(user_id)
    if existing:
        await message.reply_text("<b>⚠ You already have a running deployment</b>")
        return

    url = message.text.strip()
    status_msg = await message.reply_text("<b>🔍 Scanning repository...</b>")

    parsed = github_client.parse_github_url(url)
    if not parsed:
        await status_msg.edit_text("<b>❌ Invalid GitHub URL</b>")
        return

    scan = await github_client.scan_repository(parsed["owner"], parsed["repo"], parsed["branch"])
    if not scan.get("success"):
        await status_msg.edit_text(f"<b>❌ {scan.get('error', 'Scan failed')}</b>")
        return

    preview_text = (
        f"<blockquote><b>📦 ʀᴇᴘᴏsɪᴛᴏʀʏ sᴄᴀɴ ʀᴇsᴜʟᴛ</b></blockquote>\n\n"
        f"<b>🐙 Repo:</b> {parsed['owner']}/{parsed['repo']}\n"
        f"<b>🌿 Branch:</b> {parsed['branch']}\n"
        f"<b>⚙ Framework:</b> {scan['framework']}\n"
        f"<b>🚀 Startup:</b> {scan['startup_file']}\n"
        f"<b>📄 requirements.txt:</b> {'✅' if scan['has_requirements'] else '❌'}\n"
        f"<b>🐳 Dockerfile:</b> {'✅' if scan['has_dockerfile'] else '❌'}\n\n"
        f"<b>Click below to start deployment. To add Environment Variables, simply send <code>KEY=VALUE</code> in the chat before clicking Deploy.</b>"
    )

    deploy_id = str(uuid.uuid4())[:8]
    from bot.deployment.engine import DEPLOY_CACHE
    DEPLOY_CACHE[deploy_id] = {
        "user_id": message.from_user.id,
        "type": "github",
        "url": url,
        "owner": parsed["owner"],
        "repo": parsed["repo"],
        "branch": parsed["branch"],
        "variables": {}
    }

    await status_msg.edit_text(
        preview_text,
        reply_markup=confirmation_keyboard(f"deploy_{deploy_id}"),
    )


@Client.on_message(filters.document & filters.private)
async def handle_zip_upload(client: Client, message: Message):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        return

    existing = await database.get_user_deployment(user_id)
    if existing:
        await message.reply_text("<b>⚠ You already have a running deployment</b>")
        return

    doc = message.document
    if not doc.file_name.lower().endswith(".zip"):
        await message.reply_text("<b>❌ Only ZIP files are supported</b>")
        return

    if doc.file_size > settings.MAX_ZIP_SIZE:
        await message.reply_text(f"<b>❌ File too large. Max: {settings.MAX_ZIP_SIZE // 1024 // 1024}MB</b>")
        return

    status_msg = await message.reply_text("<b>📥 Downloading ZIP file...</b>")

    file_path = os.path.join(settings.TEMP_DIR, f"{uuid.uuid4()}.zip")
    try:
        await message.download(file_path)
        with open(file_path, "rb") as f:
            zip_data = f.read()

        threats = scan_zip_for_threats(file_path)
        if threats:
            await status_msg.edit_text(
                f"<b>❌ Security threats detected!</b>\n\n" + "\n".join(f"• {t}" for t in threats[:5])
            )
            return

        from bot.utils.formatters import is_python_project, detect_framework, detect_startup_file
        import zipfile
        import io

        files = []
        contents = {}
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                files.append(info.filename)
                try:
                    contents[info.filename] = zf.read(info).decode("utf-8", errors="ignore")
                except Exception:
                    contents[info.filename] = ""

        if not is_python_project(files):
            await status_msg.edit_text("<b>❌ ZIP must contain a Python Telegram bot project</b>")
            return

        framework = detect_framework(list(contents.values()))
        startup_file = detect_startup_file(files)

        preview_text = (
            f"<blockquote><b>📦 ᴢɪᴘ sᴄᴀɴ ʀᴇsᴜʟᴛ</b></blockquote>\n\n"
            f"<b>📄 File:</b> {doc.file_name}\n"
            f"<b>📏 Size:</b> {doc.file_size / 1024:.1f} KB\n"
            f"<b>⚙ Framework:</b> {framework}\n"
            f"<b>🚀 Startup:</b> {startup_file}\n"
            f"<b>📄 requirements.txt:</b> {'✅' if 'requirements.txt' in files else '❌'}\n\n"
            f"<b>Click below to start deployment. To add Environment Variables, simply send <code>KEY=VALUE</code> in the chat before clicking Deploy.</b>"
        )

        deploy_id = str(uuid.uuid4())[:8]
        from bot.deployment.engine import DEPLOY_CACHE
        DEPLOY_CACHE[deploy_id] = {
            "user_id": message.from_user.id,
            "type": "zip",
            "zip_data": zip_data,
            "filename": doc.file_name,
            "variables": {}
        }

        await status_msg.edit_text(
            preview_text,
            reply_markup=confirmation_keyboard(f"deploy_{deploy_id}"),
        )

    except Exception as e:
        await status_msg.edit_text(f"<b>❌ Error: {str(e)}</b>")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
