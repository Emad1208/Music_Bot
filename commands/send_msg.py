from balethon.objects import InlineKeyboard, InlineKeyboardButton
import sqlite3
import json
import asyncio


from .ads import safe_answer, init_user_state, user_state

# import sys
# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(BASE_DIR))

from db_Project.db_init import db

# ---------------------
# Setting msg
# ---------------------
async def set_new_message(callback_query):
    user_id = callback_query.author.id

    init_user_state(user_id)

    user_state[user_id]["state"] = "set_message"

    await safe_answer(
        callback_query,
        "تنظیم پیام جدید"
    )

    await callback_query.message.edit(
        "*لطفا پیام مورد نظر را ارسال کنید:*",InlineKeyboard(
            [('برگشت به منوی پیام ها', 'back_msg')]
        )
    )

# ---------------------
# Deleting msg
# ---------------------
async def delete_message(callback_query):
    messages = db.get_messages()

    if not messages:
        await safe_answer(callback_query, "پیامی وجود ندارد")

        await callback_query.message.edit(
            "*هیچ پیامی ثبت نشده است.*",InlineKeyboard(
            [('برگشت به منوی پیام ها', 'back_msg')]
        )
        )
        return

    buttons = []

    for msg in messages:
        msg_id = msg[0]
        msg_name = msg[1]

        buttons.append([
            (
                msg_name,
                f"delete_message:{msg_id}"
            )
        ])

    buttons.append([
        ('برگشت به منوی پیام ها', 'back_msg')
    ])

    await safe_answer(callback_query, "حذف پیام")

    await callback_query.message.edit(
        "*پیام مورد نظر را انتخاب کنید:*",
        InlineKeyboard(*buttons)
    )


async def ask_delete_message_confirm(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    if not msg:
        await safe_answer(
            callback_query,
            "پیام پیدا نشد"
        )
        return

    msg_name = msg[1]

    await safe_answer(
        callback_query,
        "تایید حذف"
    )

    await callback_query.message.edit(
        f"*آیا مطمئن هستید که میخواهید پیام {msg_name} را حذف کنید؟*",
        InlineKeyboard(
            [('بله',
              f'confirm_delete_message:{message_id}')],
            [('خیر',
              f'cancel_delete_message:{message_id}')]
        )
    )


async def confirm_delete_message(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    if not msg:
        await safe_answer(
            callback_query,
            "پیام پیدا نشد"
        )
        return

    msg_name = msg[1]

    deleted = db.delete_message(message_id)

    await safe_answer(
        callback_query,
        "پیام حذف شد"
    )

    if deleted:
        await callback_query.message.edit(
            f"*پیام {msg_name} با موفقیت حذف شد.*"
        )
    else:
        await callback_query.message.edit(
            f"*حذف پیام {msg_name} ناموفق بود.*"
        )


async def cancel_delete_message(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    if not msg:
        await safe_answer(
            callback_query,
            "پیام پیدا نشد"
        )
        return

    msg_name = msg[1]

    await safe_answer(
        callback_query,
        "لغو عملیات"
    )

    await callback_query.message.edit(
        f"*حذف پیام {msg_name} لغو شد.*"
    )

# ---------------------
# Send To One Messages
# ---------------------
async def send_msg_one(callback_query):
    messages = db.get_messages()

    if not messages:
        await callback_query.message.edit(
            "*هیچ پیامی ثبت نشده است.*"
        )
        return

    buttons = []

    for msg in messages:
        buttons.append([
            (
                msg[1],
                f"send_one_msg:{msg[0]}"
            )
        ])

    buttons.append([
        ('برگشت به منوی پیام ها', 'back_msg')
    ])

    await safe_answer(
        callback_query,
        "انتخاب پیام"
    )

    await callback_query.message.edit(
        "*پیام مورد نظر را انتخاب کنید:*",
        InlineKeyboard(*buttons)
    )


async def select_message_for_user(
        callback_query,
        message_id
):
    user_id = callback_query.author.id

    user_state[user_id]["selected_message_id"] = message_id
    user_state[user_id]["state"] = "waiting_target_user"

    await safe_answer(
        callback_query,
        "دریافت شناسه کاربر"
    )

    await callback_query.message.edit(
        "*شناسه کاربر مقصد را وارد کنید:*"
    )


async def confirm_send_one(callback_query):
    user_id = callback_query.author.id

    msg_id = user_state[user_id][
        "selected_message_id"
    ]

    target_user_id = user_state[user_id][
        "target_user_id"
    ]

    msg = db.get_message_by_id(msg_id)

    try:
        await send_saved_message(
            bot=callback_query.client,
            chat_id=target_user_id,
            msg=msg
        )

        await callback_query.message.edit(
            "*پیام با موفقیت ارسال شد.*"
        )

    except Exception as e:
        await callback_query.message.edit(
            f"خطا در ارسال:\n{e}"
        )

    user_state[user_id] = {"state": None}


async def cancel_send_one(callback_query):
    user_id = callback_query.author.id

    user_state[user_id] = {"state": None}

    await callback_query.message.edit(
        "*عملیات ارسال لغو شد.*"
    )

# ---------------------
# Send To All Messages
# ---------------------
async def send_msg_all(callback_query):
    messages = db.get_messages()

    if not messages:
        await callback_query.message.edit(
            "*هیچ پیامی ثبت نشده است.*"
        )
        return

    buttons = []

    for msg in messages:
        buttons.append([
            (
                msg[1],
                f"send_all_msg:{msg[0]}"
            )
        ])

    buttons.append([
        ('برگشت به منوی پیام ها', 'back_msg')
    ])

    await safe_answer(
        callback_query,
        "انتخاب پیام"
    )

    await callback_query.message.edit(
        "*پیام مورد نظر را انتخاب کنید:*",
        InlineKeyboard(*buttons)
    )


async def ask_send_all_confirm(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    if not msg:
        return

    await callback_query.message.edit(
        f"*آیا از ارسال پیام {msg[1]} برای همه کاربران اطمینان دارید؟*",
        InlineKeyboard(
            [('بله',
              f'confirm_send_all:{message_id}')],
            [('خیر',
              f'cancel_send_all:{message_id}')]
        )
    )


async def cancel_send_all(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    await callback_query.message.edit(
        f"*ارسال همگانی پیام {msg[1]} لغو شد.*"
    )


async def confirm_send_all(
        callback_query,
        message_id
):
    msg = db.get_message_by_id(message_id)

    if not msg:
        return

    users = db.get_all_active_users()

    success = 0
    failed = 0

    await callback_query.message.edit(
        "*ارسال پیام آغاز شد...*"
    )

    for user in users:
        chat_id = user[0]
        try:
            await send_saved_message(
                bot=callback_query.client,
                chat_id=chat_id,
                msg=msg
            )

            success += 1

        except Exception as e:
            if should_deactivate_user(str(e)):
                db.deactivate_user(chat_id)

            failed += 1
        await asyncio.sleep(0.2)

    await callback_query.message.edit(
        f"*ارسال پایان یافت*\n\n"
        f"موفق: {success}\n"
        f"ناموفق: {failed}\n"
        f"کل: {success + failed}"
    )

# ---------------------
# Preview Messages
# ---------------------
async def preview_messages(callback_query):
    messages = db.get_messages()

    if not messages:
        await safe_answer(
            callback_query,
            "پیامی وجود ندارد"
        )

        await callback_query.message.edit(
            "*هیچ پیامی ثبت نشده است.*"
        )
        return

    buttons = []

    for msg in messages:
        msg_id = msg[0]
        msg_name = msg[1]

        buttons.append([
            (
                msg_name,
                f"preview_message:{msg_id}"
            )
        ])

    buttons.append([
        ('برگشت به منوی پیام ها', 'back_msg')
    ])

    await safe_answer(
        callback_query,
        "پیش نمایش پیام"
    )

    await callback_query.message.edit(
        "*پیام مورد نظر را انتخاب کنید:*",
        InlineKeyboard(*buttons)
    )


async def preview_selected_message(callback_query, message_id):
    user_id = callback_query.author.id

    msg = db.get_message_by_id(message_id)

    if not msg:
        await safe_answer(callback_query, "پیام پیدا نشد")
        return

    await safe_answer(callback_query, "ارسال پیش نمایش")

    await send_saved_message(
        bot=callback_query.client,
        chat_id=user_id,
        msg=msg
    )


async def send_saved_message(bot, chat_id, msg):
    media_type = msg[2]
    file_id = msg[3]
    caption = msg[4]
    keyboard_json = msg[5]

    keyboard = make_msg_keyboard(keyboard_json)

    if media_type == "text":
        if keyboard:
            await bot.send_message(chat_id, caption, keyboard)
        else:
            await bot.send_message(chat_id, caption)

    elif media_type == "photo":
        if keyboard:
            await bot.send_photo(chat_id, file_id, caption, keyboard)
        else:
            await bot.send_photo(chat_id, file_id, caption=caption)

    elif media_type == "video":
        if keyboard:
            await bot.send_video(chat_id, file_id, caption, keyboard)
        else:
            await bot.send_video(chat_id, file_id, caption=caption)

    elif media_type == "audio":
        if keyboard:
            await bot.send_audio(chat_id, file_id, caption, keyboard)
        else:
            await bot.send_audio(chat_id, file_id, caption=caption)

    elif media_type == "document":
        if keyboard:
            await bot.send_document(chat_id, file_id, caption, keyboard)
        else:
            await bot.send_document(chat_id, file_id, caption=caption)


# ---------------------
# Keborad Setting
# ---------------------
async def msg_keyboard_no(callback_query):
    user_id = callback_query.author.id

    data = user_state[user_id]["message_data"]

    data["created_by"] = user_id

    try:
        message_id = db.add_message(data)

        user_state[user_id] = {"state": None}

        await safe_answer(callback_query, "ثبت پیام")
        await callback_query.message.edit(
            f"*پیام با موفقیت ذخیره شد.*\n\n"
            f"شناسه: {message_id}\n"
            f"نام: {data['name']}"
        )

    except sqlite3.IntegrityError:
        await callback_query.message.edit(
            "پیامی با این نام قبلاً ثبت شده است."
        )

    except Exception as e:
        await callback_query.message.edit(
            f"خطا در ذخیره پیام:\n{e}"
        )


async def msg_keyboard_yes(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["message_data"]["buttons"] = []
    user_state[user_id]["state"] = "waiting_msg_button_name"

    await safe_answer(callback_query, "افزودن دکمه")
    await callback_query.message.edit("*اسم دکمه را وارد کنید:*")


async def add_more_msg_button(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_msg_button_name"

    await safe_answer(callback_query, "افزودن دکمه جدید")
    await callback_query.message.edit("*اسم دکمه بعدی را وارد کنید:*")

 
async def finish_msg_buttons(callback_query):
    user_id = callback_query.author.id

    buttons = user_state[user_id]["message_data"].get("buttons", [])

    if buttons:
        keyboard_json = json.dumps(buttons, ensure_ascii=False)
    else:
        keyboard_json = None

    user_state[user_id]["message_data"]["keyboard_json"] = keyboard_json

    data = user_state[user_id]["message_data"]
    data["created_by"] = user_id

    try:
        message_id = db.add_message(data)

        user_state[user_id] = {"state": None}

        await safe_answer(callback_query, "ثبت پیام")
        await callback_query.message.edit(
            f"*پیام با موفقیت ذخیره شد.*\n\n"
            f"شناسه: {message_id}\n"
            f"نام: {data['name']}"
        )

    except sqlite3.IntegrityError:
        await callback_query.message.edit(
            "پیامی با این نام قبلاً ثبت شده است."
        )

    except Exception as e:
        await callback_query.message.edit(
            f"خطا در ذخیره پیام:\n{e}"
        )

# ---------------------
# Building Inline
# ---------------------
def make_msg_keyboard(keyboard_json):
    if not keyboard_json:
        return None
    raw_buttons = json.loads(keyboard_json)
    rows = []
    for row in raw_buttons:
        new_row = []
        for text, url in row:
            if url == 'start_menu':
                new_row.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data = url
                )
            )
                continue
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            new_row.append(
                InlineKeyboardButton(
                    text=text,
                    url=url
                )
            )
        rows.append(new_row)
    return InlineKeyboard(*rows)

# ---------------------
# Deactive Users
# ---------------------
def should_deactivate_user(error_text):
    deactivate_errors = (
        "bot was blocked by the user",
        "no such group or user",
        "chat not found",
        "user is deactivated"
    )

    return any(
        err in error_text.lower()
        for err in deactivate_errors
    )

# ---------------------
# Back Inline
# ---------------------
async def back_msg(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)

    user_state[user_id]["state"] = None

    await callback_query.message.edit(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('تنظیم پیام جدید', 'set_message'),
            ('حذف پیام', 'delete_message')],
            [('ارسال پیام به کاربر خاص', 'send_msg_one')],
            [('ارسال پیام به تمام کاربران', 'send_msg_all')],
            [('پیش نمایش پیام','preview_msg')],
            [('بستن', 'close')]
        )
    )

    await callback_query.answer("بازگشت به منوی اصلی")

MSG_CALLBACKS = {
    "set_message": set_new_message,
    "msg_keyboard_yes": msg_keyboard_yes,
    "msg_keyboard_no": msg_keyboard_no,
    "add_more_msg_button": add_more_msg_button,
    "finish_msg_buttons": finish_msg_buttons,

    "set_msg": set_new_message,
    "delete_message": delete_message,

     "send_msg_one": send_msg_one,
    "confirm_send_one": confirm_send_one,
    "cancel_send_one": cancel_send_one,

     "send_msg_all": send_msg_all,

    "preview_msg": preview_messages,

    "back_msg": back_msg,
}

MSG_DYNAMIC_CALLBACKS = {
    "preview_message": preview_selected_message,

    "delete_message": ask_delete_message_confirm,
    "confirm_delete_message": confirm_delete_message,
    "cancel_delete_message": cancel_delete_message,

    "send_one_msg": select_message_for_user,

    "send_all_msg": ask_send_all_confirm,
    "confirm_send_all": confirm_send_all,
    "cancel_send_all": cancel_send_all,
}

