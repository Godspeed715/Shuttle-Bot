"""
Main Flask app for Vercel deployment
Consolidates all routes and handlers
"""
import os
import sys
import json
import logging
from flask import Flask, request

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telebot

from handlers_registry import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
DATABASE_URL = os.environ.get('DATABASE_URL', '')

bot = telebot.TeleBot(BOT_TOKEN)

# Register all handlers on this bot instance
logger.info("Initializing bot with handlers...")
try:
    register_handlers(bot)
    logger.info("✅ Bot handlers registered")
except Exception as e:
    logger.error(f"❌ Failed to register handlers: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════
# WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════

@app.route('/api/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        logger.debug(f"Webhook data: {json.dumps(data, default=str)[:300]}")
        
        if data is None:
            logger.warning("Webhook received empty JSON")
            return {'status': 'ok'}, 200
        
        update = telebot.types.Update.de_json(data)
        if update:
            logger.info(f"Processing update {update.update_id}")
            try:
                bot.process_new_updates([update])
                logger.info(f"✅ Successfully processed update {update.update_id}")
            except Exception as handler_error:
                logger.error(f"❌ Handler error on update {update.update_id}: {handler_error}", exc_info=True)
                raise
        else:
            logger.warning("Failed to parse update from JSON")
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return {'error': str(e), 'status': 'error'}, 500
    
    return {'status': 'ok'}, 200


# ═══════════════════════════════════════════════════════════
# SETUP ENDPOINT (register webhook with Telegram)
# ═══════════════════════════════════════════════════════════

@app.route('/api/setup', methods=['GET'])
def setup():
    """Register the webhook URL with Telegram."""
    vercel_url = os.environ.get('TEST_VERCEL_URL', os.environ.get('VERCEL_URL', ''))

    if not vercel_url:
        error_msg = "VERCEL_URL not set"
        logger.error(error_msg)
        return {'error': error_msg}, 400

    if not vercel_url.startswith('http'):
        vercel_url = f"https://{vercel_url}"

    webhook_url = f"{vercel_url}/api/webhook"
    
    try:
        logger.info(f"Setting webhook to: {webhook_url}")
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        success_msg = f"✅ Webhook registered: {webhook_url}"
        logger.info(success_msg)
        return {'message': success_msg}, 200
    except Exception as e:
        error_msg = f"Failed to set webhook: {str(e)}"
        logger.error(error_msg)
        return {'error': error_msg}, 500


# ═══════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
@app.route('/api', methods=['GET'])
def health():
    return {
        'status': 'ok',
        'bot_token_set': bool(BOT_TOKEN),
        'database_url_set': bool(DATABASE_URL),
        'message': 'Shuttle Bot API is running'
    }, 200
