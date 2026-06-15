import logging
from telebot.types import Message
from telebot.async_telebot import AsyncTeleBot

logger = logging.getLogger(__name__)

# This tells the bot: "If a user sends /start, run this async function"
def register(bot: AsyncTeleBot):
    @bot.message_handler(commands=['start'])
    async def start_command(message: Message) -> None:
        """Handles the /start command."""

        # We extract the user's first name safely from the Message object
        user_name = message.from_user.first_name


        # We await the network call to send a message back
        await bot.reply_to(message, f"System initialized. Welcome to the Telebot framework, {user_name}.")