"""
Expiry Cron — called periodically to expire stale ride requests.

On Vercel free tier, cron runs at most once per day.
For more frequent checks, use a free external pinger
like cron-job.org to hit this endpoint every 1-5 minutes.

Also works as a manual trigger:  GET /api/cron
"""
import os
import sys
import logging

import telebot
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lib import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ['BOT_TOKEN']
DATABASE_URL = os.environ['DATABASE_URL']

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


@app.route('/api/cron', methods=['GET'])
def cron():
    """Find all pending rides past their 5-minute deadline, expire them, and notify both parties."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True

    try:
        expired = db.expire_old_requests(conn)
        count = 0

        for ride in expired:
            try:
                # Tell student
                bot.send_message(ride['student_telegram_id'],
                    "⏰ *Request Expired*\n\nThe driver did not respond within 5 minutes. Use /book to try again.",
                    parse_mode='Markdown')

                # Tell driver
                bot.send_message(ride['driver_telegram_id'],
                    f"⏰ *Request Expired*\n\nRide request from {ride['student_name']} has expired (no response).",
                    parse_mode='Markdown')

                # Remove Accept/Reject buttons from driver's chat
                if ride.get('driver_msg_id'):
                    try:
                        bot.edit_message_reply_markup(
                            ride['driver_telegram_id'], ride['driver_msg_id'], reply_markup=None)
                    except Exception:
                        pass

                count += 1
                logger.info(f"Expired ride {ride['id']}")
            except Exception as e:
                logger.error(f"Error notifying for ride {ride['id']}: {e}")

        return f"Expired {count} ride(s)", 200
    finally:
        conn.close()
