"""
Telegram setup helper.
- Default testing mode: polling
- Old WebHook mode kept below as commented fallback: switch BOT_MODE=webhook and use Vercel URL
"""
import os
import sys
import telebot
from flask import Flask, jsonify

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import BOT_TOKEN, WEBHOOK_PATH, BOT_MODE

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


# Old WebHook setup logic kept here for easy switch back:
# def build_webhook_url():
#     """Return the Telegram webhook URL based on the configured deployment URL."""
#     vercel_url = os.environ.get('TEST_VERCEL_URL', '') or os.environ.get('VERCEL_URL', '')
#     if not vercel_url:
#         return None
#
#     if not vercel_url.startswith('http'):
#         vercel_url = f"https://{vercel_url}"
#
#     return f"{vercel_url.rstrip('/')}{WEBHOOK_PATH}"


@app.route('/api/setup', methods=['GET'])
def setup():
    """Register the webhook when in webhook mode, otherwise report the active test mode."""
    if BOT_MODE == 'polling':
        return jsonify({
            "mode": "polling",
            "message": "Polling mode is active for local testing. Set BOT_MODE=webhook to switch back to webhook mode.",
        }), 200

    # Old WebHook fallback:
    # webhook_url = build_webhook_url()
    # if not webhook_url:
    #     return jsonify({"error": "VERCEL_URL or TEST_VERCEL_URL is not set"}), 400
    #
    # try:
    #     bot.remove_webhook()
    #     bot.set_webhook(url=webhook_url)
    #     return jsonify({"mode": "webhook", "message": f"✅ Webhook registered: {webhook_url}"}), 200
    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500

    webhook_url = os.environ.get('TEST_VERCEL_URL', '') or os.environ.get('VERCEL_URL', '')
    if not webhook_url:
        return jsonify({"error": "VERCEL_URL or TEST_VERCEL_URL is not set"}), 400
    if not webhook_url.startswith('http'):
        webhook_url = f"https://{webhook_url}"

    webhook_url = f"{webhook_url.rstrip('/')}{WEBHOOK_PATH}"

    try:
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        return jsonify({"mode": "webhook", "message": f"✅ Webhook registered: {webhook_url}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
