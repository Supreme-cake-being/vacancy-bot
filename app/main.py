import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.bot.handlers import start, sites
from app.bot.middlewares import DbSessionMiddleware, LoggingMiddleware
from app.config import settings
from app.db.session import close_db

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Redis for keeping FSM states
    redis = Redis.from_url(settings.REDIS_URL)
    storage = RedisStorage(redis=redis)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middleware — order is important
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(sites.router)

    logger.info("Bot is starting...")

    try:
        # Видаляємо вебхук якщо був встановлений
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        await redis.aclose()
        logger.info("Bot has been stopped.")


if __name__ == "__main__":
    asyncio.run(main())