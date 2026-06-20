from .ads import user_state
from balethon.objects import InlineKeyboard

# import sys
# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(BASE_DIR))

from db_Project.db_init import db


async def receive_admin_user_id(message):
    user_id = message.author.id

    if not message.text.isdigit():
        await message.reply("آیدی معتبر وارد کنید.")
        return

    target_user_id = int(message.text)

    if db.is_admin(target_user_id):
        await message.reply("این کاربر قبلاً ادمین شده است.")
        return

    user_state[user_id]["new_admin_user_id"] = target_user_id
    user_state[user_id]["state"] = "waiting_admin_name"

    await message.reply(
        "*نام ادمین را وارد کنید:*"
    )


async def receive_admin_name(message):
    user_id = message.author.id

    admin_name = message.text.strip()

    user_state[user_id]["new_admin_name"] = admin_name
    user_state[user_id]["state"] = "waiting_admin_confirm"

    target_user_id = user_state[user_id]["new_admin_user_id"]

    await message.reply(
        f"*آیا از صحت اطلاعات زیر اطمینان دارید؟*\n\n"
        f"نام: {admin_name}\n"
        f"آیدی: {target_user_id}",
        InlineKeyboard(
            [('بله', 'confirm_add_admin')],
            [('خیر', 'cancel_add_admin')]
        )
    )
