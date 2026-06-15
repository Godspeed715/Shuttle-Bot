"""
One-time Webhook Setup — visit this URL once after deploying to register
your Vercel URL with Telegram.

Usage:  GET https://your-app.vercel.app/api/setup
"""
import os
import telebot
from flask import Flask, jsonify

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


@app.route('/api/setup', methods=['GET'])
def setup():
    """Register the webhook URL with Telegram."""
    # Vercel gives you: https://your-project.vercel.app
    # We need to tell Telegram to send updates to /api/webhook
    vercel_url = os.environ.get('VERCEL_URL', '')

    if not vercel_url:
        return jsonify({"error": "VERCEL_URL not set. Vercel should set this automatically."}), 400

    # Ensure https:// prefix
    if not vercel_url.startswith('http'):
        vercel_url = f"https://{vercel_url}"

    webhook_url = f"{vercel_url}/api/webhook"
    
    try:
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        return jsonify({"message": f"✅ Webhook registered: {webhook_url}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
