import logging
from bot.config.settings import settings


class OwnerLogService:
    def __init__(self, client=None):
        self.client = client
        self._queue = []

    async def set_client(self, client):
        self.client = client

    async def send_log(self, log_type: str, data: dict = None, **kwargs):
        if not self.client or not settings.LOG_GROUP_ID:
            return
        if data is None:
            data = kwargs
        try:
            text = self._format_log(log_type, data)
            await self.client.send_message(settings.LOG_GROUP_ID, text)
        except Exception as e:
            logging.error(f"Failed to send log: {e}")

    def _format_log(self, log_type: str, data: dict) -> str:
        headers = {
            "new_deployment": "📥 NEW DEPLOYMENT",
            "deployment_failed": "❌ DEPLOYMENT FAILED",
            "deployment_deleted": "🗑 DEPLOYMENT DELETED",
            "deployment_restarted": "🔄 DEPLOYMENT RESTARTED",
            "token_switched": "🔄 TOKEN SWITCHED",
            "user_banned": "🔨 USER BANNED",
            "payment_completed": "✅ PAYMENT COMPLETED",
            "referral_earned": "🏆 REFERRAL EARNED",
            "broadcast_used": "📢 BROADCAST SENT",
            "token_warning": "⚠ LOW ACTIVE TOKENS",
            "abuse_detected": "⚠ ABUSE DETECTED",
            # Token cleanup events
            "orphan_cleanup": "🧹 ORPHAN PROJECT DELETED",
            "token_restricted": "🚫 TOKEN RESTRICTED/INVALID",
            "token_exhausted": "💸 TOKEN CREDIT EXHAUSTED",
            "dead_projects_cleaned": "🗑 DEAD PROJECTS CLEANED",
            "token_cleanup_summary": "📊 TOKEN CLEANUP SUMMARY",
        }
        header = headers.get(log_type, f"📋 {log_type.upper()}")
        lines = [f"━━━━━━━━━━━━━━━━━━", header, "━━━━━━━━━━━━━━━━━━"]
        for key, value in data.items():
            emoji_map = {
                "user_id": "🆔", "username": "👤", "bot_name": "📦",
                "framework": "⚙", "repo": "🔗", "url": "🌍",
                "token": "🚂", "reason": "📝", "amount": "💰",
                "points": "⭐", "error": "❌", "variables": "🔑",
            }
            emoji = emoji_map.get(key, "▫")
            lines.append(f"{emoji} {key.upper()}: {value}")
        return "\n".join(lines)

    async def send_user_notification(self, user_id: int, text: str):
        if not self.client:
            return
        try:
            await self.client.send_message(user_id, text)
        except Exception as e:
            logging.error(f"Failed to notify user {user_id}: {e}")


owner_log = OwnerLogService()
