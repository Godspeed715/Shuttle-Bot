"""
Inline keyboard builders for the Telegram bot.
Every function returns a telebot InlineKeyboardMarkup.
"""
from telebot import types


def role_keyboard():
    """Student / Driver role selection."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton('🎓 Student', callback_data='role:student'),
        types.InlineKeyboardButton('🚐 Driver',  callback_data='role:driver'),
    )
    return mk


def pickup_keyboard(locations):
    """Grid of campus locations for pickup selection."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(l['name'], callback_data=f"pk:{l['id']}") for l in locations]
    for i in range(0, len(btns), 2):
        mk.add(*btns[i:i+2])
    return mk


def destination_keyboard(locations, pickup_id, exclude_id=None):
    """Grid of campus locations for destination (carries pickup_id in callback)."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton(l['name'], callback_data=f"dst:{pickup_id}:{l['id']}")
        for l in locations if l['id'] != exclude_id
    ]
    for i in range(0, len(btns), 2):
        mk.add(*btns[i:i+2])
    return mk


def drivers_keyboard(shuttles, pickup_id, dest_id):
    """List of available shuttles (carries pickup + dest in callback)."""
    mk = types.InlineKeyboardMarkup(row_width=1)
    for s in shuttles:
        mk.add(types.InlineKeyboardButton(
            f"🚐 {s['name']} — {s['driver_name']}",
            callback_data=f"drv:{pickup_id}:{dest_id}:{s['id']}",
        ))
    mk.add(types.InlineKeyboardButton('❌ Cancel', callback_data=f"drv:0:0:cancel"))
    return mk


def ride_response_keyboard(ride_id):
    """Accept / Reject buttons sent to driver."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton('Accept ✅', callback_data=f'acc:{ride_id}'),
        types.InlineKeyboardButton('Reject ❌', callback_data=f'rej:{ride_id}'),
    )
    return mk


def cancel_confirm_keyboard(ride_id):
    """Confirm ride cancellation."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton('Yes, Cancel', callback_data=f'cnly:{ride_id}'),
        types.InlineKeyboardButton('No, Keep',    callback_data=f'cnln:{ride_id}'),
    )
    return mk


def admin_approval_keyboard(req_id):
    """Approve / Reject a driver registration."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton('Approve ✅', callback_data=f'apv:{req_id}'),
        types.InlineKeyboardButton('Reject ❌',  callback_data=f'arj:{req_id}'),
    )
    return mk


def driver_dashboard_keyboard(shuttle_id, is_available, has_active_ride):
    """Driver's main control panel."""
    mk = types.InlineKeyboardMarkup(row_width=1)
    if is_available:
        mk.add(types.InlineKeyboardButton('Go Offline 🔴', callback_data=f'sht:off:{shuttle_id}'))
    else:
        mk.add(types.InlineKeyboardButton('Go Online 🟢', callback_data=f'sht:on:{shuttle_id}'))
    mk.add(types.InlineKeyboardButton('Update Location 📍', callback_data=f'sht:loc:{shuttle_id}'))
    if has_active_ride:
        mk.add(types.InlineKeyboardButton('Complete Trip 🏁', callback_data=f'sht:cmp:{shuttle_id}'))
        mk.add(types.InlineKeyboardButton('View Passenger 👤', callback_data=f'sht:pax:{shuttle_id}'))
    return mk


def location_update_keyboard(locations, shuttle_id):
    """Grid of locations for driver to set their current position."""
    mk = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton(l['name'], callback_data=f"sloc:{shuttle_id}:{l['id']}")
        for l in locations
    ]
    for i in range(0, len(btns), 2):
        mk.add(*btns[i:i+2])
    mk.add(types.InlineKeyboardButton('Cancel', callback_data=f"sloc:{shuttle_id}:cancel"))
    return mk
