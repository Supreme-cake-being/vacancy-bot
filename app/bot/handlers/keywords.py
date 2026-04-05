import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import cancel_kb
from app.db.repositories import UserRepo

router = Router()
logger = logging.getLogger(__name__)

class KeywordsStates(StatesGroup):
    waiting_keywords = State()

@router.message(Command("keywords"))
async def cmd_keywords(message: Message, state: FSMContext, db: AsyncSession) -> None:
    user = await UserRepo.get_by_telegram_id(db, message.from_user.id)

    current = (
        f"Current keywords:\n<code>{user.keywords}</code>\n\n"
        if user.keywords
        else "Keywords are not yet set up.\n\n"
    )

    await message.answer(
        f"{current}"
        "Enter new keywords separated by commas:\n"
        "<code>Python, Remote, Senior</code>\n\n"
        "Or send <code>-</code> to remove the filter and receive all job postings.",
        reply_markup=cancel_kb(),
    )
    await state.set_state(KeywordsStates.waiting_keywords)

@router.message(KeywordsStates.waiting_keywords, F.text)
async def process_keywords(
    message: Message, state: FSMContext, db: AsyncSession
) -> None:
    text = message.text.strip()

    if text == "-":
        # Remove the filter
        await UserRepo.set_keywords(db, message.from_user.id, keywords=None)
        await state.clear()
        await message.answer(
            "Filter removed. Now you will receive all job postings."
        )
        return

    # Normalize: remove extra whitespace around commas
    keywords = ", ".join(
        k.strip() for k in text.split(",") if k.strip()
    )

    if not keywords:
        await message.answer(
            "Failed to recognize keywords. Try again.\n"
            "Example: <code>Python, Remote, Senior</code>",
            reply_markup=cancel_kb(),
        )
        return

    await UserRepo.set_keywords(db, message.from_user.id, keywords=keywords)
    await state.clear()

    await message.answer(
        f"Keywords saved:\n<code>{keywords}</code>\n\n"
        f"Now I will search for them on all your sites."
    )
    logger.info(f"User {message.from_user.id} set keywords: {keywords}")