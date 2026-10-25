"""
bot/keyboards/admin.py -- Keyboards for admin panel, driver approval, route prices, remittances.

All functions return InlineKeyboardMarkup. Callback prefixes:
    adm:  -- top-level admin navigation
    apv:  -- driver approval
    arj:  -- driver rejection
    rp:   -- route price management
    rem:  -- remittance collection
"""

from telebot import types


def admin_panel_keyboard() -> types.InlineKeyboardMarkup:
    """Return the top-level admin control-panel keyboard.

    Three entry points for the three main admin workflows:
    remittance tracking, route price management, and driver management.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            adm:remit   -- view outstanding cash remittances
            adm:prices  -- manage route prices
            adm:drivers -- manage / approve drivers
    """
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        types.InlineKeyboardButton(
            "📊 Cash Remittances", callback_data="adm:remit"
        ),
        types.InlineKeyboardButton(
            "💰 Route Prices", callback_data="adm:prices"
        ),
        types.InlineKeyboardButton(
            "🚐 Drivers", callback_data="adm:drivers"
        ),
    )
    return mk


def admin_approval_keyboard(req_id: int) -> types.InlineKeyboardMarkup:
    """Return Approve / Reject buttons for a pending driver registration request.

    Args:
        req_id: DB primary key of the driver registration / approval request.

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: apv:{req_id}  (approve)
                         arj:{req_id}  (reject)
    """
    mk = types.InlineKeyboardMarkup(row_width=2)
    rid = str(req_id)
    mk.add(
        types.InlineKeyboardButton("Approve", callback_data="apv:" + rid),
        types.InlineKeyboardButton("Reject",  callback_data="arj:" + rid),
    )
    return mk


def route_prices_keyboard() -> types.InlineKeyboardMarkup:
    """Return the route-price management sub-menu.

    Two actions: create a new route price or browse/edit existing ones.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            rp:add  -- start add-route-price wizard
            rp:edit -- list existing prices for editing/deletion
    """
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(
        types.InlineKeyboardButton("➕ Add Route Price",  callback_data="rp:add"),
        types.InlineKeyboardButton("✏️ Edit / Delete",    callback_data="rp:edit"),
    )
    return mk


def route_price_list_keyboard(prices: list) -> types.InlineKeyboardMarkup:
    """Return a scrollable list of configured route prices.

    Each button summarises the route and its current price so the admin
    can select one to edit or delete. A Back button returns to the
    route-price sub-menu.

    Args:
        prices: List of dicts with keys: id, loc_a_name, loc_b_name, price.
                'price' is an integer amount in Naira.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback format: rp:sel:{price_id}
        Back button:     adm:prices
    """
    mk = types.InlineKeyboardMarkup(row_width=1)

    for p in prices:
        # Format price with thousands separator, e.g. 1,500
        price_str = "{:,}".format(p["price"])
        label = p["loc_a_name"] + " <-> " + p["loc_b_name"] + " -- N" + price_str
        mk.add(
            types.InlineKeyboardButton(
                label, callback_data="rp:sel:" + str(p["id"])
            )
        )

    mk.add(types.InlineKeyboardButton("⬅️ Back", callback_data="adm:prices"))
    return mk


def route_price_action_keyboard(
    price_id: int,
    price_amount: int,
) -> types.InlineKeyboardMarkup:
    """Return action buttons for a selected route price entry.

    Three actions are available: change the price, delete the override so
    the system falls back to the default fare, or go back to the list.

    Args:
        price_id:     DB primary key of the route_price record.
        price_amount: Current price in Naira (unused in callbacks but kept
                      for callers that may want to display it).

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            rp:chg:{price_id} -- edit price amount
            rp:del:{price_id} -- delete this override
            rp:edit           -- back to the price list
    """
    mk = types.InlineKeyboardMarkup(row_width=1)
    pid = str(price_id)
    mk.add(
        types.InlineKeyboardButton(
            "✏️ Change Price", callback_data="rp:chg:" + pid
        ),
        types.InlineKeyboardButton(
            "🗑️ Delete (use default)", callback_data="rp:del:" + pid
        ),
        types.InlineKeyboardButton("⬅️ Back", callback_data="rp:edit"),
    )
    return mk


def remittance_driver_keyboard(
    driver_id: int,
    amount: int,
) -> types.InlineKeyboardMarkup:
    """Return Mark-Collected / Back buttons for a driver cash remittance entry.

    The amount is embedded in the callback so the handler can log the
    exact figure that was confirmed without relying on session state.

    Args:
        driver_id: DB primary key of the driver / user record.
        amount:    Outstanding cash amount in Naira to be collected.

    Returns:
        InlineKeyboardMarkup (row_width=1).
        Callback formats:
            rem:collect:{driver_id}:{amount} -- mark cash as collected
            adm:remit                        -- back to remittance list
    """
    mk = types.InlineKeyboardMarkup(row_width=1)

    amount_str = "{:,}".format(amount)
    collect_label = "Mark N" + amount_str + " Collected"
    collect_cb = "rem:collect:" + str(driver_id) + ":" + str(amount)

    mk.add(
        types.InlineKeyboardButton(collect_label, callback_data=collect_cb),
        types.InlineKeyboardButton("⬅️ Back",        callback_data="adm:remit"),
    )
    return mk


def location_select_keyboard(
    locations: list,
    prefix: str,
    extra: int = None,
) -> types.InlineKeyboardMarkup:
    """Return a generic campus-location grid for admin route-price wizards.

    Used when the admin is picking Location A and then Location B while
    creating or editing a route price. Pass the already-chosen location's
    ID as 'extra' when building the second picker to avoid duplicates.

    Args:
        locations: List of location dicts with 'id' and 'name' keys.
        prefix:    Callback prefix string. Each location button fires
                   '{prefix}:{location_id}'.
        extra:     Optional location ID to exclude from the list
                   (e.g. the already-chosen Location A when picking B).

    Returns:
        InlineKeyboardMarkup (row_width=2).
        Callback format: {prefix}:{location_id}
        Cancel button:   {prefix}:cancel
    """
    mk = types.InlineKeyboardMarkup(row_width=2)

    # Build exclusion set -- may be empty if extra is None
    excluded = {extra} if extra is not None else set()

    buttons = [
        types.InlineKeyboardButton(
            loc["name"],
            callback_data=prefix + ":" + str(loc["id"]),
        )
        for loc in locations
        if loc["id"] not in excluded
    ]
    mk.add(*buttons)

    # Cancel always exits back without making a selection
    mk.add(
        types.InlineKeyboardButton(
            "Cancel", callback_data=prefix + ":cancel"
        )
    )
    return mk

