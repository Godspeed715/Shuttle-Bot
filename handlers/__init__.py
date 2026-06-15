from handlers import student, start


def register_handlers(bot):
    """Register all bot handlers."""
    start.register(bot)
    student.register(bot)
    # driver.register(bot)
    # admin.register(bot)
