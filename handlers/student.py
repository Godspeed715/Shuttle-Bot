import logging
import copy
from env import DRIVER_ID, ADMIN_ID
from states.booking import PassengerBookingFlow
from states.register import RegistrationFlow
from keyboards.inline import locations_keyboard, role_selection_keyboard, registration_keyboard, driver_response_keyboard
from error_handling.error import error_boundary
from telebot.types import CallbackQuery, Message
from telebot.async_telebot import AsyncTeleBot
loc = {
    'daniel': 'Daniel Hall',
    'joseph': 'Joseph Hall',
    'john': 'John Hall',
    'peter': 'Peter Hall',
    'paul': 'Paul Hall',
    'esther': 'Esther Hall',
    'mary': 'Mary Hall',
    'deborah': 'Deborah Hall',
    'lydia': 'Lydia Hall',
    'dorcas': 'Dorcas Hall',
    'cst': 'CST',
    'cmss': 'CMSS',
    'lt': 'Lecture Theatre (LT)',
    'eng': 'Engineering Block'
}
locations = [
    {
        "name": "Daniel Hall",
        "id": "daniel"
    },
    {
        "name": "Joseph Hall",
        "id": "joseph"
    },
    {
        "name": "John Hall",
        "id": "john"
    },
    {
        "name": "Peter Hall",
        "id": "peter"
    },
    {
        "name": "Paul Hall",
        "id": "paul"
    },
    {
        "name": "Esther Hall",
        "id": "esther"
    },
    {
        "name": "Mary Hall",
        "id": "mary"
    },
    {
        "name": "Deborah Hall",
        "id": "deborah"
    },
    {
        "name": "Lydia Hall",
        "id": "lydia"
    },
    {
        "name": "Dorcas Hall",
        "id": "dorcas"
    },
    {
        "name": "CST",
        "id": "cst"
    },
    {
        "name": "CMSS",
        "id": "cmss"
    },
    {
        "name": "Lecture Theatre (LT)",
        "id": "lt"
    },
    {
        "name": "Engineering Block",
        "id": "eng"
    }
]
logger = logging.getLogger(__name__)

def register(bot: AsyncTeleBot):
    # ---- Booking ----
    @bot.message_handler(commands=['book'])
    @error_boundary
    async def book_command(message: Message) -> None:
        """Handles the /book command."""
        markup = locations_keyboard(locations, "pk")
        await bot.set_state(message.from_user.id, PassengerBookingFlow.choose_pickup, message.chat.id)
        await bot.send_message(message.chat.id, "**Please Enter your current location:** ", reply_markup=markup, parse_mode="markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pk:'), state=PassengerBookingFlow.choose_pickup)
    @error_boundary
    async def callback_pickup(call: CallbackQuery):
        await bot.answer_callback_query(call.id)
        pickup_id = call.data.split(':')[1]

        markup = locations_keyboard(locations, "dst")
        async with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data['pickup_id'] = pickup_id

        await bot.set_state(call.from_user.id, PassengerBookingFlow.choose_destination, call.message.chat.id)
        await bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Pick the destination location: ", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('dst:'), state=PassengerBookingFlow.choose_destination)
    @error_boundary
    async def callback_destination(call: CallbackQuery):
        await bot.answer_callback_query(call.id)
        dest_id = call.data.split(':')[1]

        async with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            pickup_id = data.get('pickup_id', 'Unknown')

        await bot.delete_state(call.from_user.id, call.message.chat.id)
        await bot.send_message(DRIVER_ID,
                               text=f'Shuttle Request\nUser: {call.from_user.username}\n {loc[pickup_id]} → {loc[dest_id]}\n',
                               reply_markup=driver_response_keyboard(1234))
        await bot.edit_message_text(chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    text=f"📍 {loc[pickup_id]} → {loc[dest_id]}\n"
                f"🚐 Mr Benga Shuttle\n\n"
                "⏳ Sending request to driver...")

    #    --- Registration ---
    @bot.message_handler(commands=['register'])
    @error_boundary
    async def register_command(message: Message):
        """Handles the /register command."""
        await bot.set_state(message.from_user.id, RegistrationFlow.choose_role, message.chat.id)
        await bot.send_message(message.chat.id,
                               "Welcome! Please select your role: ",
                               reply_markup=role_selection_keyboard(),)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('role:'), state=RegistrationFlow.choose_role)
    @error_boundary
    async def callback_role(call: CallbackQuery):
        await bot.answer_callback_query(call.id)
        role = call.data.split(':')[1]

        async with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data['role'] = role

        await bot.set_state(call.from_user.id, RegistrationFlow.enter_name, call.message.chat.id)
        await bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text="Enter your full name: ")

    @bot.message_handler(state=RegistrationFlow.enter_name)
    @error_boundary
    async def callback_role(message: Message):
        name = message.text.strip()
        async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            data['name'] = name
            role = data['role']

        await bot.set_state(message.from_user.id, RegistrationFlow.check_details, message.chat.id)
        await bot.send_message(chat_id=message.chat.id,
                               text=f"Are you sure of your details\nRole: {role}\nName: {name}",
                               reply_markup=registration_keyboard())

    @bot.callback_query_handler(func= lambda call: call.data.startswith('registration') ,state=RegistrationFlow.check_details)
    @error_boundary
    async def callback_registration(call: CallbackQuery):
        await bot.answer_callback_query(call.id)
        reply = call.data.split(':')[1]

        if reply == 'yes':

            await bot.delete_state(call.from_user.id, call.message.chat.id)

            await bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ Registration complete! Welcome aboard.\nYou can book rides with /book",
            )
        else:
            mock_message = copy.deepcopy(call.message)

            # 3. CRITICAL: Overwrite the sender ID with the actual human who clicked the button
            mock_message.from_user = call.from_user

            # 4. Await your command handler
            await register_command(mock_message)