"""
Campus Shuttle Bot — Vercel Webhook Handler & Application Entrypoint
=====================================================================
Modular architecture:
- bot/handlers: start, student, driver, wallet, admin
- bot/keyboards: student, driver, admin, common
- functions: db, paystack, pricing
- api: paystack_webhook, cron, setup
"""
import os
import json
import secrets
import logging

import telebot
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify

from config import (
    BOT_TOKEN, DATABASE_URL, ADMIN_IDS, TIMEOUT_SEC, WEBHOOK_PATH, BOT_MODE,
)
from functions import db
from bot.handlers import register_all, dispatch_text_fsm
from api.paystack_webhook import handle_paystack_webhook

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ── App & Bot Instances ───────────────────────────────────────────────────────
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ── Database Connection ───────────────────────────────────────────────────────
_conn = None


def get_conn():
    """Return a reusable psycopg2 connection (auto-reconnects if stale)."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        _conn.autocommit = True
    return _conn


def booking_id():
    """Generate a short unique booking reference like CU-A3F8B1."""
    return 'CU-' + secrets.token_hex(3).upper()


# ── Register All Handlers ─────────────────────────────────────────────────────
register_all(bot, get_conn, booking_id, ADMIN_IDS, TIMEOUT_SEC)


# ── /help Command ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        "🚐 *Campus Shuttle Commands*\n\n"
        "*🎓 Students:*\n"
        "/book — Request a ride (set passengers & cash/transfer)\n"
        "/cancel — Cancel your active ride\n"
        "/mystatus — Check your ride status\n\n"
        "*🚐 Drivers:*\n"
        "/driver — Open your shuttle dashboard\n"
        "/wallet — Check balance, cash debt & withdraw\n\n"
        "*👑 Admins:*\n"
        "/admin — Cash remittances & route prices\n\n"
        "/help — Show this message",
        parse_mode='Markdown'
    )


# ── Catch-All Text Router (Registered LAST) ───────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    """Route text input to active FSM states across student, driver, wallet, and admin."""
    try:
        handled = dispatch_text_fsm(bot, get_conn, message)
        if not handled:
            logger.debug(f"Unhandled text message from {message.from_user.id}: {message.text[:30]}")
    except Exception as e:
        logger.error(f"Error handling text from {message.from_user.id}: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ An error occurred processing your input. Please try again.")


# ── WebHook (old code kept for easy switch back) ──────────────────────────────
# @app.route(WEBHOOK_PATH, methods=['POST', 'GET'])
# @app.route('/api/webhook', methods=['POST', 'GET'])
# def telegram_webhook():
#     if request.method == 'POST':
#         try:
#             data = request.get_json(force=True)
#             if not data:
#                 return {'status': 'ok'}, 200
#
#             update = telebot.types.Update.de_json(data)
#             if update:
#                 bot.process_new_updates([update])
#         except Exception as e:
#             logger.error(f"Webhook processing error: {e}", exc_info=True)
#             return {'status': 'error', 'message': str(e)}, 200
#
#         return {'status': 'ok'}, 200
#
#     return {'status': 'ok', 'service': 'telegram_webhook'}, 200
#
#
# ── Paystack WebHook (old code kept for easy switch back) ─────────────────────
# @app.route('/api/paystack/webhook', methods=['POST'])
# def paystack_webhook_route():
#     """Receives charge.success and transfer events from Paystack."""
#     return handle_paystack_webhook(bot, get_conn, request)


# ── Cron Route (Auto-expires stale rides) ─────────────────────────────────────
@app.route('/api/cron', methods=['GET'])
def cron_route():
    """Expires pending rides older than 5 minutes and notifies both parties."""
    conn = get_conn()
    try:
        expired = db.expire_old_requests(conn)
        count = 0
        for ride in expired:
            try:
                bot.send_message(
                    ride['student_telegram_id'],
                    "⏰ *Request Expired*\n\n"
                    "The driver did not respond within 5 minutes. Use /book to try again.",
                    parse_mode='Markdown'
                )
                bot.send_message(
                    ride['driver_telegram_id'],
                    f"⏰ *Request Expired*\n\n"
                    f"Ride request from {ride['student_name']} has expired (no response).",
                    parse_mode='Markdown'
                )
                if ride.get('driver_msg_id'):
                    try:
                        bot.edit_message_reply_markup(
                            ride['driver_telegram_id'], ride['driver_msg_id'], reply_markup=None)
                    except Exception:
                        pass
                count += 1
            except Exception as notify_err:
                logger.error(f"Error expiring ride {ride['id']}: {notify_err}")

        return jsonify({"message": f"Expired {count} stale ride(s)", "count": count}), 200
    except Exception as e:
        logger.error(f"Cron execution error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Webhook Registration Helper ───────────────────────────────────────────────
@app.route('/api/setup', methods=['GET'])
def setup_webhook_route():
    """Register the Telegram webhook URL if webhook mode is active."""
    if BOT_MODE == 'polling':
        return jsonify({
            "mode": "polling",
            "message": "Polling mode is active for testing. Set BOT_MODE=webhook to switch back to webhook mode.",
        }), 200

    vercel_url = os.environ.get('TEST_VERCEL_URL', '') or os.environ.get('VERCEL_URL', '')
    if not vercel_url:
        return jsonify({"error": "VERCEL_URL environment variable is not set"}), 400

    if not vercel_url.startswith('http'):
        vercel_url = f"https://{vercel_url}"

    webhook_url = f"{vercel_url.rstrip('/')}{WEBHOOK_PATH}"
    try:
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        return jsonify({"mode": "webhook", "message": f"✅ Webhook registered: {webhook_url}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Admin Remittances API Route ───────────────────────────────────────────────
@app.route('/api/admin/remittances', methods=['GET'])
def admin_remittances_api():
    """Protected API endpoint for admin to view outstanding cash debts."""
    conn = get_conn()
    debtors = db.get_drivers_with_debt(conn)
    total_debt = sum(d['commission_owed'] for d in debtors)
    return jsonify({
        "total_outstanding_commission": total_debt,
        "debtor_count": len(debtors),
        "drivers": [
            {
                "driver_id": d['driver_id'],
                "full_name": d['full_name'],
                "commission_owed": d['commission_owed'],
                "balance": d['balance'],
                "total_earned": d['total_earned'],
            }
            for d in debtors
        ]
    }), 200


# ── Health Check ──────────────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "Campus Shuttle Bot API",
        "status": "online",
        "version": "2.0.0"
    }), 200


if __name__ == '__main__':
    if BOT_MODE == 'polling':
        logger.info("Starting Campus Shuttle Bot in polling mode for testing...")
        bot.infinity_polling(timeout=20, long_polling_timeout=30, skip_pending=True)
    else:
        logger.info("Starting Campus Shuttle Bot on port 5000 in webhook mode...")
        app.run(debug=True, port=5000)
