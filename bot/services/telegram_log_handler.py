import logging
import asyncio
from bot.config.settings import settings


class TelegramLogHandler(logging.Handler):
    def __init__(self, client=None):
        super().__init__(level=logging.WARNING)
        self.client = client
        self._queue = asyncio.Queue()
        self._task = None

    def set_client(self, client):
        self.client = client
        if self._task is None:
            self._task = asyncio.create_task(self._drain())

    async def _drain(self):
        while True:
            try:
                record = await self._queue.get()
                await self._emit(record)
            except Exception:
                pass

    def emit(self, record):
        try:
            self._queue.put_nowait(record)
        except Exception:
            pass

    async def _emit(self, record):
        if not self.client or not settings.LOG_GROUP_ID:
            return
        try:
            msg = self.format(record)
            if len(msg) > 3500:
                msg = msg[:3500] + "..."
            await self.client.send_message(
                settings.LOG_GROUP_ID,
                f"<b>⚠ {record.levelname}</b>\n<code>{msg}</code>",
                disable_web_page_preview=True,
            )
        except Exception:
            pass


telegram_log_handler = TelegramLogHandler()
