import asyncio
import logging
import os
from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_storage import StateMemoryStorage
from telebot import asyncio_filters
from handlers import register_handlers
load_dotenv()

state_storage = StateMemoryStorage()

# 1. Standard Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Initialize the Async Bot
# We use environment variables for security. Never hardcode tokens.

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TEST_TOKEN_HERE")

bot = AsyncTeleBot(TOKEN, state_storage=state_storage)

# 3. Routing via Decorators
register_handlers(bot)


# Added state filter for the bot to know how to hanlde state decorator
bot.add_custom_filter(asyncio_filters.StateFilter(bot))

# 4. Main Event Loop
async def main() -> None:
    logger.info("Bot is starting up and polling for updates...")
    # non_stop=True ensures the bot doesn't crash if Telegram's servers hiccup
    await bot.polling(non_stop=True)

if __name__ == "__main__":
    # Natively run the async event loop (Python 3.10+)
    asyncio.run(main())