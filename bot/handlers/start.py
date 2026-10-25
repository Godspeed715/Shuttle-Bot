"""
bot/handlers/start.py — Registration flow.

Handles:
  /start  — greet returning users or start registration
  role:*  — student/driver role selection callback
  vtype:* — vehicle type selection callback (car/siena)
  Text FSM states: waiting_for_name, waiting_for_shuttle_name
"""
import logging
from functions import db
from bot.keyboards.common import role_keyboard, vehicle_type_keyboard

logger = logging.getLogger(__name__)


def register(bot, get_conn):
    """Wire all start/registration handlers to the bot instance."""

    # ── /start ────────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        tid = message.from_user.id
        try:
            conn = get_conn()
            user = db.get_user(conn, tid)

            if user:
                if user['role'] == 'student':
                    bot.send_message(message.chat.id,
                        f"👋 Welcome back, {user['full_name']}!\n\n"
                        "/book — Request a ride\n"
                        "/cancel — Cancel active ride\n"
                        "/mystatus — Check ride status\n"
                        "/help — All commands")
                elif user['is_approved']:
                    bot.send_message(message.chat.id,
                        f"👋 Welcome back, Driver {user['full_name']}!\n\n"
                        "/driver — Manage your shuttle\n"
                        "/wallet — View your wallet\n"
                        "/help — All commands")
                else:
                    bot.send_message(message.chat.id,
                        "⏳ Your driver registration is still pending admin approval.")
                return

            # Pending driver request?
            if db.get_pending_driver_request(conn, tid):
                bot.send_message(message.chat.id,
                    "⏳ You already have a pending driver registration.\n"
                    "Please wait for admin approval.")
                return

            # New user — start registration
            bot.send_message(message.chat.id,
                "🚐 *Welcome to Campus Shuttle!*\n\nPlease select your role:",
                parse_mode='Markdown',
                reply_markup=role_keyboard())

        except Exception as e:
            logger.error(f"cmd_start error for {tid}: {e}", exc_info=True)
            bot.send_message(message.chat.id, "❌ An error occurred. Please try again.")

    # ── Role selection ────────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('role:'))
    def cb_role(call):
        role = call.data.split(':')[1]
        conn = get_conn()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=None)
        db.set_state(conn, call.from_user.id, 'waiting_for_name', {'role': role})

        label = '🎓 Student' if role == 'student' else '🚐 Driver'
        bot.send_message(call.message.chat.id,
            f"{label} *Registration*\n\nPlease enter your full name:",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Vehicle type selection (driver only) ──────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('vtype:'))
    def cb_vehicle_type(call):
        vtype = call.data.split(':')[1]   # 'car' or 'siena'
        conn = get_conn()
        state = db.get_state(conn, call.from_user.id)
        if not state:
            bot.answer_callback_query(call.id, "Session expired. Send /start to restart.")
            return

        data = state['data'] if isinstance(state['data'], dict) else {}
        full_name = data.get('full_name', 'Unknown')
        shuttle_name = data.get('shuttle_name', 'Unknown')

        db.clear_state(conn, call.from_user.id)

        # Create the driver request (admin approves later)
        dreq = db.create_driver_request(
            conn,
            call.from_user.id,
            call.from_user.username,
            full_name,
            shuttle_name,
            vtype,          # NEW — vehicle type passed to driver request
        )
        logger.info(f"Driver request created: {dreq['id']} — {full_name} ({shuttle_name}, {vtype})")

        # Tell the driver we received their request
        cap = 4 if vtype == 'car' else 7
        vtype_label = f"{'🚗 Car' if vtype == 'car' else '🚐 Siena'} (max {cap} passengers)"
        bot.edit_message_text(
            f"✅ *Registration Submitted!*\n\n"
            f"Name: {full_name}\n"
            f"Shuttle: {shuttle_name}\n"
            f"Vehicle: {vtype_label}\n\n"
            "Your driver application has been sent to the admins.\n"
            "You'll be notified once it's reviewed.",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

        # Notify admins (imported lazily to avoid circular import)
        from bot.keyboards.admin import admin_approval_keyboard
        from config import ADMIN_IDS as _ADMIN_IDS
        for admin_id in _ADMIN_IDS:
            try:
                bot.send_message(admin_id,
                    f"🚐 *New Driver Registration*\n\n"
                    f"👤 Name: {full_name}\n"
                    f"📱 Username: @{call.from_user.username or 'N/A'}\n"
                    f"🚐 Shuttle: {shuttle_name}\n"
                    f"🚗 Vehicle: {vtype_label}\n\n"
                    "Approve or reject this driver?",
                    parse_mode='Markdown',
                    reply_markup=admin_approval_keyboard(dreq['id']))
            except Exception as admin_err:
                logger.error(f"Failed to notify admin {admin_id}: {admin_err}")

    # ── Text FSM router ───────────────────────────────────────────────────────
    # NOTE: This must be registered LAST (it's a catch-all).
    # main.py registers it after all other handlers.
    # It is split out as a standalone function so main.py can register it.


def handle_text_fsm(bot, get_conn, message):
    """
    Handle FSM text states for registration.
    Called by the global text handler in main.py for:
      - waiting_for_name
      - waiting_for_shuttle_name
    Returns True if the state was handled, False otherwise.
    """
    conn = get_conn()
    state = db.get_state(conn, message.from_user.id)
    if not state:
        return False

    state_name = state['state']
    data = state['data'] if isinstance(state['data'], dict) else {}

    if state_name == 'waiting_for_name':
        name = message.text.strip()
        if len(name) < 2 or len(name) > 100:
            bot.send_message(message.chat.id, "❌ Name must be 2–100 characters. Try again:")
            return True

        role = data.get('role', 'student')
        if role == 'student':
            db.create_user(conn, message.from_user.id,
                           message.from_user.username, name, 'student')
            db.clear_state(conn, message.from_user.id)
            bot.send_message(message.chat.id,
                f"✅ *Registration Complete!*\n\nWelcome, {name}! 🎓\n\n"
                "Use /book to request a ride.",
                parse_mode='Markdown')
        else:
            # Driver — ask for shuttle name next
            db.set_state(conn, message.from_user.id,
                         'waiting_for_shuttle_name', {'role': 'driver', 'full_name': name})
            bot.send_message(message.chat.id,
                "🚐 What is the name or number of your shuttle? (e.g. *Shuttle 7*):",
                parse_mode='Markdown')
        return True

    if state_name == 'waiting_for_shuttle_name':
        shuttle_name = message.text.strip()
        if len(shuttle_name) < 1 or len(shuttle_name) > 100:
            bot.send_message(message.chat.id, "❌ Invalid shuttle name. Try again:")
            return True

        full_name = data.get('full_name', 'Unknown')
        db.set_state(conn, message.from_user.id,
                     'waiting_for_vehicle_type',
                     {'role': 'driver', 'full_name': full_name, 'shuttle_name': shuttle_name})
        bot.send_message(message.chat.id,
            "🚗 *What type of vehicle do you drive?*\n\n"
            "This affects how many passengers can book your shuttle.",
            parse_mode='Markdown',
            reply_markup=vehicle_type_keyboard())
        return True

    if state_name == 'waiting_for_vehicle_type':
        # User typed instead of pressing a button — prompt them to use buttons
        bot.send_message(message.chat.id,
            "Please tap one of the vehicle type buttons above:",
            reply_markup=vehicle_type_keyboard())
        return True

    return False
