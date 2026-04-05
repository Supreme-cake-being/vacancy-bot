import asyncio
import logging

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "vacancy_bot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Acknowledge task only after it finishes
    # so it gets retried if worker crashes mid-task
    task_acks_late=True,
    # Take one task at a time per worker
    worker_prefetch_multiplier=1,
    # Kill worker process after N tasks to prevent memory leaks
    # (especially important with Playwright)
    worker_max_tasks_per_child=50,
    # Retry failed tasks with exponential backoff
    task_autoretry_for=(Exception,),
    task_max_retries=3,
    task_default_retry_delay=60,
)


@celery_app.task(bind=True, name="tasks.process_site")
def process_site(self, site_id: int) -> dict:
    """
    Celery task — fetch and diff a single site.
    Runs in a separate process, uses asyncio.run() to call async code.
    """
    try:
        result = asyncio.run(_process_site_async(site_id))
        return result
    except Exception as exc:
        logger.error(f"Task failed for site {site_id}: {exc}")
        raise self.retry(exc=exc)


async def _process_site_async(site_id: int) -> dict:
    """
    Async implementation of the site processing pipeline:
    fetch → diff → save → notify
    """
    from app.db.session import get_db
    from app.db.repositories import SiteRepo
    from app.scraper.fetcher import smart_fetch
    from app.scraper.diff_engine import DiffEngine
    from app.scraper.parsers.spa import get_selector_override

    async with get_db() as db:
        # Load site from DB
        site = await SiteRepo.get_by_id(db, site_id)
        if not site or not site.is_active:
            logger.info(f"Site {site_id} not found or inactive — skipping")
            return {"skipped": True}

        logger.info(f"Processing site {site_id}: {site.url}")

        # Fetch HTML — use SPA mode if configured
        html = await smart_fetch(site.url, parse_type=site.parse_type)
        if not html:
            logger.warning(f"Failed to fetch {site.url}")
            return {"error": "fetch_failed"}

        # Check for selector override for known SPA sites
        selector = get_selector_override(site.url) or site.css_selector

        # Run diff
        engine = DiffEngine(css_selector=selector)
        known_hashes = await SiteRepo.get_vacancy_hashes(db, site_id)
        result = engine.compare(
            html=html,
            known_hashes=known_hashes,
            previous_page_hash=site.last_hash,
        )

        # Auto-save detected selector for future runs
        if result.selector_used and not site.css_selector:
            await SiteRepo.update_selector(db, site_id, result.selector_used)

        # Save new vacancies and send notifications
        if result.has_new:
            await _save_and_notify(db, site, result.new_vacancies)

        # Always update page hash and checked_at
        new_page_hash = engine.compute_page_hash(html)
        await SiteRepo.update_check_state(db, site_id, new_page_hash)

        return {
            "site_id": site_id,
            "new_vacancies": len(result.new_vacancies),
            "removed": result.removed_count,
        }


async def _save_and_notify(db, site, new_vacancies: list) -> None:
    """Save new vacancies to DB and queue notifications."""
    from app.db.repositories import SubscriptionRepo, VacancyRepo, NotificationRepo

    subscriptions = await SubscriptionRepo.get_active_for_site(db, site.id)
    if not subscriptions:
        logger.info(f"No active subscriptions for site {site.id}")
        return

    for vacancy in new_vacancies:
        # Resolve relative URL to absolute
        abs_url = vacancy.absolute_url(site.url)

        # Save vacancy to DB
        db_vacancy = await VacancyRepo.create(
            db,
            site_id=site.id,
            title=vacancy.title,
            url=abs_url,
            hash=vacancy.hash,
        )

        # Create notification for each matching subscriber
        for sub in subscriptions:
            keywords = sub.user.keywords_list() if sub.user.keywords else []
            if not vacancy.matches_keywords(keywords):
                logger.debug(
                    f"Vacancy '{vacancy.title}' skipped for user "
                    f"{sub.user_id} — no keyword match"
                )
                continue

            await NotificationRepo.create(
                db,
                user_id=sub.user_id,
                vacancy_id=db_vacancy.id,
            )

    logger.info(
        f"Saved {len(new_vacancies)} vacancies for site {site.id}, "
        f"notified {len(subscriptions)} subscribers"
    )