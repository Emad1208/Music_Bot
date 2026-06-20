from balethon.objects import InlineKeyboard
from balethon.objects import InlineKeyboardButton
import json

# import sys
# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(BASE_DIR))

from db_Project.db_init import db


import sqlite3

user_state = {}

def init_user_state(user_id):
    if user_id not in user_state:
        user_state[user_id] = {"state": None}


async def safe_answer(callback_query, text=""):
    try:
        await callback_query.answer(text)
    except Exception as e:
        print("Callback answer ignored:", e)

# ---------------------
# Active ad poster
# ---------------------
async def active_ads(callback_query):
    ads = db.get_ads()

    inactive_ads = [ad for ad in ads if ad[5] == 0]

    if not inactive_ads:
        await safe_answer(callback_query, "تبلیغ غیرفعالی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغ غیرفعالی برای فعال کردن وجود ندارد.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "فعال کردن تبلیغ")
    await callback_query.message.edit(
        "*تبلیغ مورد نظر برای فعال شدن را انتخاب کنید:*",
        build_ads_list_keyboard(inactive_ads, "active_ad")
    )


async def ask_active_ad_confirm(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]

    await safe_answer(callback_query, "تأیید فعال‌سازی")
    await callback_query.message.edit(
        f"*آیا مطمئن هستید که می‌خواهید تبلیغ «{ad_name}» را فعال کنید؟*",
        InlineKeyboard(
            [('بله', f'confirm_active_ad:{ad_id}')],
            [('خیر', f'cancel_active_ad:{ad_id}')]
        )
    )


async def confirm_active_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]
    updated = db.update_ad_active_status(ad_id, 1)

    await safe_answer(callback_query, "فعال شد")

    if updated:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» فعال شد.*"
        )
    else:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» فعال نشد.*"
        )


async def cancel_active_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)
    ad_name = ad[1] if ad else "نامشخص"

    await safe_answer(callback_query, "لغو شد")
    await callback_query.message.edit(
        f"*فعال کردن تبلیغ «{ad_name}» لغو شد.*"
    )

# ---------------------
# Deactive ad poster
# ---------------------
async def deactive_ads(callback_query):
    ads = db.get_ads()

    active_ads = [ad for ad in ads if ad[5] == 1]

    if not active_ads:
        await safe_answer(callback_query, "تبلیغ فعالی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغ فعالی برای غیرفعال کردن وجود ندارد.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "غیرفعال کردن تبلیغ")
    await callback_query.message.edit(
        "*تبلیغ مورد نظر برای غیرفعال شدن را انتخاب کنید:*",
        build_ads_list_keyboard(active_ads, "deactive_ad")
    )


async def ask_deactive_ad_confirm(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]

    await safe_answer(callback_query, "تأیید غیرفعال‌سازی")
    await callback_query.message.edit(
        f"*آیا مطمئن هستید که می‌خواهید تبلیغ «{ad_name}» را غیرفعال کنید؟*",
        InlineKeyboard(
            [('بله', f'confirm_deactive_ad:{ad_id}')],
            [('خیر', f'cancel_deactive_ad:{ad_id}')]
        )
    )


async def confirm_deactive_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]
    updated = db.update_ad_active_status(ad_id, 0)

    await safe_answer(callback_query, "غیرفعال شد")

    if updated:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» غیرفعال شد.*"
        )
    else:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» غیرفعال نشد.*"
        )


async def cancel_deactive_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)
    ad_name = ad[1] if ad else "نامشخص"

    await safe_answer(callback_query, "لغو شد")
    await callback_query.message.edit(
        f"*غیرفعال کردن تبلیغ «{ad_name}» لغو شد.*"
    )

# ---------------------
# Setting Value poster
# ---------------------
async def set_value_ads(callback_query):
    ads = db.get_ads()

    if not ads:
        await safe_answer(callback_query, "تبلیغی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغی ثبت نشده است.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "نمایش تعداد ارسال")
    await callback_query.message.edit(
        "*تبلیغ مورد نظر را انتخاب کنید:*",
        build_ads_list_keyboard(ads, "set_value_ad")
    )


async def ask_new_ad_value(callback_query, ad_id):
    user_id = callback_query.author.id
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    user_state[user_id] = {
        "state": "waiting_new_ad_value",
        "set_value_ad_id": ad_id,
        "set_value_ad_name": ad[1]
    }

    await safe_answer(callback_query, "مقدار جدید")
    await callback_query.message.edit(
        f"*مقدار جدید ارسال برای تبلیغ «{ad[1]}» را وارد کنید:*"
    )


async def confirm_set_value_ad(callback_query):
    user_id = callback_query.author.id

    ad_id = user_state[user_id]["set_value_ad_id"]
    new_value = user_state[user_id]["new_ad_value"]
    ad_name = user_state[user_id]["set_value_ad_name"]

    updated = db.update_ad_max_send(ad_id, new_value)

    user_state[user_id] = {"state": None}

    await safe_answer(callback_query, "تغییر اعمال شد")

    if updated:
        await callback_query.message.edit(
            f"*مقدار ارسال پوستر «{ad_name}» به {new_value} تغییر پیدا کرد.*"
        )
    else:
        await callback_query.message.edit(
            "*تغییر انجام نشد.*"
        )


async def cancel_set_value_ad(callback_query):
    user_id = callback_query.author.id
    ad_name = user_state[user_id].get("set_value_ad_name", "نامشخص")

    user_state[user_id] = {"state": None}

    await safe_answer(callback_query, "لغو تغییر")
    await callback_query.message.edit(
        f"*تغییرات برای تبلیغ «{ad_name}» لحاظ نشد.*"
    )

# ---------------------
# Show Value poster
# ---------------------
async def show_value_ads(callback_query):
    ads = db.get_ads()

    if not ads:
        await safe_answer(callback_query, "تبلیغی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغی ثبت نشده است.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "نمایش تعداد ارسال")
    await callback_query.message.edit(
        "*تبلیغ مورد نظر را انتخاب کنید:*",
        build_ads_list_keyboard(ads, "show_value_ad")
    )


async def show_selected_ad_value(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    name = ad[1]
    max_send = ad[6]
    sent_count = ad[7]
    is_active = ad[8]

    remaining = max_send - sent_count
    if remaining < 0:
        remaining = 0
    if is_active == 0:
        status = 'Deactive'
    if is_active == 1 :
        status = 'Active'
    await safe_answer(callback_query, "آمار تبلیغ")

    await callback_query.message.edit(
        f"*آمار تبلیغ: {name}*\n\n"
        f"Set Value : {max_send}\n"
        f"Send Number : {sent_count}\n"
        f"Remaining Number : {remaining}\n"
        f"*Status : {status}*",
        InlineKeyboard(
            [('برگشت به لیست تبلیغات', 'show_value')],
            [('برگشت به منوی اصلی', 'back')]
        )
    )

# ---------------------
# Setting poster
# ---------------------
async def set_poster_ads(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)
    user_state[user_id]["state"] = "waiting_ad_poster"

    await safe_answer(callback_query, "اضافه کردن پوستر تبلیغاتی")
    await callback_query.message.edit(
        "*لطفا پوستر تبلیغاتی مورد نظر را ارسال کنید*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        )
    )

# ---------------------
# Deletinh poster
# ---------------------
async def delete_poster_ads(callback_query):
    ads = db.get_ads()

    if not ads:
        await safe_answer(callback_query, "تبلیغی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغی برای حذف وجود ندارد.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "حذف تبلیغ")
    await callback_query.message.edit(
        "*تبلیغ مورد نظر برای حذف را انتخاب کنید:*",
        build_ads_list_keyboard(ads, "delete_ad")
    )


async def ask_delete_ad_confirm(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]

    await safe_answer(callback_query, "تأیید حذف")
    await callback_query.message.edit(
        f"*آیا از حذف تبلیغ «{ad_name}» مطمئن هستید؟*",
        InlineKeyboard(
            [('بله', f'confirm_delete_ad:{ad_id}')],
            [('خیر', f'cancel_delete_ad:{ad_id}')]
        )
    )


async def confirm_delete_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    ad_name = ad[1]
    deleted = db.delete_ad_by_id(ad_id)

    await safe_answer(callback_query, "حذف تبلیغ")

    if deleted:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» با موفقیت حذف شد.*"
        )
    else:
        await callback_query.message.edit(
            f"*تبلیغ «{ad_name}» حذف نشد.*"
        )


async def cancel_delete_ad(callback_query, ad_id):
    ad = db.get_ad_by_id(ad_id)

    if ad:
        ad_name = ad[1]
    else:
        ad_name = "نامشخص"

    await safe_answer(callback_query, "لغو حذف")
    await callback_query.message.edit(
        f"*عملیات حذف تبلیغ «{ad_name}» لغو شد.*"
    )

# ---------------------
# Preview poster ads
# ---------------------
async def preview_ads(callback_query):
    ads = db.get_ads()

    if not ads:
        await safe_answer(callback_query, "تبلیغی وجود ندارد")
        await callback_query.message.edit("*هیچ تبلیغی ثبت نشده است.*",InlineKeyboard(
            [('برگشت به منوی اصلی', 'back')]
        ))
        return

    await safe_answer(callback_query, "پیش نمایش تبلیغ")
    await callback_query.message.edit(
        "*یکی از تبلیغات را انتخاب کنید:*",
        build_ads_list_keyboard(ads, "preview_ad")
    )


async def preview_selected_ad(callback_query, ad_id):
    user_id = callback_query.author.id

    ad = db.get_ad_by_id(ad_id)

    if not ad:
        await safe_answer(callback_query, "تبلیغ پیدا نشد")
        return

    await safe_answer(callback_query, "ارسال پیش‌نمایش")

    await send_ad_to_user(
        bot=callback_query.client,
        chat_id=user_id,
        ad=ad
    )

# ---------------------
# Close Inline
# ---------------------
async def close_ads(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)
    user_state[user_id]["state"] = "close"

    await safe_answer(callback_query, "بستن صفحه")
    await callback_query.message.edit("*صفحه بسته شد*")

# ---------------------
# Back Inline
# ---------------------
async def back_ads(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)

    user_state[user_id]["state"] = None

    await callback_query.message.edit(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('فعال کردن', 'active'), ('غیرفعال کردن', 'deactive')],
            [('تنظیم تعداد ارسال', 'set_value'),
             ('نمایش تعداد ارسال شده', 'show_value')],
            [('تنظیم محتوای ارسالی', 'set_poster'),
             ('حذف محتوای ارسالی', 'delete_poster')],
             [('پیش نمایش تیلیغ', 'preview')],
            [('بستن', 'close')]
        )
    )

    await callback_query.answer("بازگشت به منوی اصلی")

# ---------------------
# Keborad Setting
# ---------------------
async def add_more_button(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_button_name"

    await safe_answer(callback_query, "افزودن دکمه جدید")
    await callback_query.message.edit("*اسم دکمه بعدی را وارد کنید:*")


async def finish_ad_buttons(callback_query):
    user_id = callback_query.author.id

    buttons = user_state[user_id]["ad_data"].get("buttons", [])

    if buttons:
        keyboard_json = json.dumps(buttons, ensure_ascii=False)
    else:
        keyboard_json = None

    user_state[user_id]["ad_data"]["keyboard_json"] = keyboard_json

    ad_data = user_state[user_id]["ad_data"]
    ad_data["created_by"] = user_id

    try:
        ad_id = db.add_ads(ad_data)

        user_state[user_id] = {"state": None}

        await safe_answer(callback_query, "ثبت تبلیغ")
        await callback_query.message.edit(
            f"*تبلیغ با موفقیت ذخیره شد.*\n\n"
            f"شناسه: {ad_id}\n"
            f"نام: {ad_data['name']}"
        )

    except sqlite3.IntegrityError:
        await callback_query.message.edit(
            "تبلیغی با این نام قبلاً ثبت شده است."
        )

    except Exception as e:
        await callback_query.message.edit(
            f"خطا در ذخیره تبلیغ:\n{e}"
        )


async def ad_keyboard_yes(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)

    user_state[user_id]["state"] = "waiting_button_name"

    await safe_answer(callback_query, "افزودن دکمه")
    await callback_query.message.edit("*اسم دکمه را وارد کنید:*")


async def ad_keyboard_no(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)

    user_state[user_id]["ad_data"]["keyboard_json"] = None

    ad_data = user_state[user_id]["ad_data"]
    ad_data["created_by"] = user_id

    try:
        ad_id = db.add_ads(ad_data)

        user_state[user_id] = {"state": None}

        await safe_answer(callback_query, "ثبت تبلیغ")
        await callback_query.message.edit(
            f"*تبلیغ با موفقیت ذخیره شد.*\n\n"
            f"شناسه: {ad_id}\n"
            f"نام: {ad_data['name']}"
        )

    except sqlite3.IntegrityError:
        await callback_query.message.edit(
            "تبلیغی با این نام قبلاً ثبت شده است."
        )

    except Exception as e:
        await callback_query.message.edit(
            f"خطا در ذخیره تبلیغ:\n{e}"
        )

# ---------------------
# Building Inline
# ---------------------
def build_ads_list_keyboard(ads, action):
    buttons = []

    for ad in ads:
        ad_id = ad[0]
        name = ad[1]

        text = f"{name} | Ad ID : {ad_id}"
        data = f"{action}:{ad_id}"

        buttons.append([(text, data)])

    buttons.append([("برگشت به منوی اصلی", "back")])

    return InlineKeyboard(*buttons)


def make_ad_keyboard(keyboard_json):
    print("KEYBOARD JSON =", keyboard_json)
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
# Sending ads to users
# ---------------------
async def send_ad_to_user(bot, chat_id, ad):
    media_type = ad[2]
    file_id = ad[3]
    caption = ad[4]
    keyboard_json = ad[5]

    keyboard = make_ad_keyboard(keyboard_json)

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




CALLBACKS = {
    "active": active_ads,

    "deactive": deactive_ads,

    "set_value": set_value_ads,
    'set_poster': set_poster_ads,
    "confirm_set_value_ad": confirm_set_value_ad,
    "cancel_set_value_ad": cancel_set_value_ad,

    'show_value': show_value_ads,

    'delete_poster': delete_poster_ads,

    'close': close_ads,

    'back': back_ads,

    'preview': preview_ads,

    'add_more_button': add_more_button,
    'finish_ad_buttons': finish_ad_buttons,

    "ad_keyboard_yes": ad_keyboard_yes,
    "ad_keyboard_no": ad_keyboard_no,
    
}


DYNAMIC_CALLBACKS = {
    "preview_ad": preview_selected_ad,

    "delete_ad": ask_delete_ad_confirm,
    "confirm_delete_ad": confirm_delete_ad,
    "cancel_delete_ad": cancel_delete_ad,

    "show_value_ad": show_selected_ad_value,

    "set_value_ad": ask_new_ad_value,

    "deactive_ad": ask_deactive_ad_confirm,
    "confirm_deactive_ad": confirm_deactive_ad,
    "cancel_deactive_ad": cancel_deactive_ad,

    "active_ad": ask_active_ad_confirm,
    "confirm_active_ad": confirm_active_ad,
    "cancel_active_ad": cancel_active_ad,
}