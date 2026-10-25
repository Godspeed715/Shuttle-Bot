"""
bot/handlers/student.py — Student booking and ride management.

Handles:
  /book        — 5-step booking flow
  /cancel      — Cancel active ride
  /mystatus    — Check current ride status
  pk:*         — Pickup location selected
  dst:*        — Destination selected
  pax:*        — Passenger count selected
  pay:*        — Payment method selected
  drv:*        — Shuttle/driver selected
  cnly:*, cnln:* — Cancel confirm/deny
"""
import logging
import datetime
import secrets

from functions import db
from functions.pricing import get_unit_price, calculate_fare, format_fare_summary
from bot.keyboards.student import (
    pickup_keyboard, destination_keyboard,
    passenger_count_keyboard, payment_method_keyboard,
    drivers_keyboard, cancel_confirm_keyboard,
)

logger = logging.getLogger(__name__)


def _booking_id():
    return 'CU-' + secrets.token_hex(3).upper()


def register(bot, get_conn, booking_id_fn, admin_ids, timeout_sec):
    """Wire all student handlers to the bot instance."""

    # ── /book ─────────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['book'])
    def cmd_book(message):
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)

        if not user or user['role'] != 'student':
            bot.send_message(message.chat.id,
                "❌ Only registered students can book rides. Use /start to register.")
            return

        if db.get_active_ride_for_student(conn, user['id']):
            bot.send_message(message.chat.id,
                "⚠️ You already have an active ride.\n"
                "Use /cancel to cancel it first, or /mystatus to check it.")
            return

        locations = db.get_locations(conn)
        if not locations:
            bot.send_message(message.chat.id, "❌ No locations available right now.")
            return

        bot.send_message(message.chat.id,
            "📍 *Step 1 of 4 — Select your pickup location:*",
            parse_mode='Markdown',
            reply_markup=pickup_keyboard(locations))

    # ── Step 1 → 2: Pickup selected ───────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('pk:'))
    def cb_pickup(call):
        pickup_id = int(call.data.split(':')[1])
        conn = get_conn()
        locations = db.get_locations(conn)

        bot.edit_message_text(
            "📍 *Step 2 of 4 — Select your destination:*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=destination_keyboard(locations, pickup_id, exclude_id=pickup_id))
        bot.answer_callback_query(call.id)

    # ── Step 2 → 3: Destination selected ─────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('dst:'))
    def cb_destination(call):
        parts = call.data.split(':')
        pickup_id, dest_id = int(parts[1]), int(parts[2])

        conn = get_conn()
        shuttles = db.get_available_shuttles(conn)

        # Determine shuttle vehicle type for capacity hint
        # Use the most common capacity (car=4) as default if mixed fleet
        vehicle_type = 'car'
        if shuttles:
            # If any siena is available, show siena capacity
            for s in shuttles:
                if s.get('vehicle_type') == 'siena':
                    vehicle_type = 'siena'
                    break

        bot.edit_message_text(
            "👥 *Step 3 of 4 — How many people are booking?*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=passenger_count_keyboard(pickup_id, dest_id, vehicle_type))
        bot.answer_callback_query(call.id)

    # ── Step 3a: "More" tapped — ask user to type a number ───────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('pax:') and c.data.endswith(':more'))
    def cb_pax_more(call):
        parts = call.data.split(':')
        pickup_id, dest_id = parts[1], parts[2]
        conn = get_conn()
        db.set_state(conn, call.from_user.id, 'waiting_for_pax_count',
                     {'pickup_id': pickup_id, 'dest_id': dest_id,
                      'msg_id': call.message.message_id})
        bot.edit_message_text(
            "👥 *How many passengers?*\n\nPlease type the number of passengers:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Step 3 → 4: Passenger count selected ─────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('pax:') and not c.data.endswith(':more'))
    def cb_pax(call):
        parts = call.data.split(':')
        pickup_id, dest_id, pax = int(parts[1]), int(parts[2]), int(parts[3])
        conn = get_conn()

        unit_price = get_unit_price(conn, pickup_id, dest_id)
        fare = calculate_fare(unit_price, pax)
        summary = format_fare_summary(fare)

        bot.edit_message_text(
            f"{summary}\n\n"
            "💳 *Step 4 of 4 — Choose payment method:*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=payment_method_keyboard(pickup_id, dest_id, pax))
        bot.answer_callback_query(call.id)

    # ── Step 4 → 5: Payment method selected ──────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('pay:'))
    def cb_payment(call):
        parts = call.data.split(':')
        pickup_id, dest_id, pax = int(parts[1]), int(parts[2]), int(parts[3])
        payment_method = parts[4]   # 'cash' or 'transfer'
        conn = get_conn()

        shuttles = db.get_available_shuttles(conn)
        if not shuttles:
            bot.edit_message_text(
                "😔 *No shuttles available right now.*\n\nPlease try again later with /book.",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown')
            bot.answer_callback_query(call.id)
            return

        method_emoji = '💵 Cash' if payment_method == 'cash' else '💳 Transfer'
        bot.edit_message_text(
            f"💳 Payment: {method_emoji}\n\n"
            "🚐 *Select a shuttle:*",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=drivers_keyboard(shuttles, pickup_id, dest_id, pax, payment_method))
        bot.answer_callback_query(call.id)

    # ── Step 5: Driver/shuttle selected — create ride ─────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('drv:'))
    def cb_select_driver(call):
        parts = call.data.split(':')
        if parts[4] == 'cancel':
            bot.edit_message_text("❌ Booking cancelled.",
                                  call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        pickup_id   = int(parts[1])
        dest_id     = int(parts[2])
        pax         = int(parts[3])
        shuttle_id  = int(parts[4])
        payment_method = parts[5]   # 'cash' or 'transfer'

        conn = get_conn()
        user = db.get_user(conn, call.from_user.id)
        if not user:
            bot.answer_callback_query(call.id, "❌ Not registered.")
            return

        if db.get_active_ride_for_student(conn, user['id']):
            bot.edit_message_text("⚠️ You already have an active ride.",
                                  call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        shuttles = db.get_available_shuttles(conn)
        shuttle = next((s for s in shuttles if s['id'] == shuttle_id), None)
        if not shuttle:
            bot.edit_message_text(
                "😔 This shuttle is no longer available. Try /book again.",
                call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        pickup = db.get_location(conn, pickup_id)
        dest   = db.get_location(conn, dest_id)

        # Calculate fare
        unit_price = get_unit_price(conn, pickup_id, dest_id)
        fare = calculate_fare(unit_price, pax)

        bid     = booking_id_fn()
        expires = (datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(seconds=timeout_sec))

        # Create ride record
        ride = db.create_ride(conn, bid, user['id'], shuttle['driver_id'],
                              shuttle_id, pickup_id, dest_id, expires)

        # Store fare and payment method
        db.update_ride_fare(
            conn, ride['id'], pax,
            fare['total'], fare['platform_cut'], fare['driver_earnings'],
            payment_method
        )

        pax_label  = f"{pax} passenger{'s' if pax > 1 else ''}"
        method_emoji = '💵 Cash on arrival' if payment_method == 'cash' else '💳 Online Transfer'

        if payment_method == 'transfer':
            # ── Online payment: initialise Paystack and await webhook ──────────
            _handle_transfer_booking(
                bot, conn, ride, bid, user, shuttle, pickup, dest,
                fare, pax_label, call
            )
        else:
            # ── Cash: send request directly to driver ─────────────────────────
            driver_msg = bot.send_message(
                shuttle['driver_telegram_id'],
                f"🔔 *New Ride Request!*\n\n"
                f"👤 Passenger: {user['full_name']}\n"
                f"📍 From: {pickup['name']}\n"
                f"📍 To: {dest['name']}\n"
                f"👥 Passengers: {pax_label}\n"
                f"💰 Fare: ₦{fare['total']:,} ({method_emoji})\n\n"
                f"⏱ You have 5 minutes to respond.",
                parse_mode='Markdown',
                reply_markup=_ride_response_kb(ride['id']))
            db.save_driver_msg_id(conn, ride['id'], driver_msg.message_id)

            bot.edit_message_text(
                f"⏳ *Ride Request Sent!*\n\n"
                f"🎫 Booking: `{bid}`\n"
                f"📍 From: {pickup['name']}\n"
                f"📍 To: {dest['name']}\n"
                f"👥 {pax_label}\n"
                f"💰 Fare: ₦{fare['total']:,} ({method_emoji})\n"
                f"🚐 Shuttle: {shuttle['name']}\n"
                f"👤 Driver: {shuttle['driver_name']}\n\n"
                f"⏱ Waiting for driver to respond (5 min)...",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown')
            bot.answer_callback_query(call.id)

    # Wire status and cancel sub-handlers
    register_status(bot, get_conn)
    register_cancel(bot, get_conn)
def _handle_transfer_booking(bot, conn, ride, bid, user, shuttle,
                              pickup, dest, fare, pax_label, call):
    """Initialise a Paystack payment for a transfer booking."""
    try:
        from functions.paystack import initialize_payment
        ref = f"SHT-{bid}"
        email = f"{user['telegram_id']}@shuttlebot.cu.edu.ng"

        result = initialize_payment(
            email=email,
            amount_naira=fare['total'],
            metadata={
                'ride_id': ride['id'],
                'booking_id': bid,
                'student_telegram_id': user['telegram_id'],
                'driver_telegram_id': shuttle['driver_telegram_id'],
            },
            channels=['bank_transfer'],
        )

        # Store Paystack reference on the ride
        db.update_ride_payment_status(conn, ride['id'], 'pending', paystack_ref=ref)

        bot.edit_message_text(
            f"💳 *Transfer Payment*\n\n"
            f"🎫 Booking: `{bid}`\n"
            f"📍 {pickup['name']} → {dest['name']}\n"
            f"👥 {pax_label}\n\n"
            f"💰 *Amount to pay: ₦{fare['total']:,}*\n\n"
            "Tap the link below to complete your payment.\n"
            "Your ride will be confirmed automatically once payment is received:\n\n"
            f"🔗 {result['authorization_url']}",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    except Exception as e:
        logger.error(f"Paystack init failed for ride {ride['id']}: {e}", exc_info=True)
        # Paystack not configured yet — fall back gracefully
        bot.edit_message_text(
            f"⏳ *Ride Request Sent!*\n\n"
            f"🎫 Booking: `{bid}`\n"
            f"📍 {pickup['name']} → {dest['name']}\n"
            f"👥 {pax_label}\n"
            f"💰 Fare: ₦{fare['total']:,}\n\n"
            "⚠️ Online payment is not yet available. Please pay cash to the driver.",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        # Fall back to cash flow — notify driver
        from bot.keyboards.driver import ride_response_keyboard
        driver_msg = bot.send_message(
            shuttle['driver_telegram_id'],
            f"🔔 *New Ride Request (Cash)*\n\n"
            f"👤 {user['full_name']}\n"
            f"📍 {pickup['name']} → {dest['name']}\n"
            f"👥 {pax_label} | 💰 ₦{fare['total']:,}\n\n"
            "⏱ 5 minutes to respond.",
            parse_mode='Markdown',
            reply_markup=ride_response_keyboard(ride['id']))
        db.save_driver_msg_id(conn, ride['id'], driver_msg.message_id)


def _ride_response_kb(ride_id):
    """Inline keyboard for driver accept/reject."""
    from bot.keyboards.driver import ride_response_keyboard
    return ride_response_keyboard(ride_id)


    # ── /mystatus ─────────────────────────────────────────────────────────────
def register_status(bot, get_conn):
    @bot.message_handler(commands=['mystatus'])
    def cmd_status(message):
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start to register first.")
            return

        ride = db.get_active_ride_for_student(conn, user['id'])
        if not ride:
            bot.send_message(message.chat.id,
                "ℹ️ You have no active ride right now. Use /book to request one.")
            return

        status_emoji = {'pending': '⏳', 'accepted': '✅'}.get(ride['status'], '❓')
        pax = ride.get('passenger_count', 1)
        fare = ride.get('fare_amount')
        fare_line = f"\n💰 Fare: ₦{fare:,}" if fare else ''
        method = ride.get('payment_method', '')
        method_line = f"\n💳 Payment: {'💵 Cash' if method == 'cash' else '💳 Transfer'}" if method else ''
        pay_status = ride.get('payment_status', 'unpaid')
        pay_status_line = f"\n✅ Paid" if pay_status == 'paid' else ('\n⏳ Payment pending' if pay_status == 'pending' else '')

        bot.send_message(message.chat.id,
            f"📊 *Your Current Ride*\n\n"
            f"🎫 Booking: `{ride['booking_id']}`\n"
            f"📍 From: {ride['pickup_name']}\n"
            f"📍 To: {ride['dest_name']}\n"
            f"👥 Passengers: {pax}\n"
            f"🚐 Shuttle: {ride['shuttle_name']}\n"
            f"👤 Driver: {ride['driver_name']}"
            f"{fare_line}{method_line}{pay_status_line}\n"
            f"{status_emoji} Status: {ride['status'].title()}",
            parse_mode='Markdown')


def register_cancel(bot, get_conn):
    # ── /cancel ───────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['cancel'])
    def cmd_cancel(message):
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Use /start to register first.")
            return

        ride = db.get_active_ride_for_student(conn, user['id'])
        if not ride:
            bot.send_message(message.chat.id, "ℹ️ You have no active ride to cancel.")
            return

        bot.send_message(message.chat.id,
            f"Are you sure you want to cancel your ride?\n\n"
            f"📍 {ride['pickup_name']} → {ride['dest_name']}\n"
            f"🚐 {ride['shuttle_name']}",
            reply_markup=cancel_confirm_keyboard(ride['id']))

    @bot.callback_query_handler(func=lambda c: c.data.startswith('cnly:'))
    def cb_cancel_yes(call):
        ride_id = int(call.data.split(':')[1])
        conn = get_conn()
        ride = db.get_ride(conn, ride_id)

        if not ride or ride['status'] not in ('pending', 'accepted'):
            bot.edit_message_text("ℹ️ This ride is no longer active.",
                                  call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        db.update_ride_status(conn, ride_id, 'cancelled')
        bot.edit_message_text("✅ *Ride Cancelled*\n\nUse /book to request a new ride.",
                              call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown')

        if ride.get('driver_msg_id'):
            try:
                bot.edit_message_reply_markup(
                    ride['driver_telegram_id'], ride['driver_msg_id'], reply_markup=None)
            except Exception:
                pass

        bot.send_message(ride['driver_telegram_id'],
            f"⚠️ *Ride Cancelled*\n\n"
            f"Passenger {ride['student_name']} has cancelled their ride.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('cnln:'))
    def cb_cancel_no(call):
        bot.edit_message_text("👍 Your ride is still active.",
                              call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)


def handle_student_text_fsm(bot, get_conn, message):
    """
    Handle FSM text states for student booking (e.g. typing custom passenger count).
    Called by main text router.
    Returns True if handled, False otherwise.
    """
    conn = get_conn()
    state = db.get_state(conn, message.from_user.id)
    if not state:
        return False

    state_name = state['state']
    data = state['data'] if isinstance(state['data'], dict) else {}

    if state_name == 'waiting_for_pax_count':
        text = message.text.strip()
        if not text.isdigit() or int(text) < 1:
            bot.send_message(message.chat.id, "❌ Please enter a valid number of passengers (at least 1):")
            return True

        pax = int(text)
        pickup_id = int(data['pickup_id'])
        dest_id = int(data['dest_id'])

        unit_price = get_unit_price(conn, pickup_id, dest_id)
        fare = calculate_fare(unit_price, pax)
        summary = format_fare_summary(fare)

        db.clear_state(conn, message.from_user.id)
        bot.send_message(
            message.chat.id,
            f"{summary}\n\n"
            "💳 *Step 4 of 4 — Choose payment method:*",
            parse_mode='Markdown',
            reply_markup=payment_method_keyboard(pickup_id, dest_id, pax))
        return True

    return False
