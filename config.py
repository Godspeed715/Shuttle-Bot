"""
config.py — Centralised configuration for Campus Shuttle Bot.
All environment variables are read once here and imported everywhere else.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get('BOT_TOKEN', '')
ADMIN_IDS   = [int(x) for x in os.environ.get('ADMIN_CHAT_IDS', '').split(',') if x.strip()]
TIMEOUT_SEC = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '300'))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# ── Paystack ──────────────────────────────────────────────────────────────────
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', 'sk_test_xxx')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', 'pk_test_xxx')
PAYSTACK_BASE_URL   = 'https://api.paystack.co'

# ── Pricing ───────────────────────────────────────────────────────────────────
DEFAULT_FARE_NAIRA  = int(os.environ.get('DEFAULT_FARE_NAIRA', '500'))   # ₦500 per passenger
PLATFORM_CUT_PCT    = float(os.environ.get('PLATFORM_CUT_PCT', '0.15'))  # 15%

# ── Shuttle Capacity ──────────────────────────────────────────────────────────
MAX_PASSENGERS_CAR   = 4
MAX_PASSENGERS_SIENA = 7

# ── Bot runtime mode ────────────────────────────────────────────────────────────
# Webhook is active by default for Vercel deployment.
# Polling is left here as a commented fallback for local testing only:
# BOT_MODE = 'polling'
BOT_MODE = os.environ.get('BOT_MODE', 'webhook').strip().lower()
if BOT_MODE not in {'polling', 'webhook'}:
    BOT_MODE = 'webhook'

# ── Misc ──────────────────────────────────────────────────────────────────────
# Old WebHook path kept here for easy reactivation:
# WEBHOOK_PATH = os.environ.get('WEBHOOK_PATH', '/asdfghjkl12390')
WEBHOOK_PATH = os.environ.get('WEBHOOK_PATH', '/asdfghjkl12390')
