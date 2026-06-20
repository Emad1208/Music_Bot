from .ads import user_state
from balethon.objects import InlineKeyboard

# import sys
# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(BASE_DIR))

from db_Project.db_init import db



async def receive_message_content(message):
    user_id = message.author.id

    media_type = None
    file_id = None
    caption = getattr(message, "caption", None)

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].id

    elif message.video:
        media_type = "video"
        file_id = message.video.id

    elif message.document:
        media_type = "document"
        file_id = message.document.id

    elif message.audio:
        media_type = "audio"
        file_id = message.audio.id

    elif message.text:
        media_type = "text"
        caption = message.text

    else:
        await message.reply(
            "نوع پیام پشتیبانی نمی‌شود."
        )
        return

    user_state[user_id]["message_data"] = {
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
        "keyboard_json": None
    }

    user_state[user_id]["state"] = "waiting_message_name"

    await message.reply(
        "*نام پیام را وارد کنید:*"
    )


async def receive_message_name(message):
    user_id = message.author.id

    user_state[user_id]["message_data"]["name"] = (
        message.text.strip()
    )

    user_state[user_id]["state"] = "waiting_message_keyboard"

    await message.reply(
        "*آیا این پیام دکمه دارد؟*",
        InlineKeyboard(
            [('بله', 'msg_keyboard_yes')],
            [('خیر', 'msg_keyboard_no')]
        )
    )


async def receive_button_name_msg(message):
    user_id = message.author.id

    button_name = message.text.strip()

    if not button_name:
        await message.reply("نام دکمه نمی‌تواند خالی باشد.")
        return

    if len(button_name) > 50:
        await message.reply("نام دکمه بیش از حد طولانی است.")
        return

    user_state[user_id]["message_data"]["button_name"] = button_name
    user_state[user_id]["state"] = "waiting_msg_button_url"

    await message.reply("*لینک دکمه را وارد کنید:*")


async def receive_button_url_msg(message):
    user_id = message.author.id
    url = message.text.strip()

    button_name = user_state[user_id]["message_data"].pop("button_name")

    user_state[user_id]["message_data"]["buttons"].append(
        [(button_name, url)]
    )

    user_state[user_id]["state"] = "waiting_more_msg_button"

    await message.reply(
        "*دکمه دیگری اضافه شود؟*",
        InlineKeyboard(
            [('بله', 'add_more_msg_button'),
            ('نه', 'finish_msg_buttons')]
        )
    )


async def receive_target_user(message):
    user_id = message.author.id

    if not message.text.isdigit():
        await message.reply(
            "شناسه معتبر وارد کنید."
        )
        return

    target_user_id = int(message.text)

    user_state[user_id]["target_user_id"] = (
        target_user_id
    )

    msg_id = user_state[user_id][
        "selected_message_id"
    ]

    msg = db.get_message_by_id(msg_id)

    user_state[user_id]["state"] = None

    await message.reply(
        f"*آیا از ارسال پیام زیر اطمینان دارید؟*\n\n"
        f"نام پیام: {msg[1]}\n"
        f"شناسه مقصد: {target_user_id}",
        InlineKeyboard(
            [('بله', 'confirm_send_one')],
            [('خیر', 'cancel_send_one')]
        )
    )


