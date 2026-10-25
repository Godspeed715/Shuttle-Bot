"""
bot/handlers/driver.py — Driver dashboard and trip lifecycle.

Handles:
  /driver       — Driver dashboard
  acc:*         — Accept ride request
  rej:*         — Reject ride request
  sht:*         — Dashboard button actions (on/off/loc/cmp/pax/wallet)
  sloc:*        — Set shuttle location
  apv:*, arj:*  — Admin approves/rejects driver (delegated from admin.py)
  bnk:*         — Bank account selection during onboarding FSM
"""
import logging
import datetime

from functions import db
from bot.keyboards.driver import (
    driver_dashboard_keyboard, location_update_keyboard,
    ride_response_keyboard, wallet_keyboard, bank_list_keyboard,
)
from bot.keyboards.admin import admin_approval_keyboard

logger = logging.getLogger(__name__)


def register(bot, get_conn, admin_ids):
    """Wire all driver handlers to the bot instance."""

    # ── /driver dashboard ─────────────────────────────────────────────────────
    @bot.message_handler(commands=['driver'])
    def cmd_driver(message):
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)

        if not user or user['role'] != 'driver':
            bot.send_message(message.chat.id,
                "❌ This command is for registered drivers only.")
            return
        if not user['is_approved']:
            bot.send_message(message.chat.id,
                "⏳ Your account is pending admin approval.")
            return

        _send_dashboard(bot, conn, message.chat.id, user['id'])

    # ── Driver: Accept ride ───────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('acc:'))
    def cb_accept(call):
        ride_id = int(call.data.split(':')[1])
        conn = get_conn()
        ride = db.get_ride(conn, ride_id)

        if not ride or ride['status'] != 'pending':
            bot.answer_callback_query(call.id, "⚠️ This request is no longer active.")
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None)
            return

        # Lazy expiry check
        if datetime.datetime.now(datetime.timezone.utc) >= ride['expires_at'].replace(
                tzinfo=datetime.timezone.utc):
            db.update_ride_status(conn, ride_id, 'expired')
            bot.edit_message_text("⏰ This request has expired.",
                                  call.message.chat.id, call.message.message_id)
            bot.send_message(ride['student_telegram_id'],
                "⏰ *Request Expired*\n\nThe driver did not respond in time. "
                "Use /book to try again.",
                parse_mode='Markdown')
            bot.answer_callback_query(call.id)
            return

        db.update_ride_status(conn, ride_id, 'accepted')

        pax = ride.get('passenger_count', 1)
        fare = ride.get('fare_amount')
        fare_line = f"\n💰 Fare: ₦{fare:,}" if fare else ''
        method = ride.get('payment_method', '')
        method_line = f"\n💳 {'Cash' if method == 'cash' else 'Transfer (online)'}" if method else ''

        bot.edit_message_text(
            f"✅ *Ride Accepted!*\n\n"
            f"👤 Passenger: {ride['student_name']}\n"
            f"📍 Pickup: {ride['pickup_name']}\n"
            f"📍 Destination: {ride['dest_name']}\n"
            f"👥 Passengers: {pax}"
            f"{fare_line}{method_line}\n\n"
            "Use /driver to complete the trip when done.",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')

        bot.send_message(ride['student_telegram_id'],
            f"✅ *Ride Confirmed!*\n\n"
            f"🎫 Booking: `{ride['booking_id']}`\n"
            f"📍 From: {ride['pickup_name']}\n"
            f"📍 To: {ride['dest_name']}\n"
            f"👥 Passengers: {pax}\n"
            f"🚐 Shuttle: {ride['shuttle_name']}\n"
            f"👤 Driver: {ride['driver_name']}"
            f"{fare_line}\n\n"
            "Your driver is on the way! Use /cancel to cancel if needed.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Driver: Reject ride ───────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('rej:'))
    def cb_reject(call):
        ride_id = int(call.data.split(':')[1])
        conn = get_conn()
        ride = db.get_ride(conn, ride_id)

        if not ride or ride['status'] != 'pending':
            bot.answer_callback_query(call.id, "⚠️ This request is no longer active.")
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None)
            return

        db.update_ride_status(conn, ride_id, 'rejected')
        bot.edit_message_text("❌ You declined this ride request.",
                              call.message.chat.id, call.message.message_id)
        bot.send_message(ride['student_telegram_id'],
            "❌ *Ride Declined*\n\nThe driver declined your request. "
            "Use /book to try another shuttle.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Dashboard button actions ──────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('sht:'))
    def cb_shuttle_action(call):
        parts  = call.data.split(':')
        action = parts[1]

        conn = get_conn()
        user = db.get_user(conn, call.from_user.id)
        if not user:
            bot.answer_callback_query(call.id, "❌ Not registered.")
            return

        shuttle = db.get_shuttle_by_driver(conn, user['id'])
        if not shuttle:
            bot.answer_callback_query(call.id, "❌ No shuttle linked to account.")
            return

        shuttle_id = shuttle['id']

        if action == 'on':
            db.set_shuttle_availability(conn, shuttle_id, True)
            bot.answer_callback_query(call.id, "✅ You are now Online!")
            _refresh_dashboard(bot, conn, call.message, user['id'])

        elif action == 'off':
            db.set_shuttle_availability(conn, shuttle_id, False)
            bot.answer_callback_query(call.id, "🔴 You are now Offline.")
            _refresh_dashboard(bot, conn, call.message, user['id'])

        elif action == 'loc':
            locations = db.get_locations(conn)
            bot.edit_message_text("📍 *Select your current location:*",
                                  call.message.chat.id, call.message.message_id,
                                  parse_mode='Markdown',
                                  reply_markup=location_update_keyboard(locations, shuttle_id))
            bot.answer_callback_query(call.id)

        elif action == 'cmp':
            ride = db.get_active_ride_for_driver(conn, user['id'])
            if ride and ride['status'] == 'accepted':
                db.update_ride_status(conn, ride['id'], 'completed')

                # Credit wallet / record commission debt depending on payment method
                payment_method = ride.get('payment_method', 'cash')
                driver_earnings = ride.get('driver_earnings', 0) or 0
                platform_cut = ride.get('platform_cut', 0) or 0

                wallet = db.get_or_create_wallet(conn, user['id'])

                if payment_method == 'transfer':
                    # Transfer rides: Paystack already holds funds.
                    # Credit driver's wallet with their earnings.
                    db.credit_wallet(conn, user['id'], driver_earnings,
                                     ride_id=ride['id'],
                                     note='Transfer ride payout')
                    wallet_msg = f"\n💰 ₦{driver_earnings:,} credited to your wallet."
                else:
                    # Cash rides: driver holds all cash; they owe platform its cut.
                    db.add_commission_debt(conn, user['id'], platform_cut,
                                          ride_id=ride['id'])
                    wallet_msg = (f"\n⚠️ ₦{platform_cut:,} platform commission recorded. "
                                  "Remit to admin when requested.")

                bot.send_message(ride['student_telegram_id'],
                    "🏁 *Trip Complete!*\n\nThanks for riding with us! "
                    "Use /book for another ride.",
                    parse_mode='Markdown')
                bot.answer_callback_query(call.id, "🏁 Trip marked complete!")
                _refresh_dashboard(bot, conn, call.message, user['id'],
                                   extra_note=wallet_msg)
            else:
                bot.answer_callback_query(call.id, "⚠️ No accepted ride to complete.")

        elif action == 'pax':
            ride = db.get_active_ride_for_driver(conn, user['id'])
            if ride:
                pax = ride.get('passenger_count', 1)
                bot.answer_callback_query(call.id,
                    f"👤 {ride['student_name']}\n"
                    f"👥 {pax} passenger(s)\n"
                    f"📍 {ride['pickup_name']} → {ride['dest_name']}",
                    show_alert=True)
            else:
                bot.answer_callback_query(call.id, "No active passenger.")

        elif action == 'wallet':
            # Redirect to wallet handler
            _show_wallet(bot, conn, call.message.chat.id, user)
            bot.answer_callback_query(call.id)

    # ── Set location callback ─────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('sloc:'))
    def cb_set_location(call):
        parts = call.data.split(':')
        shuttle_id = int(parts[1])

        if parts[2] == 'cancel':
            bot.edit_message_text("📍 Location update cancelled.",
                                  call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        location_id = int(parts[2])
        conn = get_conn()
        db.set_shuttle_location(conn, shuttle_id, location_id)
        loc = db.get_location(conn, location_id)

        bot.edit_message_text(
            f"✅ Location updated to *{loc['name']}*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id, f"📍 Now at {loc['name']}")

    # ── Admin approve/reject driver ────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('apv:'))
    def cb_approve_driver(call):
        if call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        req_id = int(call.data.split(':')[1])
        conn = get_conn()
        dreq = db.get_driver_request(conn, req_id)

        if not dreq or dreq['status'] != 'pending':
            bot.answer_callback_query(call.id, "⚠️ Already processed.")
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None)
            return

        db.update_driver_request_status(conn, req_id, 'approved')
        vtype = dreq.get('vehicle_type', 'car')
        user = db.create_user(conn, dreq['telegram_id'], dreq['username'],
                              dreq['full_name'], 'driver', is_approved=True)
        db.create_shuttle(conn, user['id'], dreq['shuttle_name'], vtype)
        # Auto-create wallet for the new driver
        db.get_or_create_wallet(conn, user['id'])

        cap = 4 if vtype == 'car' else 7
        bot.edit_message_text(
            f"✅ *Approved* {dreq['full_name']} ({dreq['shuttle_name']}, "
            f"{'Car' if vtype == 'car' else 'Siena'}, max {cap} pax)",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.send_message(dreq['telegram_id'],
            "✅ *Driver Approved!*\n\n"
            "You are now registered as a driver.\n"
            "Use /driver to manage your shuttle.\n"
            "Use /wallet to view your earnings and link your bank account.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id, "Approved ✅")

    @bot.callback_query_handler(func=lambda c: c.data.startswith('arj:'))
    def cb_reject_driver(call):
        if call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        req_id = int(call.data.split(':')[1])
        conn = get_conn()
        dreq = db.get_driver_request(conn, req_id)

        if not dreq or dreq['status'] != 'pending':
            bot.answer_callback_query(call.id, "⚠️ Already processed.")
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None)
            return

        db.update_driver_request_status(conn, req_id, 'rejected')
        bot.edit_message_text(
            f"❌ *Rejected* driver {dreq['full_name']}",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.send_message(dreq['telegram_id'],
            "❌ *Driver Request Rejected*\n\n"
            "Your driver registration has been rejected by an admin.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id, "Rejected ❌")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _send_dashboard(bot, conn, chat_id, driver_id, extra_note=''):
    """Send or refresh the driver dashboard to chat_id."""
    user = db.get_user(conn, driver_id) if isinstance(driver_id, int) else driver_id
    if isinstance(driver_id, int):
        user = next((u for u in [db.get_user(conn, driver_id)] if u), None)
    shuttle = db.get_shuttle_by_driver(conn, user['id'] if user else driver_id)
    active_ride = db.get_active_ride_for_driver(conn, user['id'] if user else driver_id)
    status = '🟢 Online' if shuttle['is_available'] else '🔴 Offline'

    text = f"🚐 *{shuttle['name']} Dashboard*\n\nStatus: {status}"
    if active_ride:
        pax = active_ride.get('passenger_count', 1)
        text += (f"\n\n📌 *Active Ride:*\n"
                 f"👤 Passenger: {active_ride['student_name']}\n"
                 f"👥 {pax} passenger(s)\n"
                 f"📍 {active_ride['pickup_name']} → {active_ride['dest_name']}\n"
                 f"Status: {active_ride['status'].title()}")
    if extra_note:
        text += f"\n\n{extra_note}"

    bot.send_message(chat_id, text, parse_mode='Markdown',
                     reply_markup=driver_dashboard_keyboard(
                         shuttle['id'], shuttle['is_available'],
                         active_ride is not None))


def _refresh_dashboard(bot, conn, message, driver_id, extra_note=''):
    """Edit the existing dashboard message in place."""
    user = db.get_user(conn, driver_id)
    shuttle = db.get_shuttle_by_driver(conn, user['id'])
    active_ride = db.get_active_ride_for_driver(conn, user['id'])
    status = '🟢 Online' if shuttle['is_available'] else '🔴 Offline'

    text = f"🚐 *{shuttle['name']} Dashboard*\n\nStatus: {status}"
    if active_ride:
        pax = active_ride.get('passenger_count', 1)
        text += (f"\n\n📌 *Active Ride:*\n"
                 f"👤 {active_ride['student_name']}\n"
                 f"👥 {pax} passenger(s)\n"
                 f"📍 {active_ride['pickup_name']} → {active_ride['dest_name']}\n"
                 f"Status: {active_ride['status'].title()}")
    if extra_note:
        text += f"\n\n{extra_note}"

    try:
        bot.edit_message_text(
            text, message.chat.id, message.message_id,
            parse_mode='Markdown',
            reply_markup=driver_dashboard_keyboard(
                shuttle['id'], shuttle['is_available'], active_ride is not None))
    except Exception:
        bot.send_message(message.chat.id, text, parse_mode='Markdown',
                         reply_markup=driver_dashboard_keyboard(
                             shuttle['id'], shuttle['is_available'],
                             active_ride is not None))


def _show_wallet(bot, conn, chat_id, user):
    """Show wallet summary inline (called from dashboard wallet button)."""
    wallet = db.get_or_create_wallet(conn, user['id'])
    balance = wallet['balance']
    owed = wallet['commission_owed']
    withdrawable = max(0, balance - owed)
    has_bank = bool(wallet.get('recipient_code'))

    bank_info = ''
    if has_bank:
        bank_info = (f"\n\n🏦 Bank: {wallet.get('bank_name', 'N/A')} — "
                     f"{wallet.get('account_number', '')}\n"
                     f"👤 {wallet.get('account_name', '')}")

    bot.send_message(chat_id,
        f"💰 *Your Wallet*\n\n"
        f"Available Balance: ₦{balance:,}\n"
        f"Total Earned: ₦{wallet['total_earned']:,}\n"
        f"Cash Commission Owed: ₦{owed:,}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"*Net Withdrawable: ₦{withdrawable:,}*"
        f"{bank_info}",
        parse_mode='Markdown',
        reply_markup=wallet_keyboard(
            has_bank=has_bank,
            can_withdraw=withdrawable > 0))
