import asyncio
import logging
from typing import Optional

from bot.database.db import database
from bot.config.settings import settings
from railway.client import RailwayClient

logger = logging.getLogger(__name__)


class TokenManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._token_index = 0

    async def add_token(self, token: str, added_by: int) -> dict:
        client = RailwayClient(token)
        valid = await client.validate_token()
        await client.close()
        if not valid:
            raise ValueError("Invalid Railway token")
        existing = await database.get_railway_token(token)
        if existing:
            raise ValueError("Token already exists")
        return await database.add_railway_token(token, added_by)

    async def get_available_token(self) -> Optional[dict]:
        async with self._lock:
            token_doc = await database.get_available_token()
            if token_doc:
                return token_doc
            return await self._fallback_token()

    async def _fallback_token(self) -> Optional[dict]:
        all_tokens = await database.get_all_tokens()
        active = [t for t in all_tokens if t.get("is_active") and t.get("current_deployments", 0) < 1]
        if not active:
            return None
        active.sort(key=lambda x: x.get("priority", 0), reverse=True)
        token_doc = active[0]
        await database.update_token_deployments(token_doc["token"])
        return token_doc

    async def release_token(self, token: str):
        await database.release_token(token)

    async def validate_and_rotate(self, token_doc: dict) -> Optional[dict]:
        client = RailwayClient(token_doc["token"])
        try:
            valid = await client.validate_token()
            if not valid:
                await database.disable_token(token_doc["token"])
                logger.warning(f"Token {token_doc['token'][:8]}... is invalid, rotating")
                return await self.get_available_token()
            info = await client.get_account_info()
            return token_doc
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            await database.disable_token(token_doc["token"])
            return await self.get_available_token()
        finally:
            await client.close()

    async def get_token_stats(self) -> dict:
        all_tokens = await database.get_all_tokens()
        active = [t for t in all_tokens if t.get("is_active")]
        total = len(all_tokens)
        active_count = len(active)
        total_deployments = sum(t.get("total_deployments", 0) for t in all_tokens)
        available = len([t for t in active if t.get("current_deployments", 0) < 1])
        return {
            "total": total,
            "active": active_count,
            "available": available,
            "total_deployments": total_deployments,
            "tokens": active,
        }

    async def remove_token(self, token: str):
        await database.delete_token(token)

    async def update_token_priority(self, token: str, priority: int):
        await database.update_token_priority(token, priority)


token_manager = TokenManager()
