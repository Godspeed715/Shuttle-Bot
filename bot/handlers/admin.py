"""
bot/handlers/admin.py — Admin panel, route price management, and cash remittances.

Handles:
  /admin                        — Admin dashboard
  adm:remit                     — View cash remittance ledger
  adm:prices                    — Route prices menu
  adm:drivers                   — View drivers list
  rem:view:{driver_id}          — View a specific driver's remittance details
  rem:collect:{driver_id}:{amt} — Mark commission collected from driver
  rp:add                        — Add new route price wizard (step 1: pick loc A)
  rpa:{loc_a_id}                — Loc A chosen (step 2: pick loc B)
  rpb:{loc_b_id}                — Loc B chosen (step 3: enter price via text)
  rp:edit                       — List custom route prices
  rp:sel:{price_id}             — Route price selected
  rp:chg:{price_id}             — Change price
  rp:del:{price_id}             — Delete route override
  Text FSM states:
    waiting_for_route_price
    waiting_for_route_price_change
"""
import logging

from config import DEFAULT_FARE_NAIRA, PLATFORM_CUT_PCT
from functions import db
from bot.keyboards.admin import (
    admin_panel_keyboard, route_prices_keyboard,
    route_price_list_keyboard, route_price_action_keyboard,
    remittance_driver_keyboard, location_select_keyboard,
)
from telebot import types

logger = logging.getLogger(__name__)


def register(bot, get_conn, admin_ids):
    """Register all admin panel handlers with the bot."""

    def _is_admin(user_id):
        return user_id in admin_ids

    # ── /admin command ────────────────────────────────────────────────────────
    @bot.message_handler(commands=['admin'])
    def cmd_admin(message):
        if not _is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Not authorized. This command is for bot admins.")
            return

        bot.send_message(message.chat.id,
            "👑 *Campus Shuttle — Admin Panel*\n\n"
            "Select an administrative task below:",
            parse_mode='Markdown',
            reply_markup=admin_panel_keyboard())

    # ── Admin Panel Navigation ────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'adm:remit')
    def cb_admin_remit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        conn = get_conn()
        debtors = db.get_drivers_with_debt(conn)

        if not debtors:
            bot.edit_message_text(
                "📊 *Cash Remittance Ledger*\n\n"
                "✅ *All drivers are settled!*\n"
                "There are no outstanding cash commissions owed to the platform.",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown',
                reply_markup=admin_panel_keyboard())
            bot.answer_callback_query(call.id)
            return

        total_debt = sum(d['commission_owed'] for d in debtors)
        text = (f"📊 *Cash Remittances Due*\n\n"
                f"Total Platform Commission Outstanding: *₦{total_debt:,}*\n"
                f"Drivers owing: *{len(debtors)}*\n\n"
                f"Select a driver below to mark their cash remittance collected:")

        mk = types.InlineKeyboardMarkup(row_width=1)
        for d in debtors:
            mk.add(types.InlineKeyboardButton(
                f"👤 {d['full_name']} — ₦{d['commission_owed']:,}",
                callback_data=f"rem:view:{d['driver_id']}"
            ))
        mk.add(types.InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm:back"))

        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown', reply_markup=mk)
        bot.answer_callback_query(call.id)

    # ── View specific driver's remittance ─────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rem:view:'))
    def cb_remit_view_driver(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        driver_id = int(call.data.split(':')[2])
        conn = get_conn()
        wallet = db.get_wallet(conn, driver_id)
        driver_user = db.get_user(conn, wallet['driver_id']) if wallet else None

        if not wallet or wallet['commission_owed'] <= 0:
            bot.edit_message_text(
                "✅ This driver has no outstanding cash commission.",
                call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        amount = wallet['commission_owed']
        bot.edit_message_text(
            f"👤 *Driver Remittance Details*\n\n"
            f"Driver: *{driver_user['full_name'] if driver_user else 'Unknown'}*\n"
            f"Outstanding Cash Commission: *₦{amount:,}*\n"
            f"Lifetime Driver Earnings: *₦{wallet['total_earned']:,}*\n\n"
            "Did the driver hand over the cash or transfer it to you?",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=remittance_driver_keyboard(driver_id, amount))
        bot.answer_callback_query(call.id)

    # ── Collect Remittance ────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rem:collect:'))
    def cb_remit_collect(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        parts = call.data.split(':')
        driver_id = int(parts[2])
        amount = int(parts[3])
        conn = get_conn()

        db.settle_commission_debt(conn, driver_id, amount)

        # Notify driver
        try:
            driver_user = db.get_user(conn, driver_id)
            if driver_user:
                bot.send_message(
                    driver_user['telegram_id'],
                    f"✅ *Remittance Settled*\n\n"
                    f"The platform admin has marked *₦{amount:,}* cash commission as collected.\n"
                    "Thank you!",
                    parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to notify driver {driver_id} of settled remittance: {e}")

        bot.edit_message_text(
            f"✅ *Remittance Recorded!*\n\n"
            f"Successfully marked *₦{amount:,}* collected from driver.",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=admin_panel_keyboard())
        bot.answer_callback_query(call.id, "Settled ✅")

    # ── Route Prices Menu ─────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'adm:prices')
    def cb_admin_prices(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        conn = get_conn()
        all_prices = db.get_all_route_prices(conn)

        text = (f"💰 *Route Pricing Management*\n\n"
                f"Default Fare: *₦{DEFAULT_FARE_NAIRA:,}* per passenger\n"
                f"Platform Cut: *{int(PLATFORM_CUT_PCT * 100)}%*\n\n"
                f"Custom Configured Routes: *{len(all_prices)}*\n"
                "*(All custom routes apply both directions automatically)*\n\n"
                "What would you like to do?")

        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=route_prices_keyboard())
        bot.answer_callback_query(call.id)

    # ── Add Route Price — Step 1: Pick Loc A ───────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'rp:add')
    def cb_rp_add_step1(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        conn = get_conn()
        locations = db.get_locations(conn)

        bot.edit_message_text(
            "➕ *Add Custom Route Price (Step 1/2)*\n\n"
            "Select the *first location* of the route pair:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=location_select_keyboard(locations, 'rpa'))
        bot.answer_callback_query(call.id)

    # ── Add Route Price — Step 2: Pick Loc B ───────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rpa:'))
    def cb_rp_add_step2(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        val = call.data.split(':')[1]
        if val == 'cancel':
            cb_admin_prices(call)
            return

        loc_a_id = int(val)
        conn = get_conn()
        locations = db.get_locations(conn)
        loc_a = db.get_location(conn, loc_a_id)

        bot.edit_message_text(
            f"➕ *Add Custom Route Price (Step 2/2)*\n\n"
            f"Location A: *{loc_a['name']}*\n\n"
            f"Now select the *second location* of the pair:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=location_select_keyboard(locations, f"rpb:{loc_a_id}", extra=loc_a_id))
        bot.answer_callback_query(call.id)

    # ── Add Route Price — Step 3: Prompt for Price in Naira ────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rpb:'))
    def cb_rp_add_step3(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        parts = call.data.split(':')
        if parts[2] == 'cancel':
            cb_admin_prices(call)
            return

        loc_a_id = int(parts[1])
        loc_b_id = int(parts[2])

        conn = get_conn()
        loc_a = db.get_location(conn, loc_a_id)
        loc_b = db.get_location(conn, loc_b_id)

        db.set_state(conn, call.from_user.id, 'waiting_for_route_price', {
            'loc_a_id': loc_a_id,
            'loc_b_id': loc_b_id,
            'loc_a_name': loc_a['name'],
            'loc_b_name': loc_b['name'],
        })

        bot.edit_message_text(
            f"💰 *Set Route Price*\n\n"
            f"Route: *{loc_a['name']} ↔ {loc_b['name']}*\n\n"
            "Please enter the price in ₦ per passenger (e.g. *350*):\n"
            "*(This price will apply in both directions)*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Edit/Delete Route Prices List ─────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'rp:edit')
    def cb_rp_edit_list(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        conn = get_conn()
        prices = db.get_all_route_prices(conn)

        if not prices:
            bot.edit_message_text(
                "💰 *Route Prices*\n\n"
                "No custom route prices have been defined yet.\n"
                f"All routes currently use the default fare of *₦{DEFAULT_FARE_NAIRA:,}*.",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown',
                reply_markup=route_prices_keyboard())
            bot.answer_callback_query(call.id)
            return

        bot.edit_message_text(
            "✏️ *Select a route to change or delete:*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=route_price_list_keyboard(prices))
        bot.answer_callback_query(call.id)

    # ── Select specific Route Price ───────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rp:sel:'))
    def cb_rp_select_price(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        price_id = int(call.data.split(':')[2])
        conn = get_conn()
        prices = db.get_all_route_prices(conn)
        target = next((p for p in prices if p['id'] == price_id), None)

        if not target:
            bot.answer_callback_query(call.id, "⚠️ Route price not found.")
            cb_rp_edit_list(call)
            return

        bot.edit_message_text(
            f"📍 *Route:* {target['loc_a_name']} ↔ {target['loc_b_name']}\n"
            f"💰 *Current Price:* ₦{target['price']:,} per passenger\n\n"
            "Choose an action:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=route_price_action_keyboard(price_id, target['price']))
        bot.answer_callback_query(call.id)

    # ── Change Route Price Action ─────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rp:chg:'))
    def cb_rp_change_price(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        price_id = int(call.data.split(':')[2])
        conn = get_conn()
        prices = db.get_all_route_prices(conn)
        target = next((p for p in prices if p['id'] == price_id), None)

        if not target:
            bot.answer_callback_query(call.id, "⚠️ Route not found.")
            cb_rp_edit_list(call)
            return

        db.set_state(conn, call.from_user.id, 'waiting_for_route_price_change', {
            'price_id': price_id,
            'route_name': f"{target['loc_a_name']} ↔ {target['loc_b_name']}",
        })

        bot.edit_message_text(
            f"✏️ *Change Route Price*\n\n"
            f"Route: *{target['loc_a_name']} ↔ {target['loc_b_name']}*\n"
            f"Current: ₦{target['price']:,}\n\n"
            "Please enter the new price in ₦:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Delete Route Price Action ─────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rp:del:'))
    def cb_rp_delete_price(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        price_id = int(call.data.split(':')[2])
        conn = get_conn()
        db.delete_route_price(conn, price_id)

        bot.edit_message_text(
            "🗑️ *Route Price Deleted*\n\n"
            f"This route has been removed and will now use the default fare (₦{DEFAULT_FARE_NAIRA:,}).",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=route_prices_keyboard())
        bot.answer_callback_query(call.id, "Deleted")

    # ── Drivers List ──────────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'adm:drivers')
    def cb_admin_drivers(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute('''
                SELECT u.full_name, u.telegram_id, s.name AS shuttle_name,
                       s.vehicle_type, s.is_available, w.balance, w.commission_owed
                FROM users u
                JOIN shuttles s ON s.driver_id = u.id
                LEFT JOIN driver_wallets w ON w.driver_id = u.id
                WHERE u.role = 'driver' AND u.is_approved = TRUE
                ORDER BY u.full_name
            ''')
            drivers = cur.fetchall()

        if not drivers:
            text = "🚐 *Approved Drivers*\n\nNo approved drivers found."
        else:
            text = f"🚐 *Approved Drivers ({len(drivers)})*\n\n"
            for d in drivers:
                status = "🟢 Online" if d['is_available'] else "🔴 Offline"
                vtype = "Siena (7 seats)" if d.get('vehicle_type') == 'siena' else "Car (4 seats)"
                bal = d.get('balance', 0) or 0
                owed = d.get('commission_owed', 0) or 0
                text += (f"• *{d['full_name']}* ({d['shuttle_name']})\n"
                         f"  Vehicle: {vtype} | {status}\n"
                         f"  Wallet: ₦{bal:,} | Remittance Owed: ₦{owed:,}\n\n")

        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm:back"))

        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown', reply_markup=mk)
        bot.answer_callback_query(call.id)

    # ── Back to Admin Panel ───────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'adm:back')
    def cb_admin_back(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        bot.edit_message_text(
            "👑 *Campus Shuttle — Admin Panel*\n\nSelect an administrative task below:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=admin_panel_keyboard())
        bot.answer_callback_query(call.id)


def handle_admin_text_fsm(bot, get_conn, message):
    """
    Handle text FSM states for route price creation and modification.
    Called by the main text router.
    Returns True if handled, False otherwise.
    """
    conn = get_conn()
    state = db.get_state(conn, message.from_user.id)
    if not state:
        return False

    state_name = state['state']
    data = state['data'] if isinstance(state['data'], dict) else {}

    # ── Setting new route price ──
    if state_name == 'waiting_for_route_price':
        text = message.text.strip().replace(",", "")
        if not text.isdigit() or int(text) <= 0:
            bot.send_message(message.chat.id, "❌ Please enter a valid price in ₦ (positive whole number):")
            return True

        price = int(text)
        loc_a_id = data['loc_a_id']
        loc_b_id = data['loc_b_id']
        loc_a_name = data.get('loc_a_name', 'Location A')
        loc_b_name = data.get('loc_b_name', 'Location B')

        db.set_route_price(conn, loc_a_id, loc_b_id, price)
        db.clear_state(conn, message.from_user.id)

        bot.send_message(message.chat.id,
            f"✅ *Route Price Saved!*\n\n"
            f"📍 Route: *{loc_a_name} ↔ {loc_b_name}*\n"
            f"💰 Price: *₦{price:,}* per passenger\n\n"
            "This price will automatically apply in both directions for all future bookings.",
            parse_mode='Markdown',
            reply_markup=admin_panel_keyboard())
        return True

    # ── Changing existing route price ──
    if state_name == 'waiting_for_route_price_change':
        text = message.text.strip().replace(",", "")
        if not text.isdigit() or int(text) <= 0:
            bot.send_message(message.chat.id, "❌ Please enter a valid price in ₦ (positive whole number):")
            return True

        price = int(text)
        price_id = data['price_id']
        route_name = data.get('route_name', 'Route')

        with conn.cursor() as cur:
            cur.execute(
                'UPDATE route_prices SET price = %s, updated_at = NOW() WHERE id = %s RETURNING *',
                (price, price_id)
            )

        db.clear_state(conn, message.from_user.id)
        bot.send_message(message.chat.id,
            f"✅ *Route Price Updated!*\n\n"
            f"📍 Route: *{route_name}*\n"
            f"💰 New Price: *₦{price:,}* per passenger",
            parse_mode='Markdown',
            reply_markup=admin_panel_keyboard())
        return True

    return False
