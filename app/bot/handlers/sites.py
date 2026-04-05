import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    cancel_kb,
    confirm_remove_kb,
    site_actions_kb,
    skip_kb,
    subscriptions_kb,
)
from app.db.repositories import SiteRepo, SubscriptionRepo, UserRepo

router = Router()
logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

class AddSiteStates(StatesGroup):
    waiting_url = State()
    waiting_keywords = State()

class EditKeywordsStates(StatesGroup):
    waiting_keywords = State()

# Add Site Flow

@router.message(Command("add_site"))
@router.callback_query(lambda c: c.data == "add_site")
async def cmd_add_site(event: Message | CallbackQuery, state: FSMContext) -> None:
    text = (
        "Send URL of a webpage with job openings.\n\n"
        "<b>Examples:</b>\n"
        "https://company.com/careers\n"
        "https://jobs.company.com\n"
    )
    kb = cancel_kb()

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)

    await state.set_state(AddSiteStates.waiting_url)

@router.message(AddSiteStates.waiting_url, F.text)
async def process_url(
    message: Message, state: FSMContext, db: AsyncSession
) -> None:
    url = message.text.strip().rstrip("/")

    # Validation of URL
    if not URL_REGEX.match(url):
        await message.answer(
            "Invalid URL. Must start with <code>https://</code>\n"
            "Try again or press Cancel.",
            reply_markup=cancel_kb(),
        )
        return

    # Check if already subscribed
    user = await UserRepo.get_by_telegram_id(db, message.from_user.id)
    site, _ = await SiteRepo.get_or_create(db, url=url)

    if await SubscriptionRepo.exists(db, user_id=user.id, site_id=site.id):
        await message.answer(
            "You are already subscribed to this site.\n"
            "View subscriptions: /my_sites"
        )
        await state.clear()
        return

    await state.update_data(url=url, site_id=site.id)
    await state.set_state(AddSiteStates.waiting_keywords)

    await message.answer(
        "Add keywords for filtering job postings?\n\n"
        "Enter them separated by commas:\n"
        "<code>Python, Remote, Senior</code>\n\n"
        "Or press <b>Skip</b> to receive all job postings.",
        reply_markup=skip_kb(),
    )

@router.message(AddSiteStates.waiting_keywords, F.text)
async def process_keywords(
    message: Message, state: FSMContext, db: AsyncSession
) -> None:
    data = await state.get_data()
    keywords = message.text.strip()

    await _finalize_subscription(message, state, db, data, keywords)

@router.callback_query(
    AddSiteStates.waiting_keywords, lambda c: c.data == "skip_keywords"
)
async def skip_keywords(
    cb: CallbackQuery, state: FSMContext, db: AsyncSession
) -> None:
    data = await state.get_data()
    await _finalize_subscription(cb.message, state, db, data, keywords=None)
    await cb.answer()

async def _finalize_subscription(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    data: dict,
    keywords: str | None,
) -> None:
    user = await UserRepo.get_by_telegram_id(db, message.chat.id)
    await SubscriptionRepo.create(
        db,
        user_id=user.id,
        site_id=data["site_id"],
        keywords=keywords,
    )
    await state.clear()

    kw_text = f"Keywords: <code>{keywords}</code>" if keywords else "All job postings"
    await message.answer(
        f"Subscription added!\n\n"
        f"Site: <code>{data['url']}</code>\n"
        f"{kw_text}\n\n"
        f"First check will happen within an hour."
    )
    logger.info(
        f"User {message.chat.id} subscribed to {data['url']} "
        f"with keywords: {keywords}"
    )

# Cancel FSM

@router.callback_query(lambda c: c.data == "cancel_fsm")
async def cancel_fsm(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text(
        "Cancelled. What to do next?",
        reply_markup=None,
    )
    await cb.answer()

# View Subscriptions

@router.message(Command("my_sites"))
@router.callback_query(lambda c: c.data == "my_sites")
async def cmd_my_sites(
    event: Message | CallbackQuery, db: AsyncSession
) -> None:
    tg_id = (
        event.from_user.id
        if isinstance(event, Message)
        else event.from_user.id
    )
    user = await UserRepo.get_by_telegram_id(db, tg_id)
    subscriptions = await SubscriptionRepo.get_by_user(db, user.id)

    if not subscriptions:
        text = (
            "You don't have any subscriptions yet.\n"
            "Add your first site with the /add_site command."
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
            await event.answer()
        else:
            await event.answer(text)
        return

    text = f"Your subscriptions ({len(subscriptions)}):"
    kb = subscriptions_kb(subscriptions)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)

# Menu for a Specific Site

@router.callback_query(lambda c: c.data.startswith("site_menu:"))
async def cb_site_menu(cb: CallbackQuery, db: AsyncSession) -> None:
    site_id = int(cb.data.split(":")[1])
    user = await UserRepo.get_by_telegram_id(db, cb.from_user.id)
    subs = await SubscriptionRepo.get_by_user(db, user.id)

    sub = next((s for s in subs if s.site_id == site_id), None)
    if not sub:
        await cb.answer("Subscription not found")
        return

    kw_text = (
        f"Keywords: <code>{sub.keywords}</code>"
        if sub.keywords
        else "Filter: all job postings"
    )
    status = "active" if sub.is_active else "on hold"

    await cb.message.edit_text(
        f"<b>{sub.site.name or sub.site.url}</b>\n\n"
        f"Status: {status}\n"
        f"{kw_text}",
        reply_markup=site_actions_kb(site_id, sub.is_active),
    )
    await cb.answer()

# Pause / Resume

@router.callback_query(lambda c: c.data.startswith("pause_site:"))
async def cb_pause_site(cb: CallbackQuery, db: AsyncSession) -> None:
    site_id = int(cb.data.split(":")[1])
    user = await UserRepo.get_by_telegram_id(db, cb.from_user.id)
    await SubscriptionRepo.deactivate(db, user_id=user.id, site_id=site_id)
    await cb.answer("Notifications paused")
    await cb.message.edit_reply_markup(
        reply_markup=site_actions_kb(site_id, is_active=False)
    )

@router.callback_query(lambda c: c.data.startswith("resume_site:"))
async def cb_resume_site(cb: CallbackQuery, db: AsyncSession) -> None:
    from sqlalchemy import update
    from app.db.models import Subscription

    site_id = int(cb.data.split(":")[1])
    user = await UserRepo.get_by_telegram_id(db, cb.from_user.id)
    await db.execute(
        update(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.site_id == site_id,
        )
        .values(is_active=True)
    )
    await cb.answer("Notifications resumed")
    await cb.message.edit_reply_markup(
        reply_markup=site_actions_kb(site_id, is_active=True)
    )

# Remove subscription

@router.callback_query(lambda c: c.data.startswith("remove_site:"))
async def cb_remove_site(cb: CallbackQuery, db: AsyncSession) -> None:
    site_id = int(cb.data.split(":")[1])
    await cb.message.edit_text(
        "Remove subscription?\nJob postings from this site will no longer be sent.",
        reply_markup=confirm_remove_kb(site_id),
    )
    await cb.answer()

@router.callback_query(lambda c: c.data.startswith("confirm_remove:"))
async def cb_confirm_remove(cb: CallbackQuery, db: AsyncSession) -> None:
    site_id = int(cb.data.split(":")[1])
    user = await UserRepo.get_by_telegram_id(db, cb.from_user.id)
    await SubscriptionRepo.deactivate(db, user_id=user.id, site_id=site_id)
    await cb.answer("Subscription removed")
    await cb.message.edit_text("Subscription removed.")
    logger.info(f"User {cb.from_user.id} removed subscription to site {site_id}")

# Edit keywords

@router.callback_query(lambda c: c.data.startswith("edit_keywords:"))
async def cb_edit_keywords(cb: CallbackQuery, state: FSMContext) -> None:
    site_id = int(cb.data.split(":")[1])
    await state.set_state(EditKeywordsStates.waiting_keywords)
    await state.update_data(site_id=site_id)
    await cb.message.edit_text(
        "Enter new keywords separated by comma:\n"
        "<code>Python, Remote, Senior</code>\n\n"
        "Or press <b>Skip</b> to remove the filter.",
        reply_markup=skip_kb(),
    )
    await cb.answer()

@router.message(EditKeywordsStates.waiting_keywords, F.text)
async def process_edit_keywords(
    message: Message, state: FSMContext, db: AsyncSession
) -> None:
    data = await state.get_data()
    await _save_keywords(message, state, db, data, message.text.strip())

@router.callback_query(
    EditKeywordsStates.waiting_keywords, lambda c: c.data == "skip_keywords"
)
async def skip_edit_keywords(
    cb: CallbackQuery, state: FSMContext, db: AsyncSession
) -> None:
    data = await state.get_data()
    await _save_keywords(cb.message, state, db, data, keywords=None)
    await cb.answer()

async def _save_keywords(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    data: dict,
    keywords: str | None,
) -> None:
    from sqlalchemy import update
    from app.db.models import Subscription

    user = await UserRepo.get_by_telegram_id(db, message.chat.id)
    await db.execute(
        update(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.site_id == data["site_id"],
        )
        .values(keywords=keywords)
    )
    await state.clear()
    kw_text = f"<code>{keywords}</code>" if keywords else "removed"
    await message.answer(f"Keywords {kw_text} saved.")