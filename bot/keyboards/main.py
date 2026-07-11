from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class Styles:
    PRIMARY = "primary"
    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    SECONDARY = "secondary"


def btn(text: str, callback: str = None, url: str = None, style: str = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text, url=url)
    return InlineKeyboardButton(text, callback_data=callback)


def build_menu(buttons: list, row_width: int = 2) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(buttons), row_width):
        rows.append(buttons[i:i + row_width])
    return InlineKeyboardMarkup(rows)


def start_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [btn("🚀 Deploy Bot", "deploy_menu"), btn("🤖 My Bot", "my_bot")],
        [btn("💎 Hosting Plans", "plans"), btn("👤 Profile", "profile")],
        [btn("📊 Analytics", "analytics"), btn("🏆 Referrals", "referral")],
        [btn("📚 Help", "help"), btn("📢 Updates", "updates")],
    ]
    if is_admin:
        buttons.append([btn("⚙ Admin Panel", "admin_panel")])
    return InlineKeyboardMarkup(buttons)


def deploy_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [btn("🐙 Deploy via GitHub", "deploy_github")],
        [btn("◀ Back", "main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def my_bot_keyboard(has_deployment: bool = False, deployment_id: str = None) -> InlineKeyboardMarkup:
    if not has_deployment:
        buttons = [
            [btn("🚀 Create Deployment", "deploy_menu")],
            [btn("◀ Back", "main_menu")],
        ]
        return InlineKeyboardMarkup(buttons)
    suffix = f"_{deployment_id}" if deployment_id else ""
    buttons = [
        [btn("🛠 Build Logs", f"live_terminal{suffix}"), btn("🚀 Deploy Logs", f"runtime_logs{suffix}")],
        [btn("📊 Runtime Stats", f"runtime_stats{suffix}"), btn("🔧 Setup Variables", f"edit_vars{suffix}")],
        [btn("🌐 Change Region", f"change_region{suffix}"), btn("🌍 Domain Manager", f"domain_manager{suffix}")],
        [btn("🔄 Restart Bot", f"restart_bot{suffix}"), btn("⏹ Stop Bot", f"stop_bot{suffix}")],
        [btn("🗑 Delete Bot", f"delete_bot{suffix}"), btn("🌍 View URL", f"view_url{suffix}")],
        [btn("📥 Download Logs", f"download_logs{suffix}"), btn("🔄 Check Repo Update", f"redeploy{suffix}")],
        [btn("✏ Rename Dashboard", f"rename_bot{suffix}")],
        [btn("◀ Back to Bots List", "my_bot")],
    ]
    return InlineKeyboardMarkup(buttons)


def variable_keyboard(deployment_id: str = None) -> InlineKeyboardMarkup:
    suffix = f"_{deployment_id}" if deployment_id else ""
    buttons = [
        [btn("➕ Add Variable", f"var_add{suffix}"), btn("✏ Edit Variable", f"var_edit{suffix}")],
        [btn("🗑 Delete Variable", f"var_delete{suffix}"), btn("👁 View Variables", f"var_view{suffix}")],
        [btn("📥 Import Variables", f"var_import{suffix}"), btn("📤 Export Variables", f"var_export{suffix}")],
        [btn("📄 Upload ENV File", f"var_upload_env{suffix}"), btn("📋 Paste Variables", f"var_paste{suffix}")],
        [btn("💾 Backup Variables", f"var_backup{suffix}"), btn("🔄 Restore Backup", f"var_restore{suffix}")],
        [btn("🔒 Encrypt Variables", f"var_encrypt{suffix}"), btn("🔄 Reset Variables", f"var_reset{suffix}")],
        [btn("◀ Back", f"my_bot{suffix}")],
    ]
    return InlineKeyboardMarkup(buttons)


def admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [btn("🚂 Add Railway Token", "admin_add_token"), btn("🗑 Remove Token", "admin_remove_token")],
        [btn("🎫 View Tokens & Stats", "admin_token_stats"), btn("🚫 Restrict Token", "admin_restrict_token")],
        [btn("👥 User Stats", "admin_user_stats"), btn("📢 Broadcast", "admin_broadcast")],
        [btn("🔨 Ban User", "admin_ban"), btn("🔓 Unban User", "admin_unban")],
        [btn("💳 Payment Requests", "admin_payments"), btn("➕ Add Plan", "admin_add_plan")],
        [btn("⚡ Force Redeploy", "admin_force_redeploy"), btn("📋 System Logs", "admin_system_logs")],
        [btn("💾 Database Status", "admin_db_status"), btn("🔧 Maintenance", "admin_maintenance")],
        [btn("🩺 API Health Check", "admin_api_health"), btn("🧹 Cleanup Workshops", "admin_cleanup_workshops")],
        [btn("🔍 Validate Tokens", "admin_validate_tokens")],
        [btn("◀ Back", "main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def force_sub_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([btn(f"📢 Join {ch.get('name', 'Channel')}", url=ch.get("invite_link", ""))])
    buttons.append([btn("✅ Check Join", "check_join")])
    buttons.append([btn("🔄 Refresh", "refresh"), btn("📞 Contact Support", "support")])
    return InlineKeyboardMarkup(buttons)


def token_stats_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [btn("🔄 Refresh", "admin_token_stats")],
        [btn("◀ Back", "admin_panel")],
    ]
    return InlineKeyboardMarkup(buttons)


def confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    if action.startswith("deploy_"):
        confirm_btn = btn("🟢 🚀 Deploy", f"confirm_{action}")
    elif action in ("delete", "var_reset"):
        confirm_btn = btn("🔴 🗑 Delete", f"confirm_{action}")
    elif action == "stop":
        confirm_btn = btn("🟡 ⏹ Stop", f"confirm_{action}")
    elif action == "restart":
        confirm_btn = btn("🟡 🔄 Restart", f"confirm_{action}")
    else:
        confirm_btn = btn("🟢 ✅ Confirm", f"confirm_{action}")

    buttons = [
        [confirm_btn, btn("🔴 ❌ Cancel", f"cancel_{action}")],
    ]
    if action.startswith("deploy_"):
        deploy_id = action[7:]
        buttons.append([
            btn("🌐 Select Region", f"selectregion_{deploy_id}"),
            btn("⚙ Add Variables", f"addvars_{action}")
        ])
    return InlineKeyboardMarkup(buttons)


def region_selection_keyboard(deploy_id: str, is_active_bot: bool = False) -> InlineKeyboardMarkup:
    regions = [
        ("🇺🇸 US West", "us-west1"),
        ("🇺🇸 US East", "us-east-1"),
        ("🇸🇬 Singapore", "asia-southeast1"),
        ("🇳🇱 Netherlands", "europe-west4")
    ]
    buttons = []
    for label, code in regions:
        cb = f"setregion_{deploy_id}_{code}" if not is_active_bot else f"setregionactive_{code}"
        buttons.append([btn(label, cb)])
    back_cb = f"cancel_deploy_{deploy_id}" if not is_active_bot else "my_bot"
    buttons.append([btn("◀ Back", back_cb)])
    return InlineKeyboardMarkup(buttons)


def domain_manager_keyboard(deployment_id: str = None) -> InlineKeyboardMarkup:
    suffix = f"_{deployment_id}" if deployment_id else ""
    buttons = [
        [btn("➕ Add Railway Domain", f"dom_create_railway{suffix}"), btn("➕ Add Custom Domain", f"dom_create_custom{suffix}")],
        [btn("🗑 Delete Domain", f"dom_delete_menu{suffix}"), btn("🔄 Refresh Domains", f"domain_manager{suffix}")],
        [btn("◀ Back", f"my_bot{suffix}")]
    ]
    return InlineKeyboardMarkup(buttons)


def domain_delete_keyboard(domains: list, deployment_id: str = None) -> InlineKeyboardMarkup:
    suffix = f"_{deployment_id}" if deployment_id else ""
    buttons = []
    for dom in domains:
        buttons.append([btn(f"🗑 {dom['domain']}", f"confirm_delete_dom_{dom['id']}{suffix}")])
    buttons.append([btn("◀ Back", f"domain_manager{suffix}")])
    return InlineKeyboardMarkup(buttons)


def pagination_keyboard(base_callback: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if page > 0:
        row.append(btn("◀", f"{base_callback}:{page - 1}"))
    row.append(btn(f"{page + 1}/{total_pages}", f"{base_callback}:{page}"))
    if page < total_pages - 1:
        row.append(btn("▶", f"{base_callback}:{page + 1}"))
    buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def support_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [btn("📞 Contact Support", "support_contact"), btn("❓ FAQ", "faq")],
        [btn("📢 Updates", "updates"), btn("👨‍💻 Developer", "developer")],
        [btn("◀ Back", "main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)
