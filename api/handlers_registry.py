"""
Handler registry - all bot handlers in one place
This module registers handlers on a bot instance
"""
import os
import sys
import datetime
import secrets
import logging

# Add parent directory to path to allow imports from functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telebot
import psycopg2
from psycopg2.extras import RealDictCursor

from functions import db
from functions.keyboards import (
    role_keyboard, pickup_keyboard, destination_keyboard,
    drivers_keyboard, ride_response_keyboard, cancel_confirm_keyboard,
    admin_approval_keyboard, driver_dashboard_keyboard, location_update_keyboard,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# CONFIG (lazy-loaded when register_handlers is called)
# ═══════════════════════════════════════════════════════════

_config = {}

def _get_config():
    """Get configuration, lazy-load from env if needed."""
    global _config
    if not _config:
        _config['BOT_TOKEN'] = os.environ.get('BOT_TOKEN', '')
        _config['DATABASE_URL'] = os.environ.get('DATABASE_URL', '')
        _config['ADMIN_IDS'] = [int(x) for x in os.environ.get('ADMIN_CHAT_IDS', '').split(',') if x.strip()]
        _config['TIMEOUT_SEC'] = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '300'))
    return _config

# ═══════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════

_conn = None

def get_conn():
    """Get database connection with auto-reconnect."""
    global _conn
    if _conn is None or _conn.closed:
        config = _get_config()
        _conn = psycopg2.connect(config['DATABASE_URL'], cursor_factory=RealDictCursor)
        _conn.autocommit = True
    return _conn


def booking_id():
    """Generate a short unique booking reference like CU-A3F8B1."""
    return 'CU-' + secrets.token_hex(3).upper()


# ═══════════════════════════════════════════════════════════
# HANDLER REGISTRATION
# ═══════════════════════════════════════════════════════════

def register_handlers(bot):
    """Register all message and callback handlers on the bot instance."""
    
    logger.info("Registering handlers...")
    config = _get_config()

    # ── /start ──
    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        try:
            logger.info(f"✅ /start from user {message.from_user.id}")
            conn = get_conn()
            user = db.get_user(conn, message.from_user.id)

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
                        "/help — All commands")
                else:
                    bot.send_message(message.chat.id,
                        "⏳ Your driver registration is still pending admin approval.")
                return

            if db.get_pending_driver_request(conn, message.from_user.id):
                bot.send_message(message.chat.id,
                    "⏳ You already have a pending driver registration.\nPlease wait for admin approval.")
                return

            bot.send_message(message.chat.id,
                "🚐 *Welcome to Campus Shuttle!*\n\nPlease select your role:",
                parse_mode='Markdown', reply_markup=role_keyboard())
        except Exception as e:
            logger.error(f"❌ cmd_start error: {e}", exc_info=True)
            try:
                bot.send_message(message.chat.id, "❌ An error occurred. Please try /start again.")
            except:
                pass

    # ── role callback ──
    @bot.callback_query_handler(func=lambda c: c.data.startswith('role:'))
    def cb_role(call):
        try:
            logger.info(f"✅ Role selected: {call.data}")
            role = call.data.split(':')[1]
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            
            conn = get_conn()
            db.set_state(conn, call.from_user.id, 'waiting_for_name', {'role': role})

            label = '🎓 Student' if role == 'student' else '🚐 Driver'
            bot.send_message(call.message.chat.id,
                f"{label} *Registration*\n\nPlease enter your full name:",
                parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"❌ cb_role error: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Error")

    # ── Text handler (FSM states) ──
    @bot.message_handler(func=lambda m: True, content_types=['text'])
    def handle_text(message):
        try:
            logger.info(f"✅ Text from user {message.from_user.id}: {message.text[:50]}")
            conn = get_conn()
            state = db.get_state(conn, message.from_user.id)
            if not state:
                logger.debug(f"No state for user {message.from_user.id}, ignoring")
                return

            state_name = state['state']
            state_data = state['data'] if isinstance(state['data'], dict) else {}

            if state_name == 'waiting_for_name':
                name = message.text.strip()
                if len(name) < 2 or len(name) > 100:
                    bot.send_message(message.chat.id, "❌ Name must be 2–100 characters. Try again:")
                    return

                role = state_data.get('role', 'student')

                if role == 'student':
                    db.create_user(conn, message.from_user.id, message.from_user.username, name, 'student')
                    db.clear_state(conn, message.from_user.id)
                    bot.send_message(message.chat.id,
                        f"✅ *Registration Complete!*\n\nWelcome, {name}! 🎓\n\nUse /book to request a ride.",
                        parse_mode='Markdown')
                    logger.info(f"✅ Student registered: {message.from_user.id}")
                else:
                    db.set_state(conn, message.from_user.id, 'waiting_for_shuttle_name',
                                 {'role': 'driver', 'full_name': name})
                    bot.send_message(message.chat.id,
                        "🚐 What is your shuttle name? (e.g. *Shuttle 7*):",
                        parse_mode='Markdown')
                    logger.info(f"✅ Driver name: {message.from_user.id} - {name}")

            elif state_name == 'waiting_for_shuttle_name':
                shuttle_name = message.text.strip()
                if len(shuttle_name) < 1 or len(shuttle_name) > 100:
                    bot.send_message(message.chat.id, "❌ Invalid shuttle name. Try again:")
                    return

                full_name = state_data.get('full_name', 'Unknown')
                db.clear_state(conn, message.from_user.id)

                dreq = db.create_driver_request(conn, message.from_user.id,
                                                message.from_user.username, full_name, shuttle_name)
                logger.info(f"✅ Driver request created: {dreq['id']}")

                for admin_id in config['ADMIN_IDS']:
                    try:
                        bot.send_message(admin_id,
                            f"🚐 *New Driver Registration*\n\n"
                            f"👤 Name: {full_name}\n"
                            f"📱 Username: @{message.from_user.username or 'N/A'}\n"
                            f"🚐 Shuttle: {shuttle_name}\n\n"
                            "Approve or reject?",
                            parse_mode='Markdown',
                            reply_markup=admin_approval_keyboard(dreq['id']))
                        logger.info(f"✅ Sent approval message to admin {admin_id}")
                    except Exception as admin_error:
                        logger.error(f"❌ Failed to notify admin {admin_id}: {admin_error}")

                bot.send_message(message.chat.id,
                    "✅ *Registration Submitted!*\n\nYou'll be notified once the admins review your application.",
                    parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ handle_text error: {e}", exc_info=True)
            try:
                bot.send_message(message.chat.id, "❌ Error processing message")
            except:
                pass

    # ── /help ──
    @bot.message_handler(commands=['help'])
    def cmd_help(message):
        try:
            bot.send_message(message.chat.id,
                "🚐 *Campus Shuttle Commands*\n\n"
                "*Students:*\n/book — Request a ride\n/cancel — Cancel ride\n/mystatus — Check status\n\n"
                "*Drivers:*\n/driver — Dashboard\n\n/help — Show this message",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ cmd_help error: {e}", exc_info=True)

    logger.info("✅ Handlers registered successfully")
