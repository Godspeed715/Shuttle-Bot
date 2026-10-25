"""
bot/keyboards/common.py -- Shared keyboards used across multiple handlers.

These are generic, reusable keyboards that are not specific to any one
user role or flow. Import them wherever a role picker, confirm dialog,
or back button is needed.
"""

from telebot import types


def role_keyboard() -> types.InlineKeyboardMarkup:
    """Return a two-button keyboard for Student / Driver role selection.

    Used at the very start of the /start onboarding flow when the user
    has not yet been assigned a role.
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("ðŸŽ“ Student", callback_data="role:student"),
        types.InlineKeyboardButton("ðŸš Driver",  callback_data="role:driver"),
    )
    return mk


def vehicle_type_keyboard() -> types.InlineKeyboardMarkup:
    """Return a two-button keyboard for Car / Siena vehicle-type selection.

    Shown during driver registration so the driver can declare the
    vehicle they operate and its passenger capacity.
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("ðŸš— Car (max 4)",   callback_data="vtype:car"),
        types.InlineKeyboardButton("ðŸš Siena (max 7)", callback_data="vtype:siena"),
    )
    return mk


def confirm_keyboard(
    yes_data: str,
    no_data: str,
    yes_label: str = "âœ… Yes",
    no_label: str = "âŒ No",
) -> types.InlineKeyboardMarkup:
    """Return a generic Yes / No confirmation keyboard.

    Args:
        yes_data:  Callback data string for the affirmative button.
        no_data:   Callback data string for the negative button.
        yes_label: Display text for the Yes button (default 'Yes').
        no_label:  Display text for the No button  (default 'No').

    Returns:
        InlineKeyboardMarkup with two buttons side by side.
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton(yes_label, callback_data=yes_data),
        types.InlineKeyboardButton(no_label,  callback_data=no_data),
    )
    return mk


def back_keyboard(
    callback_data: str,
    label: str = "⬅️ Back",
) -> types.InlineKeyboardMarkup:
    """Return a single Back / Cancel button keyboard.

    Args:
        callback_data: The callback string the button fires.
        label:         Button display text (default 'Back').

    Returns:
        InlineKeyboardMarkup with one button.
    """
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton(label, callback_data=callback_data))
    return mk

