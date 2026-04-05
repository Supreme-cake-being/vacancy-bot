from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Subscription, Site

def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Add Site", callback_data="add_site")
    builder.button(text="My Subscriptions", callback_data="my_sites")
    builder.button(text="Edit Keywords", callback_data="edit_keywords")
    builder.button(text="Help", callback_data="help")
    builder.adjust(2, 2) 
    return builder.as_markup()

def subscriptions_kb(
    subscriptions: list[Subscription],
) -> InlineKeyboardMarkup:
    """List of subscriptions with control buttons."""
    builder = InlineKeyboardBuilder()
    for sub in subscriptions:
        site_name = sub.site.name or sub.site.url[:30]
        status = "" if sub.is_active else " (пауза)"
        builder.button(
            text=f"{site_name}{status}",
            callback_data=f"site_menu:{sub.site_id}",
        )
    builder.button(text="Add Site", callback_data="add_site")
    builder.button(text="Back", callback_data="back_to_start")
    builder.adjust(1)
    return builder.as_markup()

def site_actions_kb(site_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Actions for a specific site."""
    builder = InlineKeyboardBuilder()
    if is_active:
        builder.button(
            text="Pause", callback_data=f"pause_site:{site_id}"
        )
    else:
        builder.button(
            text="Resume", callback_data=f"resume_site:{site_id}"
        )
    builder.button(
        text="Edit Keywords",
        callback_data=f"edit_keywords:{site_id}",
    )
    builder.button(
        text="Delete Subscription",
        callback_data=f"remove_site:{site_id}",
    )
    builder.button(text="Back to List", callback_data="my_sites")
    builder.adjust(1)
    return builder.as_markup()

def confirm_remove_kb(site_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Yes, delete", callback_data=f"confirm_remove:{site_id}"
    )
    builder.button(text="Cancel", callback_data=f"site_menu:{site_id}")
    builder.adjust(2)
    return builder.as_markup()

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data="cancel_fsm")
    return builder.as_markup()

def skip_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Skip", callback_data="skip_keywords")
    builder.button(text="Cancel", callback_data="cancel_fsm")
    builder.adjust(2)
    return builder.as_markup()