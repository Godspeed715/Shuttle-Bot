"""
bot/handlers/__init__.py
Imports all handler register() functions and exports central dispatch_text_fsm.
"""
from bot.handlers import start, student, driver, wallet, admin


def register_all(bot, get_conn, booking_id_fn, admin_ids, timeout_sec):
    """Register all command and callback handlers with the bot instance."""
    start.register(bot, get_conn)
    student.register(bot, get_conn, booking_id_fn, admin_ids, timeout_sec)
    driver.register(bot, get_conn, admin_ids)
    wallet.register(bot, get_conn)
    admin.register(bot, get_conn, admin_ids)


def dispatch_text_fsm(bot, get_conn, message):
    """
    Route incoming text messages to the appropriate FSM handler based on user state.
    Returns True if handled, False otherwise.
    """
    if start.handle_text_fsm(bot, get_conn, message):
        return True
    if student.handle_student_text_fsm(bot, get_conn, message):
        return True
    if wallet.handle_wallet_text_fsm(bot, get_conn, message):
        return True
    if admin.handle_admin_text_fsm(bot, get_conn, message):
        return True
    return False
