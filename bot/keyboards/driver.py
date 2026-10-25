"""
bot/keyboards/driver.py -- Keyboards for the driver dashboard and wallet flows.

All functions return InlineKeyboardMarkup. Callback data is short and
colon-separated so handlers can reconstruct context without session state.
"""

from telebot import types


def driver_dashboard_keyboard(
    shuttle_id: int,
    is_available: bool,
    has_active_ride: bool,
) -> types.InlineKeyboardMarkup:
    """Return the driver main control-panel keyboard.

    The keyboard is context-sensitive:
    - Availability toggle switches label/callback based on current status.
    - Trip management buttons (Complete / View Passenger) only appear when
      there is an active ride so the dashboard stays uncluttered otherwise.
    - Wallet button is always visible.

    Args:
        shuttle_id:      DB primary key of the driver's shuttle record.
        is_available:    True if the shuttle is currently online/available.
        has_active_ride: True if there is a ride currently in progress.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            sht:off:{shuttle_id}    -- go offline
            sht:on:{shuttle_id}     -- go online
            sht:loc:{shuttle_id}    -- update current location
            sht:cmp:{shuttle_id}    -- complete active trip
            sht:pax:{shuttle_id}    -- view active passenger info
            sht:wallet:{shuttle_id} -- open wallet
    """
    mk = types.InlineKeyboardMarkup(row_width=1)
    sid = str(shuttle_id)

    # Availability toggle
    if is_available:
        mk.add(
            types.InlineKeyboardButton(
                "Go Offline 🔴", callback_data="sht:off:" + sid
            )
        )
    else:
        mk.add(
            types.InlineKeyboardButton(
                "Go Online 🟢", callback_data="sht:on:" + sid
            )
        )

    # Location update is always visible while the driver is logged in
    mk.add(
        types.InlineKeyboardButton(
            "Update Location 📍", callback_data="sht:loc:" + sid
        )
    )

    # Trip management -- only shown when a ride is active
    if has_active_ride:
        mk.add(
            types.InlineKeyboardButton(
                "Complete Trip 🏁", callback_data="sht:cmp:" + sid
            )
        )
        mk.add(
            types.InlineKeyboardButton(
                "View Passenger 👤", callback_data="sht:pax:" + sid
            )
        )

    # Wallet always accessible
    mk.add(
        types.InlineKeyboardButton(
            "💰 My Wallet", callback_data="sht:wallet:" + sid
        )
    )

    return mk


def location_update_keyboard(
    locations: list,
    shuttle_id: int,
) -> types.InlineKeyboardMarkup:
    """Return a campus-location grid for the driver to update their position.

    Args:
        locations:  List of location dicts with 'id' and 'name' keys.
        shuttle_id: DB primary key of the driver's shuttle record.

    Returns:
        InlineKeyboardMarkup (row_width=2, cancel on its own row).
        Callback format: sloc:{shuttle_id}:{location_id}
        Cancel button:   sloc:{shuttle_id}:cancel
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    sid = str(shuttle_id)

    buttons = [
        types.InlineKeyboardButton(
            loc["name"],
            callback_data="sloc:" + sid + ":" + str(loc["id"]),
        )
        for loc in locations
    ]
    mk.add(*buttons)

    # Cancel exits back to the dashboard without changing location
    mk.add(
        types.InlineKeyboardButton(
            "Cancel", callback_data="sloc:" + sid + ":cancel"
        )
    )
    return mk


def ride_response_keyboard(ride_id: int) -> types.InlineKeyboardMarkup:
    """Return Accept / Reject buttons sent to the driver when a ride is matched.

    Args:
        ride_id: DB primary key of the incoming ride request.

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: acc:{ride_id}  (accept)
                         rej:{ride_id}  (reject)
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    rid = str(ride_id)
    mk.add(
        types.InlineKeyboardButton("Accept", callback_data="acc:" + rid),
        types.InlineKeyboardButton("Reject", callback_data="rej:" + rid),
    )
    return mk


def wallet_keyboard(
    has_bank: bool,
    can_withdraw: bool,
) -> types.InlineKeyboardMarkup:
    """Return wallet action buttons for the driver wallet screen.

    - Withdraw button is suppressed when the balance is zero.
    - Bank button label changes depending on whether a bank account is
      already linked, guiding first-time setup vs. editing.

    Args:
        has_bank:     True if the driver already has a linked bank account.
        can_withdraw: True if the driver's withdrawable balance > 0.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            wlt:withdraw -- initiate a withdrawal
            wlt:bank     -- link or change bank account
    """
    mk = types.InlineKeyboardMarkup(row_width=1)

    # Only show withdraw button when there is money to withdraw
    if can_withdraw:
        mk.add(
            types.InlineKeyboardButton(
                "💸 Withdraw", callback_data="wlt:withdraw"
            )
        )

    # Adaptive label for bank account action
    bank_label = "🏦 Change Bank" if has_bank else "🏦 Link Bank Account"
    mk.add(
        types.InlineKeyboardButton(bank_label, callback_data="wlt:bank")
    )

    return mk


def bank_list_keyboard(banks: list) -> types.InlineKeyboardMarkup:
    """Return a scrollable list of Nigerian banks for account onboarding.

    NOTE: The number of banks from most payment APIs (e.g. Paystack) can
    exceed 50. Consider adding pagination (e.g. bnk:pg:{page}) in a future
    iteration rather than sending all banks in one keyboard, which Telegram
    may truncate or render poorly.

    Args:
        banks: List of dicts with 'name' and 'code' keys as returned by
               the payment provider's bank-list endpoint.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback format: bnk:{bank_code}
        Cancel button:   bnk:cancel
    """
    mk = types.InlineKeyboardMarkup(row_width=1)

    for bank in banks:
        mk.add(
            types.InlineKeyboardButton(
                bank["name"], callback_data="bnk:" + bank["code"]
            )
        )

    mk.add(types.InlineKeyboardButton("Cancel", callback_data="bnk:cancel"))
    return mk


def withdraw_confirm_keyboard(amount: int) -> types.InlineKeyboardMarkup:
    """Return a Confirm / Cancel keyboard for a pending withdrawal.

    The amount is embedded in the confirm callback so the handler can
    validate it again server-side against the current balance without
    relying on session state.

    Args:
        amount: Withdrawal amount in Naira (integer, not kobo).

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: wlt:confirm:{amount}
                         wlt:cancel
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton(
            "Confirm", callback_data="wlt:confirm:" + str(amount)
        ),
        types.InlineKeyboardButton("Cancel", callback_data="wlt:cancel"),
    )
    return mk

