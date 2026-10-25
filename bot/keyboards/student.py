"""
bot/keyboards/student.py -- Keyboards for the student booking flow.

All functions return InlineKeyboardMarkup instances. Callback data is
short and colon-separated so handlers can split and reconstruct context.
Money amounts (fares) are handled by the handler layer, not here.
"""

from telebot import types
from config import MAX_PASSENGERS_CAR, MAX_PASSENGERS_SIENA


def pickup_keyboard(locations: list) -> types.InlineKeyboardMarkup:
    """Return a grid of campus-location buttons for pickup selection.

    Args:
        locations: List of dicts with at least 'id' and 'name' keys,
                   sourced from the locations DB table.

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: pk:{location_id}
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            loc["name"],
            callback_data="pk:" + str(loc["id"]),
        )
        for loc in locations
    ]
    mk.add(*buttons)
    return mk


def destination_keyboard(
    locations: list,
    pickup_id: int,
    exclude_id: int = None,
) -> types.InlineKeyboardMarkup:
    """Return a grid of campus-location buttons for destination selection.

    Excludes the already-chosen pickup location (and any extra exclusion)
    so the student cannot pick the same stop twice.

    Args:
        locations:  Full list of location dicts from the DB.
        pickup_id:  ID of the chosen pickup location (carried in callback).
        exclude_id: Optional additional location ID to exclude.

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: dst:{pickup_id}:{location_id}
    """
    mk = types.InlineKeyboardMarkup(row_width=2)

    # Build the exclusion set; always exclude the pickup itself
    excluded = {pickup_id}
    if exclude_id is not None:
        excluded.add(exclude_id)

    buttons = [
        types.InlineKeyboardButton(
            loc["name"],
            callback_data="dst:" + str(pickup_id) + ":" + str(loc["id"]),
        )
        for loc in locations
        if loc["id"] not in excluded
    ]
    mk.add(*buttons)
    return mk


def passenger_count_keyboard(
    pickup_id: int,
    dest_id: int,
    vehicle_type: str = "car",
) -> types.InlineKeyboardMarkup:
    """Return numbered passenger-count buttons for the chosen vehicle type.

    Capacity limits are read from config:
        car   -> MAX_PASSENGERS_CAR   (typically 4)
        siena -> MAX_PASSENGERS_SIENA (typically 7)

    A 'More...' overflow button is appended after the numbered buttons for
    cases where the student needs to type a custom number (e.g. group bookings).

    Args:
        pickup_id:    ID of the pickup location.
        dest_id:      ID of the destination location.
        vehicle_type: 'car' or 'siena' (default 'car').

    Returns:
        InlineKeyboardMarkup (row_width=4 for numbered, 1 for More).
        Callback format (numbers): pax:{pickup_id}:{dest_id}:{count}
        Callback format (more):    pax:{pickup_id}:{dest_id}:more
    """
    # Determine max seats from config based on vehicle type
    if vehicle_type == "siena":
        max_pax = MAX_PASSENGERS_SIENA
    else:
        max_pax = MAX_PASSENGERS_CAR

    mk = types.InlineKeyboardMarkup(row_width=4)

    # Build one numbered button per seat (1 .. max_pax)
    prefix = "pax:" + str(pickup_id) + ":" + str(dest_id) + ":"
    number_buttons = [
        types.InlineKeyboardButton(str(n), callback_data=prefix + str(n))
        for n in range(1, max_pax + 1)
    ]
    mk.add(*number_buttons)

    # Overflow / custom-amount button on its own row
    mk.add(
        types.InlineKeyboardButton(
            "🔢 More...",
            callback_data=prefix + "more",
        )
    )
    return mk


def payment_method_keyboard(
    pickup_id: int,
    dest_id: int,
    pax: int,
) -> types.InlineKeyboardMarkup:
    """Return Cash / Transfer payment method buttons.

    Returns:
        Callback format: pay:{pickup_id}:{dest_id}:{pax}:cash
                         pay:{pickup_id}:{dest_id}:{pax}:transfer
    """
    base = "pay:" + str(pickup_id) + ":" + str(dest_id) + ":" + str(pax) + ":"
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("💵 Cash",     callback_data=base + "cash"),
        types.InlineKeyboardButton("🏦 Transfer", callback_data=base + "transfer"),
    )
    return mk


def drivers_keyboard(
    shuttles: list,
    pickup_id: int,
    dest_id: int,
    pax: int,
    payment_method: str = 'cash',
) -> types.InlineKeyboardMarkup:
    """Return a list of available shuttle/driver buttons.

    Args:
        shuttles:       List of dicts with 'id', 'name', 'driver_name', 'vehicle_type'.
        pickup_id:      ID of the pickup location.
        dest_id:        ID of the destination location.
        pax:            Number of passengers.
        payment_method: 'cash' or 'transfer'.

    Returns:
        Callback format: drv:{pickup_id}:{dest_id}:{pax}:{shuttle_id}:{payment_method}
        Cancel button:   drv:0:0:0:cancel:cash
    """
    mk = types.InlineKeyboardMarkup(row_width=1)

    for shuttle in shuttles:
        vtype = shuttle.get("vehicle_type", "car")
        v_label = "Siena" if vtype == "siena" else "Car"
        label = (shuttle["driver_name"] + " | " + shuttle["name"]
                 + " (" + v_label + ")")
        cb = ("drv:" + str(pickup_id) + ":" + str(dest_id) + ":"
              + str(pax) + ":" + str(shuttle["id"]) + ":" + payment_method)
        mk.add(types.InlineKeyboardButton(label, callback_data=cb))

    mk.add(types.InlineKeyboardButton(
        "❌ Cancel", callback_data="drv:0:0:0:cancel:" + payment_method))
    return mk


def cancel_confirm_keyboard(ride_id: int) -> types.InlineKeyboardMarkup:
    """Return a Yes-cancel / No-keep confirmation for ride cancellation.

    Args:
        ride_id: Primary key of the ride the student wants to cancel.

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format (yes): cnly:{ride_id}
        Callback format (no):  cnln:{ride_id}
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton(
            "Yes, Cancel ❌", callback_data="cnly:" + str(ride_id)
        ),
        types.InlineKeyboardButton(
            "No, Keep ✅", callback_data="cnln:" + str(ride_id)
        ),
    )
    return mk

