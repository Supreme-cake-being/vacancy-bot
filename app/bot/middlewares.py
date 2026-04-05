import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.db.session import AsyncSessionFactory

logger = logging.getLogger(__name__)

class DbSessionMiddleware(BaseMiddleware):
    """Passes DB session to each handler through data['db']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionFactory() as session:
            data["db"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

class LoggingMiddleware(BaseMiddleware):
    """Logs all incoming messages."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and event.message:
            user = event.message.from_user
            text = event.message.text or ""
            logger.info(
                f"Message from @{user.username} ({user.id}): {text[:50]}"
            )
        return await handler(event, data)