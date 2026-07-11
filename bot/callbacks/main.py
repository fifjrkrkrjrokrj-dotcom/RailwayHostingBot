import time
import asyncio
import logging
logger = logging.getLogger(__name__)
from pyrogram import Client
from pyrogram.types import CallbackQuery
from bot.config.settings import settings
from bot.config.constants import START_CAPTION, HELP_TEXT, PLANS_TEXT, ANALYTICS_TEMPLATE, TERMINAL_HEADER, ERROR_HEADER
from bot.database.db import database
from bot.keyboards.main import (
    start_keyboard, deploy_keyboard, my_bot_keyboard, variable_keyboard,
    admin_keyboard, confirmation_keyboard, force_sub_keyboard,
    support_keyboard, token_stats_keyboard, region_selection_keyboard,
    domain_manager_keyboard, domain_delete_keyboard,
)
from pyrogram.types import InlineKeyboardMarkup
from bot.deployment.engine import deployment_engine
from bot.utils.formatters import format_uptime, format_variables_for_display
from railway.token_manager import token_manager
from railway.client import RailwayClient
from github.client import github_client


async def get_deployment_from_callback(query, user_id: int):
    data = query.data
    has_uuid = False
    if len(data) >= 36:
        potential_uuid = data[-36:]
        if potential_uuid.count("-") == 4:
            has_uuid = True
            dep = await database.get_deployment(potential_uuid)
            if dep:
                return dep
    if not has_uuid:
        return await database.get_user_deployment(user_id)
    return None


@Client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    msg = query.message

    if not (data.startswith("rename_bot") or data.startswith("var_")):
        await database.update_user(user_id, {"current_state": None})

    handlers = {
        "main_menu": cb_main_menu,
        "deploy_menu": cb_deploy_menu,
        "deploy_github": cb_deploy_github,
        "deploy_zip": cb_deploy_zip,
        "my_bot": cb_my_bot,
        "profile": cb_profile,
        "plans": cb_plans,
        "analytics": cb_analytics,
        "help": cb_help,
        "referral": cb_referral,
        "updates": cb_updates,
        "support": cb_support,
        "live_terminal": cb_live_terminal,
        "runtime_logs": cb_runtime_logs,
        "runtime_stats": cb_runtime_stats,
        "edit_vars": cb_edit_vars,
        "restart_bot": cb_restart_bot,
        "stop_bot": cb_stop_bot,
        "delete_bot": cb_delete_bot,
        "view_url": cb_view_url,
        "check_join": cb_check_join,
        "refresh": cb_refresh,
        "admin_panel": cb_admin_panel,
        "admin_add_token": cb_admin_add_token,
        "admin_remove_token": cb_admin_remove_token,
        "admin_token_stats": cb_admin_token_stats,
        "admin_queue_stats": cb_admin_queue_stats,
        "admin_user_stats": cb_admin_user_stats,
        "admin_broadcast": cb_admin_broadcast,
        "admin_ban": cb_admin_ban,
        "admin_unban": cb_admin_unban,
        "admin_payments": cb_admin_payments,
        "admin_add_plan": cb_admin_add_plan,
        "admin_force_redeploy": cb_admin_force_redeploy,
        "admin_system_logs": cb_admin_system_logs,
        "admin_db_status": cb_admin_db_status,
        "admin_maintenance": cb_admin_maintenance,
        "admin_api_health": cb_admin_api_health,
        "admin_restrict_token": cb_admin_restrict_token,
        "admin_cleanup_workshops": cb_admin_cleanup_workshops,
        "admin_validate_tokens": cb_admin_validate_tokens,
        "var_add": cb_var_add,
        "var_edit": cb_var_edit,
        "var_delete": cb_var_delete,
        "var_view": cb_var_view,
        "var_import": cb_var_import,
        "var_export": cb_var_export,
        "var_upload_env": cb_var_upload_env,
        "var_paste": cb_var_paste,
        "var_backup": cb_var_backup,
        "var_restore": cb_var_restore,
        "var_encrypt": cb_var_encrypt,
        "var_reset": cb_var_reset,
        "support_contact": cb_support_contact,
        "faq": cb_faq,
        "developer": cb_developer,
        "change_region": cb_change_region,
        "domain_manager": cb_domain_manager,
        "dom_create_railway": cb_dom_create_railway,
        "dom_create_custom": cb_dom_create_custom,
        "dom_delete_menu": cb_dom_delete_menu,
        "download_logs": cb_download_logs,
        "redeploy": cb_redeploy,
        "redeploy_vars": cb_redeploy_vars,
        "rename_bot": cb_rename_bot,
    }

    matched_prefix = None
    if len(data) > 37:
        potential_prefix = data[:-37]
        potential_uuid = data[-36:]
        if potential_uuid.count("-") == 4:
            if potential_prefix in handlers:
                matched_prefix = potential_prefix

    handler = handlers.get(data) or (handlers.get(matched_prefix) if matched_prefix else None)
    try:
        if handler:
            await handler(client, query)
        elif data.startswith("selectregion_"):
            await cb_select_region(client, query)
        elif data.startswith("setregion_"):
            await cb_set_region(client, query)
        elif data.startswith("setregionactive_"):
            await cb_set_region_active(client, query)
        elif data.startswith("toggle_restrict_"):
            await cb_toggle_restrict(client, query)
        elif data.startswith("confirm_delete_dom_"):
            await cb_confirm_delete_dom(client, query)
        elif data.startswith("confirm_"):
            await cb_confirm(client, query)
        elif data.startswith("cancel_"):
            await cb_cancel(client, query)
        elif data.startswith("addvars_"):
            await query.answer("To add variables, simply send them in the chat using KEY=VALUE format. For example:\nBOT_TOKEN=123:ABC", show_alert=True)
        else:
            await query.answer("Unknown action")
    except Exception as e:
        logger.exception(f"Error handling callback {data}: {e}")
        try:
            await query.answer("An error occurred. Check notifications.", show_alert=True)
        except Exception:
            pass
        from bot.services.log_service import owner_log
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        err_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])
        try:
            await client.send_message(
                user_id,
                f"❌ <b>Error processing action:</b>\n<code>{str(e)}</code>",
                reply_markup=err_markup
            )
        except Exception as msg_err:
            logger.error(f"Failed to send error notification message to user: {msg_err}")


async def cb_main_menu(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    is_owner = user_id in settings.OWNER_IDS
    await query.message.edit_text(
        START_CAPTION.format(user=query.from_user.first_name or "user"),
        reply_markup=start_keyboard(is_owner),
    )
    await query.answer()


async def cb_deploy_menu(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    await query.message.edit_text(
        "<blockquote><b>🚀 ᴅᴇᴘʟᴏʏ ᴍᴇɴᴜ</b></blockquote>\n\n"
        "<b>Send your public GitHub repository link to deploy your Python Telegram bot.</b>\n\n"
        "<b>📌 Format:</b>\n"
        "<code>https://github.com/username/repository</code>\n\n"
        "<b>🐙 Only public GitHub repos are supported.</b>",
        reply_markup=deploy_keyboard(),
    )
    await query.answer()


async def cb_deploy_github(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<b>🐙 GitHub Deployment</b>\n\n"
        "<b>Send me your public GitHub repository URL.</b>\n\n"
        "<b>Example:</b>\n"
        "<code>https://github.com/username/repository</code>",
        reply_markup=confirmation_keyboard("back_deploy"),
    )
    await query.answer()


async def cb_deploy_zip(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<b>📦 ZIP Deployment</b>\n\n"
        "<b>Upload your bot's ZIP file directly.</b>\n\n"
        "<b>Requirements:</b>\n"
        "• Only Python Telegram bots\n"
        "• Max 50MB file size\n"
        "• Must include main.py or bot.py\n"
        "• requirements.txt recommended",
        reply_markup=confirmation_keyboard("back_deploy"),
    )
    await query.answer()


async def cb_my_bot(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    selected_dep_id = None
    if len(data) >= 36:
        potential_uuid = data[-36:]
        if potential_uuid.count("-") == 4:
            selected_dep_id = potential_uuid

    if selected_dep_id:
        await query.answer("Fetching dashboard details...")
        dep = await database.get_deployment(selected_dep_id)
        if dep:
            await database.update_user(user_id, {"active_management_id": dep["deployment_id"]})
    else:
        await query.answer()
        deps = await database.get_all_user_deployments(user_id)
        if len(deps) >= 1:
            from bot.keyboards.main import btn
            buttons = []
            for d in deps:
                status_emoji = "🟢" if d.get("status") == "running" else "🟡" if d.get("status") == "deploying" else "🔴"
                name = d.get("dashboard_name") or f"{d.get('framework', 'Bot')} ({d['deployment_id'][:8]})"
                label = f"{status_emoji} {name}"
                buttons.append([btn(label, f"my_bot_{d['deployment_id']}")])
            buttons.append([btn("🚀 Deploy New Bot", "deploy_menu")])
            buttons.append([btn("◀ Back", "main_menu")])
            await query.message.edit_text(
                "<blockquote><b>🤖 ʏᴏᴜʀ ʙᴏᴛs</b></blockquote>\n\n"
                "<b>Choose a bot to manage:</b>",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        else:
            dep = None

    if not dep:
        await query.message.edit_text(
            "<b>🤖 ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ᴀᴄᴛɪᴠᴇ ʙᴏᴛ</b>\n\n"
            "<b>ᴅᴇᴘʟᴏʏ ʏᴏᴜʀ ғɪʀsᴛ ʙᴏᴛ ɴᴏᴡ!</b>",
            reply_markup=my_bot_keyboard(False),
        )
    else:
        status = dep.get("status", "unknown")
        framework = dep.get("framework", "Unknown")
        url = dep.get("url", "N/A")
        runtime = time.time() - dep.get("created_at", time.time())

        # Get token details and show credits & usage
        token_doc = await database.get_railway_token(dep["railway_token"])
        cpu_usage_str = "N/A"
        ram_usage_str = "N/A"
        net_usage_str = "N/A"
        if token_doc:
            try:
                # Live credit update
                r_client = RailwayClient(token_doc["token"])
                info = await r_client.get_account_info()
                workspaces = info.get("me", {}).get("workspaces", [])
                if workspaces:
                    customer = workspaces[0].get("customer", {})
                    credits = customer.get("remainingUsageCreditBalance")
                    if credits is None:
                        credit_bal = customer.get("creditBalance", -5.0)
                        credits = abs(credit_bal) if credit_bal is not None else 5.0
                    
                    # Update database with the live credit
                    await database.db.railway_tokens.update_one(
                        {"token": token_doc["token"]},
                        {"$set": {"credits": credits}}
                    )
                    token_doc["credits"] = credits

                # Fetch project usage from Railway API
                usage_res = await r_client.get_project_usage(dep["project_id"])
                proj_data = usage_res.get("project") or {}
                usage_data = proj_data.get("usage") or {}
                if usage_data:
                    cpu_val = usage_data.get("cpu")
                    mem_val = usage_data.get("memory")
                    net_val = usage_data.get("network")

                    if cpu_val is not None:
                        if cpu_val < 1.0:
                            cpu_usage_str = f"{cpu_val * 100:.1f}%"
                        else:
                            cpu_usage_str = f"{cpu_val:.1f} cores"
                    
                    if mem_val is not None:
                        if mem_val > 1024 * 1024:
                            ram_usage_str = f"{mem_val / (1024 * 1024):.1f} MB"
                        elif mem_val > 1024:
                            ram_usage_str = f"{mem_val / 1024:.1f} KB"
                        else:
                            ram_usage_str = f"{mem_val:.1f} Bytes"
                    
                    if net_val is not None:
                        if net_val > 1024 * 1024 * 1024:
                            net_usage_str = f"{net_val / (1024 * 1024 * 1024):.1f} GB"
                        elif net_val > 1024 * 1024:
                            net_usage_str = f"{net_val / (1024 * 1024):.1f} MB"
                        elif net_val > 1024:
                            net_usage_str = f"{net_val / 1024:.1f} KB"
                        else:
                            net_usage_str = f"{net_val:.1f} Bytes"

                await r_client.close()
            except Exception as e:
                logger.error(f"Failed to fetch live credits/usage for token: {e}")

        credits_str = f"${token_doc['credits']:.2f}" if (token_doc and "credits" in token_doc) else "N/A"
        bot_title = dep.get("dashboard_name") or f"{framework} ({dep['deployment_id'][:8]})"

        text = (
            f"<blockquote><b>🤖 ᴅᴀsʜʙᴏᴀʀᴅ: {bot_title}</b></blockquote>\n\n"
            f"<b>📊 Status:</b> {status}\n"
            f"<b>⚙ Framework:</b> {framework}\n"
            f"<b>🌍 URL:</b> <code>{url}</code>\n"
            f"<b>⏱ Runtime:</b> {format_uptime(runtime)}\n"
            f"<b>🔄 Restarts:</b> {dep.get('restart_count', 0)}\n"
            f"<b>💳 Railway Credit:</b> <code>{credits_str}</code>\n\n"
            f"<blockquote><b>📈 ʀᴀɪʟᴡᴀʏ ᴜsᴀɢᴇ</b></blockquote>\n"
            f"<b>💻 CPU Usage:</b> <code>{cpu_usage_str}</code>\n"
            f"<b>🧠 RAM Usage:</b> <code>{ram_usage_str}</code>\n"
            f"<b>🌐 Network Usage:</b> <code>{net_usage_str}</code>\n\n"
            f"<i>Selected Bot: <code>{dep['deployment_id'][:8]}</code></i>"
        )
        await query.message.edit_text(text, reply_markup=my_bot_keyboard(True, dep["deployment_id"]))


async def cb_profile(client: Client, query: CallbackQuery):
    await query.answer()
    user_id = query.from_user.id
    user = await database.get_user(user_id)
    if not user:
        user = await database.create_user(user_id, query.from_user.username or "", query.from_user.first_name or "")
    wallet = await database.get_wallet(user_id)
    if not wallet:
        wallet = await database.create_wallet(user_id)

    text = (
        f"<blockquote><b>👤 ᴘʀᴏғɪʟᴇ</b></blockquote>\n\n"
        f"<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>👤 Name:</b> {query.from_user.first_name}\n"
        f"<b>💎 Plan:</b> {user.get('plan', 'free').title()}\n"
        f"<b>🤖 Deployments:</b> {user.get('total_deployments', 0)}\n"
        f"<b>💰 Balance:</b> ${wallet.get('balance', 0):.2f}\n"
        f"<b>⭐ Points:</b> {user.get('points', 0)}"
    )
    await query.message.edit_text(text, reply_markup=start_keyboard(user_id in settings.OWNER_IDS))


async def cb_plans(client: Client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text(PLANS_TEXT, reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS))


async def cb_analytics(client: Client, query: CallbackQuery):
    await query.answer()
    total_users = await database.count_users()
    active_deployments = await database.count_active_deployments()
    total_deployments = await database.count_total_deployments()
    active_tokens = await database.count_active_tokens()
    try:
        db_stats = await database.get_db_stats()
        db_size = f"{db_stats.get('dataSize', 0) / 1024 / 1024:.1f} MB"
    except Exception:
        db_size = "N/A"

    text = ANALYTICS_TEMPLATE.format(
        total_users=total_users,
        active_deployments=active_deployments,
        total_deployments=total_deployments,
        queue_size=0,
        railway_tokens=active_tokens,
        db_size=db_size,
        avg_uptime="N/A",
    )
    await query.message.edit_text(text, reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS))


async def cb_help(client: Client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text(HELP_TEXT, reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS))


async def cb_referral(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    user = await database.get_user(user_id)
    ref_code = f"ref_{user_id}_pbc"
    text = (
        f"<blockquote><b>🏆 ʀᴇғᴇʀʀᴀʟ sʏsᴛᴇᴍ</b></blockquote>\n\n"
        f"<b>ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs ᴀɴᴅ ᴇᴀʀɴ ᴘᴏɪɴᴛs!</b>\n\n"
        f"<b>🔗 Your Referral Link:</b>\n"
        f"<code>https://t.me/{settings.BOT_USERNAME}?start={ref_code}</code>\n\n"
        f"<b>⭐ Your Points:</b> {user.get('points', 0)}\n"
        f"<b>🎁 Bonus per referral:</b> {settings.REFERRAL_BONUS} pts\n"
        f"<b>🎉 Daily reward:</b> {settings.DAILY_REWARD} pts"
    )
    await query.message.edit_text(text, reply_markup=start_keyboard(user_id in settings.OWNER_IDS))
    await query.answer()


async def cb_updates(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<blockquote><b>📢 ᴜᴘᴅᴀᴛᴇs</b></blockquote>\n\n"
        f"<b>⚡ Bot Version:</b> {settings.BOT_VERSION}\n"
        "<b>✅ Latest features and improvements.</b>",
        reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS),
    )
    await query.answer()

async def cb_support(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<blockquote><b>📞 sᴜᴘᴘᴏʀᴛ ᴄᴇɴᴛᴇʀ</b></blockquote>\n\n"
        "<b>ɴᴇᴇᴅ ʜᴇʟᴘ? ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ.</b>",
        reply_markup=support_keyboard(),
    )
    await query.answer()


# --- LOGS AUTO-REFRESH SYSTEM ---
ACTIVE_REFRESHES = {}

async def start_auto_refresh(client, chat_id, message_id, deployment_id, log_type):
    key = (chat_id, message_id)
    if key in ACTIVE_REFRESHES:
        try:
            ACTIVE_REFRESHES[key].cancel()
        except Exception:
            pass
            
    async def refresh_loop():
        try:
            for _ in range(15): # Refresh every 4 seconds for 60 seconds total
                await asyncio.sleep(4)
                try:
                    msg = await client.get_messages(chat_id, message_id)
                    if not msg or not msg.text:
                        break
                    # Verify user is still on the log view
                    expected_kw = "ʙᴜɪʟᴅ ʟᴏɢs" if log_type == "build" else "ᴅᴇᴘʟᴏʏ ʟᴏɢs"
                    expected_kw_old = "ʟɪᴠᴇ ʙᴜɪʟᴅ ᴛᴇʀᴍɪɴᴀʟ" if log_type == "build" else "ᴀᴘᴘʟɪᴄᴀᴛɪᴏɴ ʀᴜɴᴛɪᴍᴇ ʟᴏɢs"
                    if expected_kw not in msg.text and expected_kw_old not in msg.text:
                        break
                except Exception:
                    break
                    
                if log_type == "build":
                    logs = await deployment_engine.get_build_logs(deployment_id, limit=50)
                    full_text = (
                        f"🛠 <b>ʙᴜɪʟᴅ ʟᴏɢs</b> (ID: <code>{deployment_id[:8]}</code>)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"<code>{logs}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔄 <i>Auto-refreshing dynamically...</i>"
                    )
                else:
                    logs = await deployment_engine.get_runtime_logs(deployment_id, limit=50)
                    full_text = (
                        f"🚀 <b>ᴅᴇᴘʟᴏʏ ʟᴏɢs</b> (ID: <code>{deployment_id[:8]}</code>)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"<code>{logs}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔄 <i>Auto-refreshing dynamically...</i>"
                    )
                    
                if len(full_text) > 4000:
                    full_text = full_text[-4000:]
                    
                try:
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=full_text,
                        reply_markup=my_bot_keyboard(True, deployment_id)
                    )
                except Exception as e:
                    if "MESSAGE_NOT_MODIFIED" in str(e) or "not modified" in str(e).lower():
                        continue
                    break
        except asyncio.CancelledError:
            pass
        finally:
            ACTIVE_REFRESHES.pop(key, None)

    task = asyncio.create_task(refresh_loop())
    ACTIVE_REFRESHES[key] = task


async def cb_live_terminal(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.answer("Fetching build logs...")
    logs = await deployment_engine.get_build_logs(dep["deployment_id"], limit=50)
    full_text = (
        f"🛠 <b>ʙᴜɪʟᴅ ʟᴏɢs</b> (ID: <code>{dep['deployment_id'][:8]}</code>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{logs}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 <i>Auto-refreshing dynamically...</i>"
    )
    if len(full_text) > 4000:
        full_text = full_text[-4000:]
    await query.message.edit_text(
        full_text,
        reply_markup=my_bot_keyboard(True, dep["deployment_id"]),
    )
    await start_auto_refresh(client, query.message.chat.id, query.message.id, dep["deployment_id"], "build")


async def cb_runtime_logs(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.answer("Fetching deploy logs...")
    logs = await deployment_engine.get_runtime_logs(dep["deployment_id"], limit=50)
    full_text = (
        f"🚀 <b>ᴅᴇᴘʟᴏʏ ʟᴏɢs</b> (ID: <code>{dep['deployment_id'][:8]}</code>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{logs}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 <i>Auto-refreshing dynamically...</i>"
    )
    if len(full_text) > 4000:
        full_text = full_text[-4000:]
    await query.message.edit_text(full_text, reply_markup=my_bot_keyboard(True, dep["deployment_id"]))
    await start_auto_refresh(client, query.message.chat.id, query.message.id, dep["deployment_id"], "runtime")



async def cb_runtime_stats(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.answer("Fetching stats...")
    stats = await deployment_engine.get_runtime_stats(dep["deployment_id"])
    text = (
        f"<blockquote><b>📊 ʀᴜɴᴛɪᴍᴇ sᴛᴀᴛs</b></blockquote>\n\n"
        f"<b>📊 Status:</b> {stats.get('status', 'N/A')}\n"
        f"<b>⏱ Uptime:</b> {format_uptime(stats.get('uptime', 0))}\n"
        f"<b>🌍 URL:</b> <code>{stats.get('url', 'N/A')}</code>\n"
        f"<b>🔄 Restarts:</b> {stats.get('restart_count', 0)}\n"
        f"<b>⚙ Framework:</b> {stats.get('framework', 'N/A')}\n"
        f"<b>🚀 Startup:</b> {stats.get('startup_file', 'N/A')}\n\n"
        f"<i>Selected Bot: <code>{dep['deployment_id'][:8]}</code></i>"
    )
    await query.message.edit_text(text, reply_markup=my_bot_keyboard(True, dep["deployment_id"]))


async def cb_edit_vars(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    # Track which deployment the user is editing variables for
    await database.update_user(user_id, {"current_state": f"var_edit_{dep['deployment_id']}"})
    await query.message.edit_text(
        "<blockquote><b>🔧 ᴠᴀʀɪᴀʙʟᴇ ᴍᴀɴᴀɢᴇʀ</b></blockquote>\n\n"
        "<b>ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ʙᴏᴛ's ᴇɴᴠɪʀᴏɴᴍᴇɴᴛ ᴠᴀʀɪᴀʙʟᴇs.</b>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_restart_bot(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>🔄 Restarting your bot...</b>",
        reply_markup=confirmation_keyboard(f"restart_{dep['deployment_id']}"),
    )
    await query.answer()


async def cb_stop_bot(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>⏹ Are you sure you want to stop your bot?</b>",
        reply_markup=confirmation_keyboard(f"stop_{dep['deployment_id']}"),
    )
    await query.answer()


async def cb_delete_bot(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>🗑 Are you sure you want to permanently delete your bot?</b>\n\n"
        "<b>⚠ This action cannot be undone!</b>",
        reply_markup=confirmation_keyboard(f"delete_{dep['deployment_id']}"),
    )
    await query.answer()


async def cb_view_url(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    url = dep.get("url", "N/A")
    await query.answer(f"URL: {url}", show_alert=True)


async def cb_check_join(client: Client, query: CallbackQuery):
    channels = await database.get_all_channels()
    if not channels:
        await query.message.edit_text(START_CAPTION.format(user=query.from_user.first_name or "user"), reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS))
        await query.answer("✅ All good!")
        return
    not_joined = []
    for ch in channels:
        try:
            member = await client.get_chat_member(ch["channel_id"], query.from_user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    if not_joined:
        await query.message.edit_text("⚠ Join Required Channels", reply_markup=force_sub_keyboard(not_joined))
        await query.answer("❌ Please join all channels")
    else:
        await query.message.edit_text(START_CAPTION.format(user=query.from_user.first_name or "user"), reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS))
        await query.answer("✅ Welcome! You can now use the bot.")


async def cb_refresh(client: Client, query: CallbackQuery):
    await cb_check_join(client, query)


async def cb_admin_panel(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<blockquote><b>⚙ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ</b></blockquote>\n\n"
        "<b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ.</b>",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_add_token(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>🚂 Add Railway Token</b>\n\n"
        "<b>Send me a Railway API token.</b>\n\n"
        "<b>Example:</b>\n"
        "<code>976a3bd2-793d-4359-bcc9-076238e2599e</code>\n\n"
        "<b>Usage:</b> /addtoken YOUR_TOKEN",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_remove_token(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>🗑 Remove Railway Token</b>\n\n"
        "<b>Usage:</b> /removetoken TOKEN",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_token_stats(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    stats = await token_manager.get_token_stats()
    text = (
        f"<blockquote><b>🚂 ʀᴀɪʟᴡᴀʏ ᴛᴏᴋᴇɴ sᴛᴀᴛs</b></blockquote>\n\n"
        f"<b>📊 Total Tokens:</b> {stats['total']}\n"
        f"<b>✅ Active:</b> {stats['active']}\n"
        f"<b>🆓 Available:</b> {stats['available']}\n"
        f"<b>📦 Total Deployments:</b> {stats['total_deployments']}\n\n"
    )
    for t in stats.get("tokens", []):
        if not t.get("is_active"):
            continue
        text += (
            f"<b>Token:</b> <code>{t['token'][:12]}...</code>\n"
            f"  <b>Active:</b> {'✅' if t.get('is_active') else '❌'}\n"
            f"  <b>Deployments:</b> {t.get('current_deployments', 0)}/{t.get('max_deployments', 1)}\n"
            f"  <b>Credits:</b> ${t.get('credits', 0):.2f}\n\n"
        )
    await query.message.edit_text(text, reply_markup=token_stats_keyboard())
    await query.answer()


async def cb_admin_queue_stats(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<blockquote><b>📊 ǫᴜᴇᴜᴇ sᴛᴀᴛs</b></blockquote>\n\n"
        "<b>⚡ Queue system active and running</b>\n"
        "<b>📌 No pending deployments in queue.</b>",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_user_stats(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    total = await database.count_users()
    active = await database.count_active_deployments()
    total_deps = await database.count_total_deployments()
    await query.message.edit_text(
        f"<blockquote><b>👥 ᴜsᴇʀ sᴛᴀᴛs</b></blockquote>\n\n"
        f"<b>👤 Total Users:</b> {total}\n"
        f"<b>🤖 Active Deployments:</b> {active}\n"
        f"<b>📦 Total Deployments:</b> {total_deps}",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_broadcast(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>📢 Broadcast Message</b>\n\n"
        "<b>Reply to a message with /broadcast to send it to all users.</b>",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_ban(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>🔨 Ban User</b>\n\n<b>Usage:</b> /ban USER_ID REASON",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_unban(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>🔓 Unban User</b>\n\n<b>Usage:</b> /unban USER_ID",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_payments(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<blockquote><b>💳 ᴘᴀʏᴍᴇɴᴛ ʀᴇǫᴜᴇsᴛs</b></blockquote>\n\n"
        "<b>No pending payment requests.</b>",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_add_plan(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>➕ Add Hosting Plan</b>\n\n"
        "<b>Usage:</b> Send plan details via admin command.",
        reply_markup=admin_keyboard(),
    )
    await query.answer()


async def cb_admin_force_redeploy(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.message.edit_text(
        "<b>⚡ Force Redeploy</b>\n\n"
        "<b>This will restart all active deployments.</b>",
        reply_markup=confirmation_keyboard("force_redeploy"),
    )
    await query.answer()


async def cb_admin_system_logs(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    logs = await database.get_recent_logs(20)
    text = "<blockquote><b>📋 sʏsᴛᴇᴍ ʟᴏɢs</b></blockquote>\n\n"
    for log in logs:
        ts = log.get("timestamp", "")
        text += f"<b>[{ts}]</b> {log.get('type', 'log')}\n"
    await query.message.edit_text(text or "<b>No logs</b>", reply_markup=admin_keyboard())
    await query.answer()


async def cb_admin_db_status(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    try:
        stats = await database.get_db_stats()
        text = (
            f"<blockquote><b>💾 ᴅᴀᴛᴀʙᴀsᴇ sᴛᴀᴛᴜs</b></blockquote>\n\n"
            f"<b>📊 Collections:</b> {stats.get('collections', 0)}\n"
            f"<b>📦 Objects:</b> {stats.get('objects', 0)}\n"
            f"<b>💾 Data Size:</b> {stats.get('dataSize', 0) / 1024:.1f} KB\n"
            f"<b>📏 Storage Size:</b> {stats.get('storageSize', 0) / 1024:.1f} KB\n"
            f"<b>📊 Indexes:</b> {stats.get('indexes', 0)}\n"
            f"<b>📐 Index Size:</b> {stats.get('indexSize', 0) / 1024:.1f} KB\n"
            f"<b>✅ Status:</b> {'🟢 Connected' if stats else '🔴 Disconnected'}"
        )
    except Exception as e:
        text = f"<b>❌ Database error: {str(e)}</b>"
    await query.message.edit_text(text, reply_markup=admin_keyboard())
    await query.answer()


async def cb_admin_maintenance(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    current = settings.MAINTENANCE_MODE
    await query.message.edit_text(
        f"<blockquote><b>🔧 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ</b></blockquote>\n\n"
        f"<b>Current status:</b> {'🟢 Active' if current else '🔴 Inactive'}\n\n"
        f"<b>Toggle maintenance mode:</b>",
        reply_markup=confirmation_keyboard("toggle_maintenance"),
    )
    await query.answer()


async def cb_admin_api_health(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.answer("🩺 Running health checks on ALL tokens...", show_alert=True)
    await query.message.edit_text("<b>🔍 Checking all services and tokens...</b>")

    results = []
    dead_tokens = []

    # 1) MongoDB health
    try:
        await database.db.command("ping")
        results.append(("✅", "MongoDB", "Connected"))
    except Exception as e:
        results.append(("❌", "MongoDB", str(e)))

    # 2) Per-token Railway API health
    tokens = await database.get_all_tokens()
    if tokens:
        token_results = []
        for tdoc in tokens:
            token_preview = f"{tdoc['token'][:12]}..."
            if not tdoc.get("is_active"):
                token_results.append(("❌", token_preview, "DISABLED"))
                continue
            restricted = tdoc.get("is_restricted", False)
            r_client = RailwayClient(tdoc["token"])
            try:
                info = await asyncio.wait_for(r_client.get_account_info(), timeout=15)
                me = info.get("me", {})
                if not me.get("id"):
                    token_results.append(("❌", token_preview, "Invalid token"))
                    dead_tokens.append(tdoc)
                    await r_client.close()
                    continue
                workspaces = me.get("workspaces", [])
                customer = workspaces[0].get("customer", {}) if workspaces else {}
                credits = customer.get("remainingUsageCreditBalance") or customer.get("creditBalance", "N/A")
                if isinstance(credits, (int, float)):
                    credits = f"${credits:.2f}"
                cur_deps = tdoc.get("current_deployments", 0)
                max_deps = tdoc.get("max_deployments", 2)
                status_icon = "🚫" if restricted else "✅"
                label = f"{status_icon} {token_preview}"
                token_results.append((status_icon, label, f"Credits:{credits} Deploy:{cur_deps}/{max_deps}"))
                await r_client.close()
            except asyncio.TimeoutError:
                token_results.append(("⏳", token_preview, "TIMEOUT"))
                dead_tokens.append(tdoc)
                await r_client.close()
            except Exception as e:
                token_results.append(("❌", token_preview, str(e)[:60]))
                dead_tokens.append(tdoc)
                await r_client.close()

        results.append(("🚂", f"Railway Tokens ({len(tokens)})", f"{len([t for t in tokens if t.get('is_active') and not t.get('is_restricted')])} active"))
        for icon, label, status in token_results:
            results.append((icon, f"  {label}", status))

        # Auto-disable dead tokens
        for tdoc in dead_tokens:
            try:
                await database.disable_token(tdoc["token"])
                # Migrate deployments from dead token
                deps = await database.db.deployments.find({"railway_token": tdoc["token"]}).to_list(None)
                for dep in deps:
                    asyncio.create_task(deployment_engine.migrate_deployment(dep["deployment_id"]))
                results.append(("🔄", f"  ↳ {tdoc['token'][:12]}...", f"{len(deps)} deployment(s) auto-migrating"))
            except Exception:
                pass
    else:
        results.append(("⚠", "Railway API", "No tokens configured"))

    # 3) GitHub API health
    try:
        test_ok = await github_client._test_connection()
        results.append(("✅" if test_ok else "❌", "GitHub API", "Reachable" if test_ok else "Unreachable"))
    except Exception as e:
        results.append(("❌", "GitHub API", str(e)))

    # 4) Bot status
    try:
        me = await client.get_me()
        results.append(("✅", "Bot", f"@{me.username} (ID: {me.id})"))
    except Exception as e:
        results.append(("❌", "Bot", str(e)))

    # 5) Deployment engine status
    active_deps = await database.count_active_deployments()
    total_deps = await database.count_total_deployments()
    results.append(("ℹ", "Deployments", f"{active_deps} active / {total_deps} total"))

    text = "<blockquote><b>🩺 API HEALTH CHECK</b></blockquote>\n\n"
    for icon, name, status in results:
        text += f"<b>{icon} {name}:</b> <code>{status}</code>\n"
    text += f"\n<b>Last check:</b> <code>{__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</code>"

    if dead_tokens:
        text += "\n\n<b>⚠ Some tokens were dead — deployments auto-migrating to healthy tokens.</b>"

    await query.message.edit_text(text, reply_markup=admin_keyboard())


async def cb_admin_restrict_token(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    tokens = await database.get_all_tokens()
    if not tokens:
        await query.message.edit_text("<b>No tokens configured.</b>", reply_markup=admin_keyboard())
        await query.answer()
        return
    from bot.keyboards.main import btn
    from pyrogram.types import InlineKeyboardMarkup
    buttons = []
    for t in tokens:
        prefix = t["token"][:12]
        restricted = t.get("is_restricted", False)
        label = f"{'🚫' if restricted else '✅'} {prefix}..."
        buttons.append([btn(label, f"toggle_restrict_{t['token']}")])
    buttons.append([btn("◀ Back", "admin_panel")])
    await query.message.edit_text(
        "<blockquote><b>🚫 ᴛᴏᴋᴇɴ ʀᴇsᴛʀɪᴄᴛɪᴏɴ</b></blockquote>\n\n"
        "<b>Click a token to toggle restriction.</b>\n"
        "<b>🚫 = Restricted (not used for new deployments)</b>\n"
        "<b>✅ = Active (available for deployment)</b>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await query.answer()


async def cb_admin_cleanup_workshops(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.answer("🧹 Running workshop cleanup...", show_alert=True)
    await query.message.edit_text("<b>🧹 Cleaning up non-running workshops...</b>")

    cleaned = 0
    errors = 0
    tokens = await database.get_all_tokens()
    for tdoc in tokens:
        if not tdoc.get("is_active"):
            continue
        if tdoc.get("is_restricted"):
            continue
        r_client = RailwayClient(tdoc["token"])
        try:
            projects = await r_client.list_all_projects()
            for proj in projects:
                pid = proj["id"]
                services = await r_client.get_project_services_status(pid)
                all_dead = True
                for svc in services:
                    dep_node = svc.get("deployments", {}).get("edges", [{}])[0].get("node", {})
                    status = (dep_node.get("status") or "").upper()
                    if status in ("SUCCESS", "RUNNING", "BUILDING", "QUEUED", "DEPLOYING"):
                        all_dead = False
                        break
                if all_dead and services:
                    # Check if this is one of our deployments
                    db_dep = await database.db.deployments.find_one({"project_id": pid})
                    if not db_dep:
                        # Orphan project - safe to delete
                        try:
                            await r_client.delete_project(pid)
                            cleaned += 1
                        except Exception:
                            errors += 1
        except Exception:
            errors += 1
        finally:
            await r_client.close()

    text = (
        f"<blockquote><b>🧹 ᴄʟᴇᴀɴᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇ</b></blockquote>\n\n"
        f"<b>🗑 Projects deleted:</b> {cleaned}\n"
        f"<b>❌ Errors:</b> {errors}\n"
        f"<b>🔍 Tokens scanned:</b> {len(tokens)}"
    )
    await query.message.edit_text(text, reply_markup=admin_keyboard())


async def cb_admin_validate_tokens(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    await query.answer("🔍 Validating all tokens...", show_alert=True)
    await query.message.edit_text("<b>🔍 Validating tokens and removing invalid ones...</b>")
    tokens = await database.get_all_tokens()
    removed = 0
    kept = 0
    for tdoc in tokens:
        if not tdoc.get("is_active") and not tdoc.get("is_restricted"):
            await database.delete_token(tdoc["token"])
            removed += 1
            continue
        r_client = RailwayClient(tdoc["token"])
        try:
            info = await asyncio.wait_for(r_client.get_account_info(), timeout=15)
            if not info.get("me", {}).get("id"):
                await database.delete_token(tdoc["token"])
                removed += 1
            else:
                kept += 1
            await r_client.close()
        except Exception:
            await r_client.close()
            await database.delete_token(tdoc["token"])
            removed += 1
    text = (
        f"<blockquote><b>🔍 ᴛᴏᴋᴇɴ ᴠᴀʟɪᴅᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ</b></blockquote>\n\n"
        f"<b>🗑 Removed invalid tokens:</b> {removed}\n"
        f"<b>✅ Kept valid tokens:</b> {kept}\n"
        f"<b>📊 Total before:</b> {len(tokens)}"
    )
    await query.message.edit_text(text, reply_markup=admin_keyboard())


async def cb_toggle_restrict(client: Client, query: CallbackQuery):
    if query.from_user.id not in settings.OWNER_IDS:
        await query.answer("Unauthorized")
        return
    token = query.data[16:]
    tdoc = await database.get_railway_token(token)
    if not tdoc:
        await query.answer("Token not found", show_alert=True)
        return
    if tdoc.get("is_restricted"):
        await database.unrestrict_token(token)
        await query.answer("✅ Token unrestricted - now available for deployments", show_alert=True)
    else:
        await database.restrict_token(token)
        # Delete all workshops/deployments using this token
        deps = await database.db.deployments.find({"railway_token": token}).to_list(None)
        deleted_count = 0
        r_client = RailwayClient(token)
        for dep in deps:
            try:
                await r_client.delete_project(dep["project_id"])
            except Exception:
                pass
            await database.delete_deployment(dep["deployment_id"])
            await token_manager.release_token(token)
            deleted_count += 1
        await r_client.close()
        await query.answer(f"🚫 Token restricted - {deleted_count} workshop(s) deleted", show_alert=True)
    await cb_admin_restrict_token(client, query)


async def cb_var_add(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>➕ Add Variable</b>\n\n"
        "<b>Send variable in format:</b>\n"
        "<code>KEY=VALUE</code>\n\n"
        "<b>Example:</b>\n"
        "<code>BOT_TOKEN=123456:ABC</code>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_edit(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>✏ Edit Variable</b>\n\n"
        "<b>Send the updated variable:</b>\n"
        "<code>KEY=NEW_VALUE</code>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_delete(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    vars_list = list(dep.get("variables", {}).keys())
    if not vars_list:
        await query.message.edit_text("<b>No variables to delete</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
        await query.answer()
        return
    text = "<b>🗑 Delete Variable</b>\n\n<b>To delete a variable, send:</b>\n<code>/delvar KEY_NAME</code>\n\n<b>Current keys:</b>\n" + "\n".join(f"• <code>{k}</code>" for k in vars_list)
    await query.message.edit_text(text, reply_markup=variable_keyboard(dep["deployment_id"]))
    await query.answer()


async def cb_var_view(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    variables = dep.get("variables", {})
    if not variables:
        await query.message.edit_text("<b>No variables configured</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
        await query.answer()
        return
    text = "<blockquote><b>👁 ᴠᴀʀɪᴀʙʟᴇs</b></blockquote>\n\n" + format_variables_for_display(variables)
    await query.message.edit_text(text, reply_markup=variable_keyboard(dep["deployment_id"]))
    await query.answer()


async def cb_var_import(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>📥 Import Variables</b>\n\n"
        "<b>Paste multiple variables:</b>\n"
        "<code>KEY1=VALUE1</code>\n"
        "<code>KEY2=VALUE2</code>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_export(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    variables = dep.get("variables", {})
    if not variables:
        await query.message.edit_text("<b>No variables to export</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
        await query.answer()
        return
    text = "<b>📤 Exported Variables</b>\n\n<code>"
    for k, v in variables.items():
        text += f"{k}={v}\n"
    text += "</code>"
    await query.message.edit_text(text, reply_markup=variable_keyboard(dep["deployment_id"]))
    await query.answer()


async def cb_var_upload_env(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>📄 Upload .env File</b>\n\n"
        "<b>Send me your .env file directly.</b>\n"
        "<b>I will automatically import all variables.</b>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_paste(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>📋 Paste Variables</b>\n\n"
        "<b>Paste your variables in format:</b>\n"
        "<code>KEY1=VALUE1</code>\n"
        "<code>KEY2=VALUE2</code>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_backup(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    variables = dep.get("variables", {})
    if not variables:
        await query.message.edit_text("<b>No variables to backup</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
        await query.answer()
        return
    backup_id = f"backup_{dep['deployment_id']}_{int(time.time())}"
    await database.db.backups.insert_one({
        "backup_id": backup_id,
        "user_id": user_id,
        "variables": variables,
        "created_at": time.time(),
    })
    await query.message.edit_text(
        f"<b>✅ Variables backed up!</b>\n\n<b>Backup ID:</b> <code>{backup_id}</code>",
        reply_markup=variable_keyboard(dep["deployment_id"]),
    )
    await query.answer()


async def cb_var_restore(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    backups = await database.db.backups.find({"user_id": user_id}).sort("created_at", -1).limit(5).to_list(None)
    if not backups:
        await query.message.edit_text("<b>No backups found</b>", reply_markup=variable_keyboard(dep["deployment_id"] if dep else None))
        await query.answer()
        return
    text = "<b>🔄 Restore Backup</b>\n\n"
    for b in backups:
        text += f"<b>ID:</b> <code>{b['backup_id']}</code>\n"
        text += f"<b>Date:</b> {time.ctime(b['created_at'])}\n"
        text += f"<b>Vars:</b> {len(b['variables'])} variables\n\n"
    await query.message.edit_text(text, reply_markup=variable_keyboard(dep["deployment_id"] if dep else None))
    await query.answer()


async def cb_var_encrypt(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    variables = dep.get("variables", {})
    if not variables:
        await query.message.edit_text("<b>No variables to encrypt</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
        await query.answer()
        return
    encrypted = {}
    for k, v in variables.items():
        if k.upper() in ["BOT_TOKEN", "API_HASH", "MONGO_URI", "STRING_SESSION"]:
            from bot.utils.security import encrypt_value
            encrypted[k] = encrypt_value(v)
        else:
            encrypted[k] = v
    await database.update_deployment(dep["deployment_id"], {"variables": encrypted})
    await query.message.edit_text("<b>✅ Sensitive variables encrypted</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
    await query.answer()


async def cb_var_reset(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>⚠ Reset all variables?</b>\n\n<b>This will delete ALL your environment variables.</b>",
        reply_markup=confirmation_keyboard(f"var_reset_{dep['deployment_id']}"),
    )
    await query.answer()


async def cb_support_contact(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<b>📞 Contact Support</b>\n\n"
        "<b>For support, please contact:</b>\n"
        "<b>📧 Email:</b> support@pythonbotcloud.com\n"
        "<b>💬 Telegram:</b> @PythonBotCloudSupport",
        reply_markup=support_keyboard(),
    )
    await query.answer()


async def cb_faq(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<blockquote><b>❓ ғᴀǫ</b></blockquote>\n\n"
        "<b>Q: What bots can I deploy?</b>\n"
        "<b>A: Only Python Telegram bots (Pyrogram, Telethon, Aiogram)</b>\n\n"
        "<b>Q: How many deployments?</b>\n"
        "<b>A: One deployment per user</b>\n\n"
        "<b>Q: Can I use my own domain?</b>\n"
        "<b>A: Yes, on premium plans</b>\n\n"
        "<b>Q: What if my bot crashes?</b>\n"
        "<b>A: Auto-redeploy and migration system handles it</b>",
        reply_markup=support_keyboard(),
    )
    await query.answer()


async def cb_developer(client: Client, query: CallbackQuery):
    await query.message.edit_text(
        "<blockquote><b>👨‍💻 ᴅᴇᴠᴇʟᴏᴘᴇʀ</b></blockquote>\n\n"
        f"<b>Bot Version:</b> {settings.BOT_VERSION}\n"
        "<b>Built with:</b> Pyrogram + MongoDB + Railway API\n"
        "<b>⚡ Enterprise Cloud Platform</b>",
        reply_markup=start_keyboard(query.from_user.id in settings.OWNER_IDS),
    )
    await query.answer()


async def cb_confirm(client: Client, query: CallbackQuery):
    action = query.data[8:]
    user_id = query.from_user.id

    if action.startswith("stop"):
        await query.answer("Stopping bot...")
        dep = await get_deployment_from_callback(query, user_id)
        if dep:
            await deployment_engine.stop_deployment(dep["deployment_id"])
            await query.message.edit_text("<b>✅ Bot stopped successfully</b>", reply_markup=my_bot_keyboard(False, dep["deployment_id"]))
    elif action.startswith("delete"):
        await query.answer("Deleting bot...")
        dep = await get_deployment_from_callback(query, user_id)
        if dep:
            await deployment_engine.delete_deployment(dep["deployment_id"])
            await query.message.edit_text("<b>✅ Bot deleted permanently</b>", reply_markup=my_bot_keyboard(False))
    elif action.startswith("restart"):
        await query.answer("Restarting bot...")
        dep = await get_deployment_from_callback(query, user_id)
        if dep:
            await deployment_engine.restart_deployment(dep["deployment_id"])
            await query.message.edit_text("<b>✅ Bot restarted successfully</b>", reply_markup=my_bot_keyboard(True, dep["deployment_id"]))
    elif action.startswith("var_reset"):
        await query.answer("Resetting variables...")
        dep = await get_deployment_from_callback(query, user_id)
        if dep:
            await database.update_deployment(dep["deployment_id"], {"variables": {}})
            await query.message.edit_text("<b>✅ Variables reset</b>", reply_markup=variable_keyboard(dep["deployment_id"]))
    elif action == "force_redeploy" and user_id in settings.OWNER_IDS:
        await query.answer("Force redeploying...")
        await query.message.edit_text("<b>⚡ Force redeploying all deployments...</b>", reply_markup=admin_keyboard())
    elif action == "toggle_maintenance" and user_id in settings.OWNER_IDS:
        await query.answer()
        settings.MAINTENANCE_MODE = not settings.MAINTENANCE_MODE
        await query.message.edit_text(f"<b>✅ Maintenance mode: {settings.MAINTENANCE_MODE}</b>", reply_markup=admin_keyboard())
    elif action.startswith("deploy_"):
        deploy_id = action[7:]
        from bot.deployment.engine import DEPLOY_CACHE
        if deploy_id not in DEPLOY_CACHE:
            await query.answer()
            await query.message.edit_text("<b>❌ Deployment session expired. Please upload again.</b>", reply_markup=deploy_keyboard())
            return
            
        context = DEPLOY_CACHE.pop(deploy_id)
        dep_vars = context.get("variables", {})
        
        asyncio.create_task(track_background_deployment(client, query.message, user_id, context, dep_vars))
        await query.answer("Deployment initiated in background...")
    elif action == "back_deploy":
        await query.answer()
        await cb_deploy_menu(client, query)


async def cb_cancel(client: Client, query: CallbackQuery):
    await query.answer()
    action = query.data[7:]
    user_id = query.from_user.id
    action_type = action.split("_")[0]
    if action.startswith("deploy_"):
        from bot.deployment.engine import DEPLOY_CACHE
        deploy_id = action[7:]
        DEPLOY_CACHE.pop(deploy_id, None)
        await query.message.edit_text("<b>❌ Deployment cancelled</b>", reply_markup=deploy_keyboard())
    elif action_type in ("stop", "delete", "restart", "var_reset", "force_redeploy"):
        dep = await get_deployment_from_callback(query, user_id)
        await query.message.edit_text("<b>❌ Action cancelled</b>", reply_markup=my_bot_keyboard(bool(dep), dep["deployment_id"] if dep else None))
    elif action == "back_deploy":
        await cb_deploy_menu(client, query)
    else:
        await cb_main_menu(client, query)


async def cb_change_region(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment", show_alert=True)
        return
    await query.message.edit_text(
        "<blockquote><b>🌐 sᴇʟᴇᴄᴛ ʀᴇɢɪᴏɴ</b></blockquote>\n\n"
        "Choose a region for your running bot. Changing region will restart the bot.",
        reply_markup=region_selection_keyboard(dep["deployment_id"], is_active_bot=True)
    )
    await query.answer()


async def cb_select_region(client: Client, query: CallbackQuery):
    deploy_id = query.data.split("_")[1]
    await query.message.edit_text(
        "<blockquote><b>🌐 sᴇʟᴇᴄᴛ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ʀᴇɢɪᴏɴ</b></blockquote>\n\n"
        "Pick a deployment region/server for your bot:",
        reply_markup=region_selection_keyboard(deploy_id, is_active_bot=False)
    )
    await query.answer()


async def cb_set_region(client: Client, query: CallbackQuery):
    parts = query.data.split("_")
    deploy_id = parts[1]
    region_code = parts[2]
    
    from bot.deployment.engine import DEPLOY_CACHE
    if deploy_id in DEPLOY_CACHE:
        DEPLOY_CACHE[deploy_id]["region"] = region_code
        
    await query.answer(f"Region set to: {region_code}", show_alert=True)
    
    context = DEPLOY_CACHE.get(deploy_id, {})
    if context.get("type") == "github":
        repo_slug = f"{context['owner']}/{context['repo']}"
        text = (
            f"<blockquote><b>📦 ʀᴇᴘᴏsɪᴛᴏʀʏ sᴄᴀɴ ʀᴇsᴜʟᴛ</b></blockquote>\n\n"
            f"<b>🐙 Repo:</b> {repo_slug}\n"
            f"<b>🌿 Branch:</b> {context['branch']}\n"
            f"<b>🌍 Region:</b> <code>{region_code}</code>\n\n"
            f"<b>Click below to start deployment. To add Environment Variables, simply send <code>KEY=VALUE</code> in the chat before clicking Deploy.</b>"
        )
    else:
        text = (
            f"<blockquote><b>📦 ᴢɪᴘ sᴄᴀɴ ʀᴇsᴜʟᴛ</b></blockquote>\n\n"
            f"<b>📄 File:</b> {context.get('filename')}\n"
            f"<b>🌍 Region:</b> <code>{region_code}</code>\n\n"
            f"<b>Click below to start deployment. To add Environment Variables, simply send <code>KEY=VALUE</code> in the chat before clicking Deploy.</b>"
        )
        
    await query.message.edit_text(text, reply_markup=confirmation_keyboard(f"deploy_{deploy_id}"))


async def cb_set_region_active(client: Client, query: CallbackQuery):
    region_code = query.data.split("_")[1]
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment", show_alert=True)
        return
        
    await query.message.edit_text(f"<b>🌐 Changing region to {region_code} and restarting...</b>")
    
    r_client = RailwayClient(dep["railway_token"])
    try:
        success = await r_client.update_service_instance_region(dep["service_id"], dep["environment_id"], region_code)
        if success:
            new_dep_id = await r_client.create_deployment(dep["service_id"], dep["environment_id"])
            if new_dep_id:
                await database.update_deployment(dep["deployment_id"], {"railway_deployment_id": new_dep_id})
            await query.message.edit_text(
                f"<b>✅ Region changed to {region_code} successfully! Bot is restarting.</b>",
                reply_markup=my_bot_keyboard(True, dep["deployment_id"])
            )
        else:
            await query.message.edit_text(
                "<b>❌ Failed to update region on Railway.</b>",
                reply_markup=my_bot_keyboard(True, dep["deployment_id"])
            )
    except Exception as e:
        await query.message.edit_text(f"<b>❌ Error: {str(e)}</b>", reply_markup=my_bot_keyboard(True, dep["deployment_id"]))
    finally:
        await r_client.close()
    await query.answer()


async def cb_domain_manager(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    r_client = RailwayClient(dep["railway_token"])
    try:
        domains_data = await r_client.get_service_domains(dep["project_id"], dep["environment_id"], dep["service_id"])
        service_doms = domains_data.get("serviceDomains", [])
        custom_doms = domains_data.get("customDomains", [])
        
        text = "<blockquote><b>🌍 ᴅᴏᴍᴀɪɴ ᴍᴀɴᴀɢᴇʀ</b></blockquote>\n\n"
        if not service_doms and not custom_doms:
            text += "<b>No domains configured for this service.</b>"
        else:
            if service_doms:
                text += "<b>🚂 Railway Domains:</b>\n"
                for d in service_doms:
                    text += f"• <code>https://{d['domain']}</code>\n"
            if custom_doms:
                text += "\n<b>🌍 Custom Domains:</b>\n"
                for d in custom_doms:
                    text += f"• <code>https://{d['domain']}</code>\n"
                    
        await query.message.edit_text(text, reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    except Exception as e:
        await query.message.edit_text(f"<b>❌ Error: {str(e)}</b>", reply_markup=my_bot_keyboard(True, dep["deployment_id"]))
    finally:
        await r_client.close()
    await query.answer()


async def cb_dom_create_railway(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text("<b>🚂 Creating Railway domain...</b>")
    r_client = RailwayClient(dep["railway_token"])
    try:
        res = await r_client.create_service_domain(dep["service_id"], dep["environment_id"])
        if res and res.get("domain"):
            url = f"https://{res['domain']}"
            await database.update_deployment(dep["deployment_id"], {"url": url})
            await query.message.edit_text(
                f"<b>✅ Domain created successfully!</b>\n\n<b>Domain:</b> <code>{url}</code>",
                reply_markup=domain_manager_keyboard(dep["deployment_id"])
            )
        else:
            await query.message.edit_text("<b>❌ Failed to create Railway domain.</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    except Exception as e:
        await query.message.edit_text(f"<b>❌ Error: {str(e)}</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    finally:
        await r_client.close()
    await query.answer()


async def cb_dom_create_custom(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text(
        "<b>➕ Add Custom Domain</b>\n\n"
        "Send your custom domain in the chat using format:\n"
        "<code>DOMAIN=yourdomain.com</code>",
        reply_markup=domain_manager_keyboard(dep["deployment_id"])
    )
    await query.answer()


async def cb_dom_delete_menu(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    r_client = RailwayClient(dep["railway_token"])
    try:
        domains_data = await r_client.get_service_domains(dep["project_id"], dep["environment_id"], dep["service_id"])
        service_doms = domains_data.get("serviceDomains", [])
        custom_doms = domains_data.get("customDomains", [])
        
        all_doms = []
        for d in service_doms:
            all_doms.append({"id": d["id"], "domain": d["domain"]})
        for d in custom_doms:
            all_doms.append({"id": d["id"], "domain": d["domain"]})
            
        if not all_doms:
            await query.message.edit_text("<b>No domains to delete.</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
        else:
            await query.message.edit_text(
                "<b>🗑 Select Domain to Delete:</b>",
                reply_markup=domain_delete_keyboard(all_doms, dep["deployment_id"])
            )
    except Exception as e:
        await query.message.edit_text(f"<b>❌ Error: {str(e)}</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    finally:
        await r_client.close()
    await query.answer()


async def cb_confirm_delete_dom(client: Client, query: CallbackQuery):
    domain_id = query.data.split("_")[3]
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    await query.message.edit_text("<b>🗑 Deleting domain...</b>")
    r_client = RailwayClient(dep["railway_token"])
    try:
        success = await r_client.delete_service_domain(domain_id)
        if success:
            await query.message.edit_text("<b>✅ Domain deleted successfully!</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
        else:
            await query.message.edit_text("<b>❌ Failed to delete domain.</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    except Exception as e:
        await query.message.edit_text(f"<b>❌ Error: {str(e)}</b>", reply_markup=domain_manager_keyboard(dep["deployment_id"]))
    finally:
        await r_client.close()
    await query.answer()


async def track_background_deployment(client: Client, message, user_id: int, context: dict, dep_vars: dict):
    logger = logging.getLogger(__name__)
    from bot.services.log_service import owner_log
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    building_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Main Menu", callback_data="main_menu")]])
    
    try:
        await message.edit_text("<b>🚀 Starting project creation and setup...</b>", reply_markup=building_kb)
        
        if context["type"] == "github":
            scan_result = context.get("scan_result")
            result = await deployment_engine.deploy_from_github(user_id, context["url"], dep_vars, scan_result=scan_result)
        else:
            result = await deployment_engine.deploy_from_zip(user_id, context["zip_data"], dep_vars)
            
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            await owner_log.send_user_notification(
                user_id,
                f"❌ <b>Deployment Failed:</b>\n<code>{error_msg}</code>"
            )
            await message.edit_text(
                f"<blockquote><b>❌ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ғᴀɪʟᴇᴅ</b></blockquote>\n\n"
                f"<b>Error:</b> {error_msg}",
                reply_markup=deploy_keyboard(),
            )
            return
            
        deployment_id = result["deployment_id"]
        dep_url = result["url"]
        framework = result["framework"]
        
        dep = await database.get_deployment(deployment_id)
        if not dep:
            await message.edit_text("<b>❌ Deployment record not found in database.</b>", reply_markup=deploy_keyboard())
            return
            
        railway_deployment_id = dep["railway_deployment_id"]
        railway_token = dep["railway_token"]
        
        await message.edit_text("<b>🟢 Project created! Checking build progress...</b>", reply_markup=building_kb)
        
        last_text = ""
        for attempt in range(120): # Polling for 10 minutes max
            await asyncio.sleep(5)
            r_client = RailwayClient(railway_token)
            try:
                res = await r_client.get_deployment(railway_deployment_id)
                if not res or not res.get("deployment"):
                    continue
                    
                status = res["deployment"].get("status", "unknown").upper()
                
                # Fetch recent build logs
                logs = await r_client.get_build_logs(railway_deployment_id, limit=15)
                log_lines = "\n".join(f"[{log.get('timestamp', '')}] {log.get('message', '')}" for log in logs)
                if not log_lines.strip():
                    log_lines = "Waiting for builder to output logs..."
                
                if len(log_lines) > 3000:
                    log_lines = log_lines[-3000:]
                    
                text = (
                    f"<blockquote><b>🛠 ʙᴜɪʟᴅɪɴɢ ʙᴏᴛ...</b></blockquote>\n\n"
                    f"<b>Status:</b> <code>{status}</code>\n"
                    f"<b>Framework:</b> {framework}\n\n"
                    f"<b>Recent Build Logs:</b>\n"
                    f"<pre>{log_lines}</pre>\n\n"
                    f"<i>Refreshing dynamically...</i>"
                )
                
                if text != last_text:
                    try:
                        current_msg = await client.get_messages(message.chat.id, message.id)
                        if current_msg and current_msg.text and ("ʙᴜɪʟᴅɪɴɢ ʙᴏᴛ" in current_msg.text or "Starting project" in current_msg.text or "Project created" in current_msg.text):
                            await message.edit_text(text, reply_markup=building_kb)
                            last_text = text
                    except Exception:
                        pass
                
                if status in ("SUCCESS", "RUNNING", "CRASHED", "FAILED"):
                    if status in ("SUCCESS", "RUNNING"):
                        await database.update_deployment(deployment_id, {"status": "running", "url": dep_url})
                        await database.update_user(user_id, {"active_management_id": deployment_id})
                        await owner_log.send_user_notification(
                            user_id,
                            f"🎉 <b>Bot Deployment Successful!</b>\n\n"
                            f"⚙ <b>Framework:</b> {framework}\n"
                            f"🌍 <b>URL:</b> {dep_url}\n"
                            f"🆔 <b>Deployment ID:</b> <code>{deployment_id}</code>"
                        )
                        try:
                            current_msg = await client.get_messages(message.chat.id, message.id)
                            if current_msg and current_msg.text and ("ʙᴜɪʟᴅɪɴɢ ʙᴏᴛ" in current_msg.text or "Starting project" in current_msg.text or "Project created" in current_msg.text):
                                await message.edit_text(
                                    f"<blockquote><b>✅ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ sᴜᴄᴄᴇssғᴜʟ</b></blockquote>\n\n"
                                    f"<b>⚙ Framework:</b> {framework}\n"
                                    f"<b>🌍 URL:</b> <code>{dep_url}</code>\n\n"
                                    f"<b>Use the buttons below to manage your bot.</b>",
                                    reply_markup=my_bot_keyboard(True, deployment_id),
                                )
                        except Exception:
                            pass
                    else:
                        await database.update_deployment(deployment_id, {"status": "failed"})
                        await owner_log.send_user_notification(
                            user_id,
                            f"❌ <b>Bot Deployment Failed!</b>\n\n"
                            f"🆔 <b>Deployment ID:</b> <code>{deployment_id}</code>\n"
                            f"⚠️ <b>Status:</b> <code>{status}</code>\n"
                            f"Please check your code or build logs."
                        )
                        try:
                            current_msg = await client.get_messages(message.chat.id, message.id)
                            if current_msg and current_msg.text and ("ʙᴜɪʟᴅɪɴɢ ʙᴏᴛ" in current_msg.text or "Starting project" in current_msg.text or "Project created" in current_msg.text):
                                await message.edit_text(
                                    f"<blockquote><b>❌ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ғᴀɪʟᴇᴅ</b></blockquote>\n\n"
                                    f"<b>Status:</b> <code>{status}</code>\n\n"
                                    f"Please check your code syntax or logs.",
                                    reply_markup=deploy_keyboard(),
                                )
                        except Exception:
                            pass
                    break
            except Exception as e:
                logger.error(f"Error in tracking build: {e}")
            finally:
                await r_client.close()
        else:
            try:
                current_msg = await client.get_messages(message.chat.id, message.id)
                if current_msg and current_msg.text and ("ʙᴜɪʟᴅɪɴɢ ʙᴏᴛ" in current_msg.text or "Starting project" in current_msg.text or "Project created" in current_msg.text):
                    await message.edit_text("<b>❌ Build tracking timed out (took >10 mins). Check status later.</b>", reply_markup=my_bot_keyboard(True, deployment_id))
            except Exception:
                pass
            
    except Exception as ex:
        logger.exception("Background deployment error")
        await owner_log.send_user_notification(
            user_id,
            f"❌ <b>Unexpected Deployment Error:</b>\n<code>{str(ex)}</code>"
        )
        try:
            await message.edit_text(f"<b>❌ Unexpected deployment error:</b> {str(ex)}")
        except Exception:
            pass



async def cb_download_logs(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment found", show_alert=True)
        return
        
    await query.answer("📥 Fetching and formatting logs... please wait.")
    
    # Get build and runtime logs
    build_logs = await deployment_engine.get_build_logs(dep["deployment_id"], limit=100)
    runtime_logs = await deployment_engine.get_runtime_logs(dep["deployment_id"], limit=100)
    
    log_content = (
        "============================================================\n"
        f"                 BUILD LOGS (BOT: {dep['deployment_id']})\n"
        "============================================================\n"
        f"{build_logs}\n\n"
        "============================================================\n"
        f"                 APPLICATION RUNTIME LOGS\n"
        "============================================================\n"
        f"{runtime_logs}\n"
    )
    
    from io import BytesIO
    log_file = BytesIO(log_content.encode("utf-8"))
    log_file.name = f"logs_{dep['deployment_id'][:8]}.txt"
    
    try:
        await client.send_document(
            chat_id=query.message.chat.id,
            document=log_file,
            caption=f"📋 <b>Here are the logs for your bot:</b>\n"
                    f"▫ <b>ID:</b> <code>{dep['deployment_id'][:8]}</code>\n"
                    f"▫ <b>Status:</b> <code>{dep.get('status')}</code>",
        )
    except Exception as err:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send logs document: {err}")
        await query.message.reply_text(f"<b>❌ Failed to send logs document: {str(err)}</b>")


async def track_background_redeploy(client: Client, message, user_id: int, deployment_id: str, railway_deployment_id: str):
    logger = logging.getLogger(__name__)
    try:
        dep = await database.get_deployment(deployment_id)
        if not dep:
            await message.edit_text("<b>❌ Deployment record not found in database.</b>")
            return
            
        railway_token = dep["railway_token"]
        framework = dep.get("framework", "Bot")
        dep_url = dep.get("url", "")
        
        await message.edit_text("<b>🟢 Redeployment triggered! Checking build progress...</b>")
        
        last_text = ""
        for attempt in range(120): # Polling for 10 minutes max
            await asyncio.sleep(5)
            r_client = RailwayClient(railway_token)
            try:
                res = await r_client.get_deployment(railway_deployment_id)
                if not res or not res.get("deployment"):
                    continue
                    
                status = res["deployment"].get("status", "unknown").upper()
                
                # Fetch recent build logs
                logs = await r_client.get_build_logs(railway_deployment_id, limit=15)
                log_lines = "\n".join(f"[{log.get('timestamp', '')}] {log.get('message', '')}" for log in logs)
                if not log_lines.strip():
                    log_lines = "Waiting for builder to output logs..."
                
                text = (
                    f"<blockquote><b>⚙ Redeploying Bot ({status})</b></blockquote>\n\n"
                    f"<b>📋 Live Build Logs:</b>\n"
                    f"<code>{log_lines[-3000:]}</code>"
                )
                
                if text != last_text:
                    try:
                        await message.edit_text(text)
                        last_text = text
                    except Exception:
                        pass
                
                if status in ("SUCCESS", "RUNNING", "CRASHED", "FAILED"):
                    if status in ("SUCCESS", "RUNNING"):
                        await database.update_deployment(deployment_id, {"status": "running", "railway_deployment_id": railway_deployment_id})
                        await message.edit_text(
                            f"<blockquote><b>✅ ʀᴇᴅᴇᴘʟᴏʏᴍᴇɴᴛ sᴜᴄᴄᴇssғᴜʟ</b></blockquote>\n\n"
                            f"<b>⚙ Framework:</b> {framework}\n"
                            f"<b>🌍 URL:</b> <code>{dep_url}</code>\n\n"
                            f"<b>Your bot is updated with the latest GitHub commits!</b>",
                            reply_markup=my_bot_keyboard(True, deployment_id),
                        )
                    else:
                        await database.update_deployment(deployment_id, {"status": "failed"})
                        await message.edit_text(
                            f"<blockquote><b>❌ ʀᴇᴅᴇᴘʟᴏʏᴍᴇɴᴛ ғᴀɪʟᴇᴅ</b></blockquote>\n\n"
                            f"<b>Status:</b> <code>{status}</code>\n\n"
                            f"Please check your code syntax or logs.",
                            reply_markup=my_bot_keyboard(True, deployment_id),
                        )
                    break
            except Exception as e:
                logger.error(f"Error in tracking build: {e}")
            finally:
                await r_client.close()
        else:
            await message.edit_text("<b>❌ Redeployment tracking timed out (took >10 mins). Check status later.</b>", reply_markup=my_bot_keyboard(True, deployment_id))
            
    except Exception as ex:
        logger.exception("Background redeployment error")
        try:
            await message.edit_text(f"<b>❌ Unexpected redeployment error:</b> {str(ex)}")
        except Exception:
            pass


async def cb_redeploy(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment found", show_alert=True)
        return

    if dep.get("repo_url") == "ZIP Upload":
        await query.answer("❌ This bot was deployed via ZIP. You cannot check repository updates for ZIP uploads. Use restart or upload a new ZIP.", show_alert=True)
        return

    await query.message.edit_text("<b>🔄 Checking for repository updates...</b>")
    await query.answer("Triggering redeploy...")

    new_dep_id = await deployment_engine.redeploy_deployment(dep["deployment_id"])
    if new_dep_id:
        asyncio.create_task(track_background_redeploy(client, query.message, user_id, dep["deployment_id"], new_dep_id))
    else:
        await query.message.edit_text("<b>❌ Failed to trigger redeployment on Railway.</b>", reply_markup=my_bot_keyboard(True, dep["deployment_id"]))


async def cb_redeploy_vars(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment found", show_alert=True)
        return

    await query.answer("🔄 Syncing variables & redeploying...")
    await query.message.edit_text("<b>🔄 Syncing variables to Railway and redeploying...</b>")

    # Sync current variables from DB to Railway
    variables = dep.get("variables", {})
    r_client = RailwayClient(dep["railway_token"])
    try:
        for key, value in variables.items():
            await r_client.set_environment_variable(
                dep["project_id"], dep["environment_id"], key, value,
                service_id=dep["service_id"]
            )
    except Exception as e:
        logger.warning(f"Variable sync failed during redeploy_vars: {e}")
    finally:
        await r_client.close()

    new_dep_id = await deployment_engine.redeploy_deployment(dep["deployment_id"])
    if new_dep_id:
        asyncio.create_task(track_background_redeploy(client, query.message, user_id, dep["deployment_id"], new_dep_id))
    else:
        await query.message.edit_text(
            "<b>❌ Failed to trigger redeployment.</b>\nAll tokens may be restricted.",
            reply_markup=my_bot_keyboard(True, dep["deployment_id"])
        )


async def cb_rename_bot(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    dep = await get_deployment_from_callback(query, user_id)
    if not dep:
        await query.answer("No active deployment")
        return
    
    # Set user state in user doc
    await database.update_user(user_id, {"current_state": f"rename_bot_{dep['deployment_id']}"})
    
    from bot.keyboards.main import btn
    await query.message.edit_text(
        f"<blockquote><b>✏️ ʀᴇɴᴀᴍᴇ ᴅᴀsʜʙᴏᴀʀᴅ</b></blockquote>\n\n"
        f"<b>Current Name:</b> <code>{dep.get('dashboard_name', 'None')}</code>\n\n"
        f"<b>Please send the new name for this bot's dashboard in the chat.</b>\n"
        f"<i>Maximum length: 30 characters.</i>",
        reply_markup=InlineKeyboardMarkup([[btn("◀ Back to Bot", f"my_bot_{dep['deployment_id']}")]])
    )
    await query.answer()
