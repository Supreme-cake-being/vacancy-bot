import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def setup_scheduler() -> None:
    """Register all scheduled jobs."""
    scheduler.add_job(
        enqueue_due_sites,
        trigger=IntervalTrigger(minutes=settings.CHECK_INTERVAL_MINUTES),
        id="enqueue_due_sites",
        replace_existing=True,
        max_instances=1,        # prevent overlap if previous run is slow
    )

    scheduler.add_job(
        dispatch_pending_notifications,
        trigger=IntervalTrigger(minutes=1),
        id="dispatch_notifications",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started — checking sites every "
        f"{settings.CHECK_INTERVAL_MINUTES} minutes"
    )


async def enqueue_due_sites() -> None:
    """
    Load all sites due for a check and push them to Celery queue.
    Called every CHECK_INTERVAL_MINUTES by APScheduler.
    """
    from app.db.session import get_db
    from app.db.repositories import SiteRepo
    from app.scheduler.tasks import process_site

    async with get_db() as db:
        sites = await SiteRepo.get_due_for_check(db)

    if not sites:
        logger.debug("No sites due for check")
        return

    logger.info(f"Enqueuing {len(sites)} sites for check")

    # Push to Celery in batches to avoid flooding Redis
    batch_size = 20
    for i in range(0, len(sites), batch_size):
        batch = sites[i : i + batch_size]
        for site in batch:
            process_site.delay(site.id)
        # Small pause between batches
        if i + batch_size < len(sites):
            await asyncio.sleep(0.5)

    logger.info(f"Enqueued {len(sites)} tasks")


async def dispatch_pending_notifications() -> None:
    """
    Send all unsent notifications via Telegram.
    Called every minute by APScheduler.
    Separated from processing so bot stays responsive.
    """
    from app.db.session import get_db
    from app.db.repositories import NotificationRepo
    from app.notifications.dispatcher import send_notification

    async with get_db() as db:
        pending = await NotificationRepo.get_pending(db)

    if not pending:
        return

    logger.info(f"Dispatching {len(pending)} pending notifications")

    for notification in pending:
        await send_notification(notification)
        # Telegram rate limit: max 30 messages/second globally
        await asyncio.sleep(0.05)