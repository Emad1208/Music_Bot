from .ads import init_user_state, user_state
from .ads_admin import (
    receive_ad_poster,
    receive_ad_name,
    receive_ad_max_send,
    receive_button_name_ad,
    receive_button_url_ad,
    receive_new_ad_value,
)
from .add_admin import (
    receive_admin_user_id,
    receive_admin_name,
)
from .msg_admin import (
    receive_message_content,
    receive_message_name,
    receive_button_name_msg,
    receive_button_url_msg,
    receive_target_user,
)
from db_Project.db_init import db


ADMIN_HANDLERS = {
    "waiting_ad_poster": receive_ad_poster,
    "waiting_ad_name": receive_ad_name,
    "waiting_ad_max_send": receive_ad_max_send,
    "waiting_button_name": receive_button_name_ad,
    "waiting_button_url": receive_button_url_ad,
    "waiting_new_ad_value": receive_new_ad_value,

    "waiting_admin_user_id": receive_admin_user_id,
    "waiting_admin_name": receive_admin_name,

    "set_message": receive_message_content,
    "waiting_message_name": receive_message_name,
    "waiting_msg_button_name": receive_button_name_msg,
    "waiting_msg_button_url": receive_button_url_msg,
    "waiting_target_user": receive_target_user,
}

admin_states = set(ADMIN_HANDLERS.keys())


async def handle_admin_message(message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply(
            "you are not an admin \nplease send others commands"
        )
        return

    init_user_state(user_id)

    state = user_state[user_id].get("state")
    handler = ADMIN_HANDLERS.get(state)

    if handler:
        await handler(message)


