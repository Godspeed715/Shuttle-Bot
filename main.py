"""
Campus Shuttle Bot — Vercel Webhook Handler
============================================
Receives Telegram updates via POST, processes them, and responds.
All bot logic lives in this single file for simplicity.
"""
import os
import json
import secrets
import datetime
import logging

import telebot
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request
import sys
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

# Calculate the parent directory path and append it to Python's search list
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))
from functions import db
from functions.keyboards import (
    role_keyboard, pickup_keyboard, destination_keyboard,
    drivers_keyboard, ride_response_keyboard, cancel_confirm_keyboard,
    admin_approval_keyboard, driver_dashboard_keyboard, location_update_keyboard,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# CONFIGURATION  (read from Vercel Environment Variables)
# ═══════════════════════════════════════════════════════════
BOT_TOKEN    = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_IDS    = [int(x) for x in os.environ.get('ADMIN_CHAT_IDS', '').split(',') if x.strip()]
TIMEOUT_SEC  = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '300'))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)


# ═══════════════════════════════════════════════════════════
# DATABASE CONNECTION  (one connection per request)
# ═══════════════════════════════════════════════════════════
_conn = None

def get_conn():
    """Return a reusable psycopg2 connection (auto-reconnects if stale)."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        _conn.autocommit = True
    return _conn


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def booking_id():
    """Generate a short unique booking reference like CU-A3F8B1."""
    return 'CU-' + secrets.token_hex(3).upper()


# ═══════════════════════════════════════════════════════════
# /start — REGISTRATION
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        logger.info(f"Processing /start from user {message.from_user.id}")
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)
        logger.info(f"Processed /start from user {message.from_user.id} and has gotten conn and user")
        if user:
            if user['role'] == 'student':
                bot.send_message(message.chat.id,
                    f"👋 Welcome back, {user['full_name']}!\n\n"
                    "/book — Request a ride\n"
                    "/cancel — Cancel active ride\n"
                    "/mystatus — Check ride status\n"
                    "/help — All commands")
                
            # If not user obviously it will be a driver and then we check if the driver is approved or not
            elif user['is_approved']:
                bot.send_message(message.chat.id,
                    f"👋 Welcome back, Driver {user['full_name']}!\n\n"
                    "/driver — Manage your shuttle\n"
                    "/help — All commands")
                
            # If the user is a driver but not approved, we show a pending message
            else:
                bot.send_message(message.chat.id,
                    "⏳ Your driver registration is still pending admin approval.")
            return

        # Check for pending driver request
        if db.get_pending_driver_request(conn, message.from_user.id):
            bot.send_message(message.chat.id,
                "⏳ You already have a pending driver registration.\nPlease wait for admin approval.")
            return

        # if no user and no pending driver request, start registration flow
        bot.send_message(message.chat.id,
            "🚐 *Welcome to Campus Shuttle!*\n\nPlease select your role:",
            parse_mode='Markdown', reply_markup=role_keyboard())
        logger.info(f"Sent /start registration prompt to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in cmd_start for user {message.from_user.id}: {e}", exc_info=True)
        try:
            bot.send_message(message.chat.id, "❌ An error occurred. Please try again.")
        except:
            logger.error(f"Failed to send error message to {message.chat.id}")
    bot.send_message(message.chat.id,
        "🚐 *Welcome to Campus Shuttle!*\n\nPlease select your role:",
        parse_mode='Markdown', reply_markup=role_keyboard())

# Callback when user selects role (student or driver)
@bot.callback_query_handler(func=lambda c: c.data.startswith('role:'))
def cb_role(call):
    role = call.data.split(':')[1]
    # Remove role selection buttons
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    conn = get_conn()
    # Save role in state so we know which registration flow to continue with when they enter their name
    db.set_state(conn, call.from_user.id, 'waiting_for_name', {'role': role})

    label = '🎓 Student' if role == 'student' else '🚐 Driver'
    bot.send_message(call.message.chat.id,
        f"{label} *Registration*\n\nPlease enter your full name:",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════
# /book — STUDENT BOOKING FLOW
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['book'])
def cmd_book(message):
    conn = get_conn()
    user = db.get_user(conn, message.from_user.id)

    if not user or user['role'] != 'student':
        bot.send_message(message.chat.id, "❌ Only registered students can book rides. Use /start to register.")
        return

    if db.get_active_ride_for_student(conn, user['id']):
        bot.send_message(message.chat.id,
            "⚠️ You already have an active ride.\nUse /cancel to cancel it first, or /mystatus to check it.")
        return

    locations = db.get_locations(conn)
    if not locations:
        bot.send_message(message.chat.id, "❌ No locations available right now.")
        return

    bot.send_message(message.chat.id,
        "📍 *Select your pickup location:*",
        parse_mode='Markdown', reply_markup=pickup_keyboard(locations))


@bot.callback_query_handler(func=lambda c: c.data.startswith('pk:'))
def cb_pickup(call):
    pickup_id = int(call.data.split(':')[1])
    conn = get_conn()
    locations = db.get_locations(conn)

    bot.edit_message_text(
        "📍 *Now select your destination:*",
        call.message.chat.id, call.message.message_id,
        parse_mode='Markdown',
        reply_markup=destination_keyboard(locations, pickup_id, exclude_id=pickup_id))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('dst:'))
def cb_destination(call):
    parts = call.data.split(':')
    pickup_id, dest_id = int(parts[1]), int(parts[2])

    conn = get_conn()
    shuttles = db.get_available_shuttles(conn)

    if not shuttles:
        bot.edit_message_text(
            "😔 *No shuttles available right now.*\nPlease try again later with /book.",
            call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        return

    bot.edit_message_text(
        "🚐 *Select a shuttle:*",
        call.message.chat.id, call.message.message_id,
        parse_mode='Markdown',
        reply_markup=drivers_keyboard(shuttles, pickup_id, dest_id))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('drv:'))
def cb_select_driver(call):
    parts = call.data.split(':')
    if parts[3] == 'cancel':
        bot.edit_message_text("❌ Booking cancelled.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    pickup_id, dest_id, shuttle_id = int(parts[1]), int(parts[2]), int(parts[3])
    conn = get_conn()

    user = db.get_user(conn, call.from_user.id)
    if not user:
        bot.answer_callback_query(call.id, "❌ Not registered.")
        return

    # Double-check no active ride
    if db.get_active_ride_for_student(conn, user['id']):
        bot.edit_message_text("⚠️ You already have an active ride.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    # Grab shuttle and location info
    shuttles = db.get_available_shuttles(conn)
    shuttle = next((s for s in shuttles if s['id'] == shuttle_id), None)
    if not shuttle:
        bot.edit_message_text("😔 This shuttle is no longer available. Try /book again.",
                              call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    pickup = db.get_location(conn, pickup_id)
    dest   = db.get_location(conn, dest_id)
    bid    = booking_id()
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=TIMEOUT_SEC)

    # Create ride request
    ride = db.create_ride(conn, bid, user['id'], shuttle['driver_id'],
                          shuttle_id, pickup_id, dest_id, expires)

    # Notify driver
    driver_msg = bot.send_message(shuttle['driver_telegram_id'],
        f"🔔 *New Ride Request!*\n\n"
        f"👤 Passenger: {user['full_name']}\n"
        f"📍 From: {pickup['name']}\n"
        f"📍 To: {dest['name']}\n\n"
        f"⏱ You have 5 minutes to respond.",
        parse_mode='Markdown',
        reply_markup=ride_response_keyboard(ride['id']))
    db.save_driver_msg_id(conn, ride['id'], driver_msg.message_id)

    # Notify student
    bot.edit_message_text(
        f"⏳ *Ride Request Sent!*\n\n"
        f"🎫 Booking: `{bid}`\n"
        f"📍 From: {pickup['name']}\n"
        f"📍 To: {dest['name']}\n"
        f"🚐 Shuttle: {shuttle['name']}\n"
        f"👤 Driver: {shuttle['driver_name']}\n\n"
        f"⏱ Waiting for driver to respond (5 min)...",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════
# DRIVER ACCEPT / REJECT
# ═══════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: c.data.startswith('acc:'))
def cb_accept(call):
    ride_id = int(call.data.split(':')[1])
    conn = get_conn()
    ride = db.get_ride(conn, ride_id)

    if not ride or ride['status'] != 'pending':
        bot.answer_callback_query(call.id, "⚠️ This request is no longer active.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    # Lazy expiry check — if past deadline, reject even if status is still 'pending'
    if datetime.datetime.now(datetime.timezone.utc) >= ride['expires_at'].replace(tzinfo=datetime.timezone.utc):
        db.update_ride_status(conn, ride_id, 'expired')
        bot.edit_message_text("⏰ This request has expired.", call.message.chat.id, call.message.message_id)
        bot.send_message(ride['student_telegram_id'],
            "⏰ *Request Expired*\n\nThe driver did not respond in time. Use /book to try again.",
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)
        return

    db.update_ride_status(conn, ride_id, 'accepted')

    # Tell driver
    bot.edit_message_text(
        f"✅ *Ride Accepted!*\n\n"
        f"👤 Passenger: {ride['student_name']}\n"
        f"📍 Pickup: {ride['pickup_name']}\n"
        f"📍 Destination: {ride['dest_name']}\n\n"
        f"Use /driver to complete the trip when done.",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    # Tell student
    bot.send_message(ride['student_telegram_id'],
        f"✅ *Ride Confirmed!*\n\n"
        f"🎫 Booking: `{ride['booking_id']}`\n"
        f"📍 From: {ride['pickup_name']}\n"
        f"📍 To: {ride['dest_name']}\n"
        f"🚐 Shuttle: {ride['shuttle_name']}\n"
        f"👤 Driver: {ride['driver_name']}\n\n"
        f"Your driver is on the way! Use /cancel to cancel if needed.",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('rej:'))
def cb_reject(call):
    ride_id = int(call.data.split(':')[1])
    conn = get_conn()
    ride = db.get_ride(conn, ride_id)

    if not ride or ride['status'] != 'pending':
        bot.answer_callback_query(call.id, "⚠️ This request is no longer active.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    db.update_ride_status(conn, ride_id, 'rejected')

    bot.edit_message_text("❌ You declined this ride request.",
                          call.message.chat.id, call.message.message_id)
    bot.send_message(ride['student_telegram_id'],
        "❌ *Ride Declined*\n\nThe driver declined your request. Use /book to try another shuttle.",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════
# /cancel — STUDENT CANCELLATION
# ═══════════════════════════════════════════════════════════

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
        bot.edit_message_text("ℹ️ This ride is no longer active.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    db.update_ride_status(conn, ride_id, 'cancelled')

    bot.edit_message_text("✅ *Ride Cancelled*\n\nUse /book to request a new ride.",
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    # Remove buttons from driver's chat
    if ride.get('driver_msg_id'):
        try:
            bot.edit_message_reply_markup(ride['driver_telegram_id'], ride['driver_msg_id'], reply_markup=None)
        except Exception:
            pass

    bot.send_message(ride['driver_telegram_id'],
        f"⚠️ *Ride Cancelled*\n\nPassenger {ride['student_name']} has cancelled their ride.",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('cnln:'))
def cb_cancel_no(call):
    bot.edit_message_text("👍 Your ride is still active.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════
# /mystatus — CHECK RIDE STATUS
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['mystatus'])
def cmd_status(message):
    conn = get_conn()
    user = db.get_user(conn, message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "❌ Use /start to register first.")
        return

    ride = db.get_active_ride_for_student(conn, user['id'])
    if not ride:
        bot.send_message(message.chat.id, "ℹ️ You have no active ride right now. Use /book to request one.")
        return

    status_emoji = {'pending': '⏳', 'accepted': '✅'}.get(ride['status'], '❓')
    bot.send_message(message.chat.id,
        f"📊 *Your Current Ride*\n\n"
        f"🎫 Booking: `{ride['booking_id']}`\n"
        f"📍 From: {ride['pickup_name']}\n"
        f"📍 To: {ride['dest_name']}\n"
        f"🚐 Shuttle: {ride['shuttle_name']}\n"
        f"👤 Driver: {ride['driver_name']}\n"
        f"{status_emoji} Status: {ride['status'].title()}",
        parse_mode='Markdown')


# ═══════════════════════════════════════════════════════════
# /driver — DRIVER DASHBOARD
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['driver'])
def cmd_driver(message):
    conn = get_conn()
    user = db.get_user(conn, message.from_user.id)

    if not user or user['role'] != 'driver':
        bot.send_message(message.chat.id, "❌ This command is for registered drivers only.")
        return
    if not user['is_approved']:
        bot.send_message(message.chat.id, "⏳ Your account is pending admin approval.")
        return

    shuttle = db.get_shuttle_by_driver(conn, user['id'])
    if not shuttle:
        bot.send_message(message.chat.id, "❌ No shuttle linked to your account. Contact admin.")
        return

    active_ride = db.get_active_ride_for_driver(conn, user['id'])
    status = '🟢 Online' if shuttle['is_available'] else '🔴 Offline'

    text = f"🚐 *{shuttle['name']} Dashboard*\n\nStatus: {status}"
    if active_ride:
        text += (f"\n\n📌 *Active Ride:*\n"
                 f"👤 Passenger: {active_ride['student_name']}\n"
                 f"📍 {active_ride['pickup_name']} → {active_ride['dest_name']}\n"
                 f"Status: {active_ride['status'].title()}")

    bot.send_message(message.chat.id, text, parse_mode='Markdown',
                     reply_markup=driver_dashboard_keyboard(
                         shuttle['id'], shuttle['is_available'], active_ride is not None))


@bot.callback_query_handler(func=lambda c: c.data.startswith('sht:'))
def cb_shuttle_action(call):
    parts = call.data.split(':')
    action, shuttle_id = parts[1], int(parts[2])
    conn = get_conn()

    if action == 'on':
        db.set_shuttle_availability(conn, shuttle_id, True)
        bot.answer_callback_query(call.id, "✅ You are now Online!")
        # Refresh dashboard
        cmd_driver_refresh(call.message, conn, call.from_user.id)

    elif action == 'off':
        db.set_shuttle_availability(conn, shuttle_id, False)
        bot.answer_callback_query(call.id, "🔴 You are now Offline.")
        cmd_driver_refresh(call.message, conn, call.from_user.id)

    elif action == 'loc':
        locations = db.get_locations(conn)
        bot.edit_message_text("📍 *Select your current location:*",
                              call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=location_update_keyboard(locations, shuttle_id))
        bot.answer_callback_query(call.id)

    elif action == 'cmp':
        user = db.get_user(conn, call.from_user.id)
        ride = db.get_active_ride_for_driver(conn, user['id'])
        if ride and ride['status'] == 'accepted':
            db.update_ride_status(conn, ride['id'], 'completed')
            bot.send_message(ride['student_telegram_id'],
                "🏁 *Trip Complete!*\n\nThanks for riding with us! Use /book for another ride.",
                parse_mode='Markdown')
            bot.answer_callback_query(call.id, "🏁 Trip marked complete!")
            cmd_driver_refresh(call.message, conn, call.from_user.id)
        else:
            bot.answer_callback_query(call.id, "⚠️ No accepted ride to complete.")

    elif action == 'pax':
        user = db.get_user(conn, call.from_user.id)
        ride = db.get_active_ride_for_driver(conn, user['id'])
        if ride:
            bot.answer_callback_query(call.id,
                f"👤 {ride['student_name']}\n📍 {ride['pickup_name']} → {ride['dest_name']}",
                show_alert=True)
        else:
            bot.answer_callback_query(call.id, "No active passenger.")


def cmd_driver_refresh(message, conn, telegram_id):
    """Re-render the driver dashboard after a state change."""
    user = db.get_user(conn, telegram_id)
    shuttle = db.get_shuttle_by_driver(conn, user['id'])
    active_ride = db.get_active_ride_for_driver(conn, user['id'])
    status = '🟢 Online' if shuttle['is_available'] else '🔴 Offline'

    text = f"🚐 *{shuttle['name']} Dashboard*\n\nStatus: {status}"
    if active_ride:
        text += (f"\n\n📌 *Active Ride:*\n"
                 f"👤 Passenger: {active_ride['student_name']}\n"
                 f"📍 {active_ride['pickup_name']} → {active_ride['dest_name']}\n"
                 f"Status: {active_ride['status'].title()}")

    try:
        bot.edit_message_text(text, message.chat.id, message.message_id,
                              parse_mode='Markdown',
                              reply_markup=driver_dashboard_keyboard(
                                  shuttle['id'], shuttle['is_available'], active_ride is not None))
    except Exception:
        bot.send_message(message.chat.id, text, parse_mode='Markdown',
                         reply_markup=driver_dashboard_keyboard(
                             shuttle['id'], shuttle['is_available'], active_ride is not None))


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

    bot.edit_message_text(f"✅ Location updated to *{loc['name']}*",
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    bot.answer_callback_query(call.id, f"📍 Now at {loc['name']}")


# ═══════════════════════════════════════════════════════════
# ADMIN — APPROVE / REJECT DRIVERS
# ═══════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: c.data.startswith('apv:'))
def cb_approve_driver(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Not authorized.")
        return

    req_id = int(call.data.split(':')[1])
    conn = get_conn()
    dreq = db.get_driver_request(conn, req_id)

    if not dreq or dreq['status'] != 'pending':
        bot.answer_callback_query(call.id, "⚠️ Already processed.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    db.update_driver_request_status(conn, req_id, 'approved')

    # Create driver account + shuttle
    user = db.create_user(conn, dreq['telegram_id'], dreq['username'],
                          dreq['full_name'], 'driver', is_approved=True)
    db.create_shuttle(conn, user['id'], dreq['shuttle_name'])

    bot.edit_message_text(
        f"✅ *Approved* driver {dreq['full_name']} ({dreq['shuttle_name']})",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    bot.send_message(dreq['telegram_id'],
        "✅ *Driver Approved!*\n\nYou are now registered as a driver. Use /driver to manage your shuttle.",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id, "Approved ✅")


@bot.callback_query_handler(func=lambda c: c.data.startswith('arj:'))
def cb_reject_driver(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Not authorized.")
        return

    req_id = int(call.data.split(':')[1])
    conn = get_conn()
    dreq = db.get_driver_request(conn, req_id)

    if not dreq or dreq['status'] != 'pending':
        bot.answer_callback_query(call.id, "⚠️ Already processed.")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    db.update_driver_request_status(conn, req_id, 'rejected')

    bot.edit_message_text(
        f"❌ *Rejected* driver {dreq['full_name']}",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    bot.send_message(dreq['telegram_id'],
        "❌ *Driver Request Rejected*\n\nYour driver registration has been rejected by an admin.",
        parse_mode='Markdown')
    bot.answer_callback_query(call.id, "Rejected ❌")


# ═══════════════════════════════════════════════════════════
# /help
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(message.chat.id,
        "🚐 *Campus Shuttle Commands*\n\n"
        "*Students:*\n"
        "/book — Request a ride\n"
        "/cancel — Cancel your active ride\n"
        "/mystatus — Check ride status\n\n"
        "*Drivers:*\n"
        "/driver — Open your shuttle dashboard\n\n"
        "/help — Show this message",
        parse_mode='Markdown')


# ═══════════════════════════════════════════════════════════
# TEXT MESSAGE ROUTER (for FSM states like name entry)
# This MUST be registered last — it's a catch-all.
# ═══════════════════════════════════════════════════════════

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    try:
        logger.info(f"Handling text message from user {message.from_user.id}: {message.text[:50]}")
        conn = get_conn()
        state = db.get_state(conn, message.from_user.id)
        if not state:
            logger.debug(f"No active state for user {message.from_user.id}")
            return  # no active conversational state — ignore

        state_name = state['state']
        state_data = state['data'] if isinstance(state['data'], dict) else {}

        # ── Name entry (both student and driver) ──
        if state_name == 'waiting_for_name':
            name = message.text.strip()
            if len(name) < 2 or len(name) > 100:
                bot.send_message(message.chat.id, "❌ Name must be 2–100 characters. Try again:")
                logger.warning(f"Invalid name length from user {message.from_user.id}: {len(name)}")
                return

            role = state_data.get('role', 'student')

            if role == 'student':
                db.create_user(conn, message.from_user.id, message.from_user.username, name, 'student')
                db.clear_state(conn, message.from_user.id)
                bot.send_message(message.chat.id,
                    f"✅ *Registration Complete!*\n\nWelcome, {name}! 🎓\n\n"
                    "Use /book to request a ride.",
                    parse_mode='Markdown')
                logger.info(f"Student registered: {message.from_user.id} - {name}")
            else:
                db.set_state(conn, message.from_user.id, 'waiting_for_shuttle_name',
                             {'role': 'driver', 'full_name': name})
                bot.send_message(message.chat.id,
                    "🚐 What is the name or number of your shuttle? (e.g. *Shuttle 7*):",
                    parse_mode='Markdown')
                logger.info(f"Driver name received: {message.from_user.id} - {name}")

        # ── Shuttle name entry (driver only) ──
        elif state_name == 'waiting_for_shuttle_name':
            shuttle_name = message.text.strip()
            if len(shuttle_name) < 1 or len(shuttle_name) > 100:
                bot.send_message(message.chat.id, "❌ Invalid shuttle name. Try again:")
                logger.warning(f"Invalid shuttle name from user {message.from_user.id}: {len(shuttle_name)}")
                return

            full_name = state_data.get('full_name', 'Unknown')
            db.clear_state(conn, message.from_user.id)

            # Create driver request for admin approval
            dreq = db.create_driver_request(conn, message.from_user.id,
                                            message.from_user.username, full_name, shuttle_name)
            logger.info(f"Driver request created: {dreq['id']} - {full_name} ({shuttle_name})")

            # Notify admins
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(admin_id,
                        f"🚐 *New Driver Registration*\n\n"
                        f"👤 Name: {full_name}\n"
                        f"📱 Username: @{message.from_user.username or 'N/A'}\n"
                        f"🚐 Shuttle: {shuttle_name}\n\n"
                        "Approve or reject this driver?",
                        parse_mode='Markdown',
                        reply_markup=admin_approval_keyboard(dreq['id']))
                    logger.info(f"Sent admin approval message to {admin_id}")
                except Exception as admin_error:
                    logger.error(f"Failed to notify admin {admin_id}: {admin_error}")

            bot.send_message(message.chat.id,
                "✅ *Registration Submitted!*\n\n"
                "Your driver application has been sent to the admins.\n"
                "You'll be notified once it's reviewed.",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in handle_text for user {message.from_user.id}: {e}", exc_info=True)
        try:
            bot.send_message(message.chat.id, "❌ An error occurred processing your message. Please try again.")
        except:
            logger.error(f"Failed to send error message to {message.chat.id}")


# ═══════════════════════════════════════════════════════════
# FLASK ENDPOINT  (Vercel calls this)
# ═══════════════════════════════════════════════════════════

@app.route(f'/{BOT_TOKEN}', methods=['POST','GET'])
def webhook():
    if request.method == 'POST':
        try:
            data = request.get_json(force=True)
            if data is None:
                logger.warning("⚠️ Webhook received empty JSON")
                return {'status': 'ok'}, 200
            
            logger.debug(f"📨 Raw webhook data: {json.dumps(data, default=str)[:200]}")
            
            update = telebot.types.Update.de_json(data)
            if update:
                logger.info(f"📤 Processing update {update.update_id}")
                try:
                    bot.process_new_updates([update])
                    logger.info(f"✅ Update {update.update_id} processed successfully")
                except Exception as handler_error:
                    logger.error(f"❌ Handler error on update {update.update_id}: {handler_error}", exc_info=True)
                    # Still return 200 to prevent Telegram retry
            else:
                logger.warning("⚠️ Failed to parse update from JSON data")
        except Exception as e:
            logger.error(f"❌ Webhook endpoint exception: {e}", exc_info=True)
            return {'status':'Error','message':'Error in WebHook!'},403
        
        return {'status': 'ok'}, 200
    
    elif request.method == 'GET':
        return {'status':'ok'},201


if __name__ == '__main__':
    app.run(debug=True, port=5000)
    # print("Bot is listening!")
    # bot.remove_webhook()
    # bot.infinity_polling()
