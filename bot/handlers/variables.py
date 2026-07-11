import io
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.config.settings import settings
from bot.database.db import database
from bot.keyboards.main import variable_keyboard, my_bot_keyboard
from bot.utils.formatters import parse_env_content, format_variables_for_display
from bot.utils.security import encrypt_value, decrypt_value
from railway.client import RailwayClient


@Client.on_message(filters.command("vars") & filters.private)
async def vars_handler(client: Client, message: Message):
    await message.reply_text(
        "<blockquote><b>🔧 ᴠᴀʀɪᴀʙʟᴇ ᴍᴀɴᴀɢᴇʀ</b></blockquote>\n\n"
        "<b>ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴇɴᴠɪʀᴏɴᴍᴇɴᴛ ᴠᴀʀɪᴀʙʟᴇs.</b>",
        reply_markup=variable_keyboard(),
    )


@Client.on_message(filters.text & filters.private & filters.regex(r"^[\w_]+=.+"))
async def handle_single_variable(client: Client, message: Message):
    user_id = message.from_user.id
    lines = message.text.strip().splitlines()
    parsed_vars = {}
    for line in lines:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            parsed_vars[key.strip()] = value.strip().strip('"').strip("'")

    if not parsed_vars:
        return

    # Check if this matches DOMAIN=yourdomain.com
    first_line = message.text.strip().splitlines()[0]
    if "=" in first_line:
        key, value = first_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.upper() == "DOMAIN" and "." in value:
            dep = await database.get_user_deployment(user_id)
            if not dep:
                await message.reply_text("<b>❌ No active deployment found</b>")
                return
            status_msg = await message.reply_text(f"<b>🌐 Adding custom domain <code>{value}</code>...</b>")
            r_client = RailwayClient(dep["railway_token"])
            try:
                res = await r_client.create_custom_domain(dep["project_id"], dep["environment_id"], dep["service_id"], value)
                if res and res.get("domain"):
                    url = f"https://{value}"
                    await database.update_deployment(dep["deployment_id"], {"url": url})
                    await status_msg.edit_text(
                        f"<b>✅ Custom domain added successfully!</b>\n\n"
                        f"<b>Domain:</b> <code>{url}</code>\n"
                        f"Please ensure your DNS CNAME points to Railway."
                    )
                else:
                    await status_msg.edit_text("<b>❌ Failed to add custom domain.</b>")
            except Exception as e:
                await status_msg.edit_text(f"<b>❌ Error: {str(e)}</b>")
            finally:
                await r_client.close()
            return

    from bot.deployment.engine import DEPLOY_CACHE
    # ALWAYS check pending cache first — variables go only to pending deploy
    user_entries = [(did, d) for did, d in DEPLOY_CACHE.items() if d.get("user_id") == user_id]
    if user_entries:
        target_id, target_data = user_entries[-1]
        target_data.setdefault("variables", {}).update(parsed_vars)
        var_str = "\n".join([f"<b>{k}</b> = <code>{v[:20]}...</code>" for k, v in list(parsed_vars.items())[:5]])
        if len(parsed_vars) > 5:
            var_str += f"\n...and {len(parsed_vars) - 5} more"
        await message.reply_text(
            f"<b>✅ {len(parsed_vars)} Variables added to pending deployment:</b>\n\n{var_str}"
        )
        return

    # No pending cache — check for an existing active deployment
    dep = await database.get_user_deployment(user_id)
    if not dep:
        await message.reply_text("<b>❌ No active deployment or pending deployment found</b>")
        return

    # Only apply vars if user is in "edit variable" state
    user = await database.get_user(user_id)
    user_state = user.get("current_state") if user else ""
    if not user_state.startswith("var_"):
        await message.reply_text(
            "<b>⚠ You have an active bot running.</b>\n\n"
            "Use the <b>🔧 Setup Variables</b> button in your bot dashboard to edit variables.",
            reply_markup=my_bot_keyboard(True, dep["deployment_id"])
        )
        return

    variables = dep.get("variables", {})
    variables.update(parsed_vars)
    await database.update_deployment(dep["deployment_id"], {"variables": variables})

    status_msg = await message.reply_text("<b>⚙ Syncing variables to Railway...</b>")
    r_client = RailwayClient(dep["railway_token"])
    try:
        for k, v in parsed_vars.items():
            await r_client.set_environment_variable(dep["project_id"], dep["environment_id"], k, v, service_id=dep["service_id"])
        
        # Trigger redeployment to apply new variables
        new_dep_id = await r_client.create_deployment(dep["service_id"], dep["environment_id"])
        if new_dep_id:
            await database.update_deployment(dep["deployment_id"], {"railway_deployment_id": new_dep_id})

        var_str = "\n".join([f"<b>{k}</b> = <code>{v[:20]}...</code>" for k, v in list(parsed_vars.items())[:5]])
        if len(parsed_vars) > 5:
            var_str += f"\n...and {len(parsed_vars) - 5} more"
        await status_msg.edit_text(
            f"<b>✅ {len(parsed_vars)} Variables synced to Railway and bot is restarting:</b>\n\n{var_str}"
        )
    except Exception as e:
        await status_msg.edit_text(f"<b>❌ Failed to sync variables to Railway: {str(e)}</b>")
    finally:
        await r_client.close()


@Client.on_message(filters.document & filters.private)
async def handle_env_upload(client: Client, message: Message):
    if not message.document.file_name.endswith(".env"):
        return
    user_id = message.from_user.id
    dep = await database.get_user_deployment(user_id)
    if not dep:
        await message.reply_text("<b>❌ No active deployment found</b>")
        return

    status_msg = await message.reply_text("<b>📥 Reading .env file...</b>")
    try:
        import os as _os, uuid as _uuid
        env_path = _os.path.join(settings.TEMP_DIR, f"{_uuid.uuid4()}.env")
        await message.download(env_path)
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        _os.remove(env_path)
        parsed = parse_env_content(content)
        
        variables = dep.get("variables", {})
        variables.update(parsed)
        await database.update_deployment(dep["deployment_id"], {"variables": variables})
        
        # Sync with Railway in real-time
        await status_msg.edit_text("<b>⚙ Syncing variables to Railway...</b>")
        r_client = RailwayClient(dep["railway_token"])
        try:
            for k, v in parsed.items():
                await r_client.set_environment_variable(dep["project_id"], dep["environment_id"], k, v, service_id=dep["service_id"])
            
            # Trigger redeployment to apply variables
            new_dep_id = await r_client.create_deployment(dep["service_id"], dep["environment_id"])
            if new_dep_id:
                await database.update_deployment(dep["deployment_id"], {"railway_deployment_id": new_dep_id})
            
            await status_msg.edit_text(
                f"<b>✅ Imported and synced {len(parsed)} variables from .env file. Bot is restarting.</b>\n\n"
                + format_variables_for_display(parsed)
            )
        except Exception as e:
            await status_msg.edit_text(f"<b>❌ Failed to sync variables to Railway: {str(e)}</b>")
        finally:
            await r_client.close()
    except Exception as e:
        await status_msg.edit_text(f"<b>❌ Error: {str(e)}</b>")


@Client.on_message(filters.command("delvar") & filters.private)
async def handle_delete_variable(client: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        await message.reply_text("<b>❌ Please specify the key name. Example:</b>\n<code>/delvar BOT_TOKEN</code>")
        return
        
    key = message.command[1].strip()
    dep = await database.get_user_deployment(user_id)
    if not dep:
        await message.reply_text("<b>❌ No active deployment found</b>")
        return
        
    variables = dep.get("variables", {})
    if key not in variables:
        await message.reply_text(f"<b>❌ Variable <code>{key}</code> not found in your deployment</b>")
        return
        
    del variables[key]
    await database.update_deployment(dep["deployment_id"], {"variables": variables})
    
    status_msg = await message.reply_text(f"<b>🗑 Deleting variable <code>{key}</code> from Railway...</b>")
    r_client = RailwayClient(dep["railway_token"])
    try:
        success = await r_client.delete_environment_variable(dep["project_id"], dep["environment_id"], key, dep["service_id"])
        if success:
            new_dep_id = await r_client.create_deployment(dep["service_id"], dep["environment_id"])
            if new_dep_id:
                await database.update_deployment(dep["deployment_id"], {"railway_deployment_id": new_dep_id})
            await status_msg.edit_text(f"<b>✅ Variable <code>{key}</code> deleted from Railway. Bot is restarting.</b>")
        else:
            await status_msg.edit_text(f"<b>❌ Failed to delete variable <code>{key}</code> on Railway. Local entry removed.</b>")
    except Exception as e:
        await status_msg.edit_text(f"<b>❌ Error deleting variable: {str(e)}</b>")
    finally:
        await r_client.close()
