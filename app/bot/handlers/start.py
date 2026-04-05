import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import main_menu_kb
from app.db.repositories import UserRepo

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession) -> None:
    user, created = await UserRepo.get_or_create(
        db,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    if created:
        text = (
            f"Hi, {message.from_user.first_name}!\n\n"
            "I monitor job pages and send notifications "
            "when new positions are available.\n\n"
            "What do we do?"
        )
        logger.info(f"New user registered: {user.telegram_id}")
    else:
        text = f"Welcome back, {message.from_user.first_name}! What do we do?"

    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "<b>Available commands:</b>\n\n"
        "/add_site — add a site for monitoring\n"
        "/my_sites — view your subscriptions\n"
        "/pause — pause all notifications\n"
        "/resume — resume notifications\n"
        "/help — this help\n\n"
        "<b>How it works:</b>\n"
        "The bot checks sites every hour and sends "
        "notifications when new positions are available."
    )
    await message.answer(text)


@router.callback_query(lambda c: c.data == "back_to_start")
async def cb_back_to_start(cb: CallbackQuery) -> None:
    await cb.message.edit_text(
        "Main Menu", reply_markup=main_menu_kb()
    )
    await cb.answer()


@router.callback_query(lambda c: c.data == "help")
async def cb_help(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "Use /add_site to add a site for monitoring."
    )
    await cb.answer()