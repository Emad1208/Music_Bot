from commands.ads import user_state
from Platform.bot_helpers import start_message


async def handle_start_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    user_state.setdefault(user_id, {"state": None})

    if data.startswith("start_menu"):
        await start_message(callback_query.message)
        return