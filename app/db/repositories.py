from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Notification, Site, Subscription, User, Vacancy

class UserRepo:

    @staticmethod
    async def get_by_telegram_id(
        db: AsyncSession, telegram_id: int
    ) -> User | None:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> tuple[User, bool]:
        user = await UserRepo.get_by_telegram_id(db, telegram_id)
        if user:
            return user, False
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        db.add(user)
        await db.flush()
        return user, True

    @staticmethod
    async def set_keywords(
        db: AsyncSession, telegram_id: int, keywords: str | None
    ) -> None:
        """Зберігає ключові слова для користувача."""
        await db.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(keywords=keywords)
        )

class SiteRepo:

    @staticmethod
    async def get_by_url(db: AsyncSession, url: str) -> Site | None:
        result = await db.execute(select(Site).where(Site.url == url))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        db: AsyncSession, url: str, name: str | None = None
    ) -> tuple[Site, bool]:
        site = await SiteRepo.get_by_url(db, url)
        if site:
            return site, False
        site = Site(url=url, name=name)
        db.add(site)
        await db.flush()
        return site, True

    @staticmethod
    async def get_due_for_check(db: AsyncSession) -> list[Site]:
        """Sites that need to be checked — haven't been checked for longer than check_interval_min."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Site).where(
                Site.is_active == True,
                # checked_at IS NULL (never checked)
                # OR checked_at + interval < now
                (Site.checked_at == None)
                | (
                    Site.checked_at
                    < now - timedelta(minutes=1) * Site.check_interval_min
                ),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_vacancy_hashes(db: AsyncSession, site_id: int) -> set[str]:
        """All known hashes of vacancies for the site."""
        result = await db.execute(
            select(Vacancy.hash).where(Vacancy.site_id == site_id)
        )
        return set(result.scalars().all())

    @staticmethod
    async def update_check_state(
        db: AsyncSession, site_id: int, new_hash: str
    ) -> None:
        await db.execute(
            update(Site)
            .where(Site.id == site_id)
            .values(
                last_hash=new_hash,
                checked_at=datetime.now(timezone.utc),
            )
        )

class SubscriptionRepo:

    @staticmethod
    async def get_by_user(
        db: AsyncSession, user_id: int
    ) -> list[Subscription]:
        result = await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .options(selectinload(Subscription.site))
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_for_site(
        db: AsyncSession, site_id: int
    ) -> list[Subscription]:
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.site_id == site_id,
                Subscription.is_active == True,
            )
            .options(selectinload(Subscription.user))
        )
        return list(result.scalars().all())

    @staticmethod
    async def exists(
        db: AsyncSession, user_id: int, site_id: int
    ) -> bool:
        result = await db.execute(
            select(Subscription.id).where(
                Subscription.user_id == user_id,
                Subscription.site_id == site_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        site_id: int,
    ) -> Subscription:
        sub = Subscription(user_id=user_id, site_id=site_id)
        db.add(sub)
        await db.flush()
        return sub

    @staticmethod
    async def deactivate(
        db: AsyncSession, user_id: int, site_id: int
    ) -> None:
        await db.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.site_id == site_id,
            )
            .values(is_active=False)
        )

class VacancyRepo:

    @staticmethod
    async def create(
        db: AsyncSession,
        site_id: int,
        title: str,
        url: str | None,
        hash: str,
    ) -> Vacancy:
        vacancy = Vacancy(
            site_id=site_id,
            title=title,
            url=url,
            hash=hash,
        )
        db.add(vacancy)
        await db.flush()
        return vacancy

class NotificationRepo:

    @staticmethod
    async def create(
        db: AsyncSession, user_id: int, vacancy_id: int
    ) -> Notification:
        notif = Notification(user_id=user_id, vacancy_id=vacancy_id)
        db.add(notif)
        await db.flush()
        return notif

    @staticmethod
    async def get_pending(db: AsyncSession) -> list[Notification]:
        result = await db.execute(
            select(Notification)
            .where(Notification.sent == False)
            .options(
                selectinload(Notification.user),
                selectinload(Notification.vacancy),
            )
            .order_by(Notification.id)
            .limit(100)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_sent(db: AsyncSession, notification_id: int) -> None:
        await db.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(sent=True, sent_at=datetime.now(timezone.utc))
        )