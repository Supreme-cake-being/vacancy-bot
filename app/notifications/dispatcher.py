import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.config import settings

logger = logging.getLogger(__name__)

# Single Bot instance reused across all notifications
_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.BOT_TOKEN)
    return _bot


async def send_notification(notification) -> None:
    """
    Send a single notification to the user via Telegram.
    Marks it as sent in DB on success.
    """
    from app.db.session import get_db
    from app.db.repositories import NotificationRepo

    vacancy = notification.vacancy
    site = vacancy.site
    user = notification.user

    text = _format_message(site, vacancy)

    success = await _send_with_retry(user.telegram_id, text)

    async with get_db() as db:
        if success:
            await NotificationRepo.mark_sent(db, notification.id)
        else:
            logger.warning(
                f"Failed to send notification {notification.id} "
                f"to user {user.telegram_id}"
            )


def _format_message(site, vacancy) -> str:
    lines = [
        f"New vacancy — <b>{site.name or site.url}</b>",
        "",
        f"{vacancy.title}",
    ]
    if vacancy.url:
        lines.append(f"\n{vacancy.url}")
    return "\n".join(lines)


async def _send_with_retry(
    telegram_id: int, text: str, attempts: int = 3
) -> bool:
    bot = get_bot()
    for attempt in range(attempts):
        try:
            await bot.send_message(chat_id=telegram_id, text=text)
            return True

        except TelegramRetryAfter as e:
            # Telegram tells us exactly how long to wait
            logger.warning(f"Rate limited — waiting {e.retry_after}s")
            import asyncio
            await asyncio.sleep(e.retry_after + 1)

        except TelegramForbiddenError:
            # User blocked the bot — deactivate their subscriptions
            logger.info(f"User {telegram_id} blocked the bot — deactivating")
            await _deactivate_user(telegram_id)
            return False

        except Exception as e:
            logger.error(
                f"Send failed for {telegram_id} "
                f"(attempt {attempt + 1}): {e}"
            )
            import asyncio
            await asyncio.sleep(2 ** attempt)

    return False


async def _deactivate_user(telegram_id: int) -> None:
    """Deactivate all subscriptions for a user who blocked the bot."""
    from app.db.session import get_db
    from sqlalchemy import update
    from app.db.models import Subscription, User

    async with get_db() as db:
        # Find user
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        # Deactivate all their subscriptions
        await db.execute(
            update(Subscription)
            .where(Subscription.user_id == user.id)
            .values(is_active=False)
        )