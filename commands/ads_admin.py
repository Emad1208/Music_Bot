from .ads import user_state

from balethon.objects import InlineKeyboard


async def receive_ad_poster(message):
    user_id = message.author.id

    media_type = None
    file_id = None
    caption = getattr(message, "caption", None)

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].id
        # await message.reply(file_id)

    elif message.video:
        media_type = "video"
        file_id = message.video.id
        # await message.reply(file_id)

    elif message.document:
        media_type = "document"
        file_id = message.document.id
        # await message.reply(file_id)

    elif message.audio:
        media_type = "audio"
        file_id = message.audio.id
        # await message.reply(file_id)

    elif message.text:
        media_type = "text"
        caption = message.text
        # await message.reply(caption)

    else:
        await message.reply("نوع پیام پشتیبانی نمی‌شود.")
        return

    user_state[user_id]["ad_data"] = {
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
        "keyboard_json": None
    }

    user_state[user_id]["state"] = "waiting_ad_name"

    await message.reply("*اسم تبلیغ را وارد کنید:*")


async def receive_ad_name(message):
    user_id = message.author.id
    ad_name = message.text.strip()

    user_state[user_id]["ad_data"]["name"] = ad_name
    user_state[user_id]["state"] = "waiting_ad_max_send"

    await message.reply("*تعداد ارسال تبلیغ را وارد کنید:*")


async def receive_ad_max_send(message):
    user_id = message.author.id

    if not message.text.isdigit():
        await message.reply("عدد معتبر وارد کنید.")
        return

    user_state[user_id]["ad_data"]["max_send"] = int(message.text)
    user_state[user_id]["ad_data"]["buttons"] = []
    user_state[user_id]["state"] = "waiting_keyboard_choice"

    await message.reply(
        "*آیا می‌خواهید این تبلیغ دکمه داشته باشد؟*",
        InlineKeyboard(
            [('بله', 'ad_keyboard_yes')],
            [('نه', 'ad_keyboard_no')]
        )
    )


async def receive_button_name_ad(message):
    user_id = message.author.id

    button_name = message.text.strip()

    if not button_name:
        await message.reply("نام دکمه نمی‌تواند خالی باشد.")
        return

    if len(button_name) > 50:
        await message.reply("نام دکمه بیش از حد طولانی است.")
        return

    user_state[user_id]["ad_data"]["button_name"] = button_name
    user_state[user_id]["state"] = "waiting_button_url"

    await message.reply("*لینک دکمه را وارد کنید:*")


async def receive_button_url_ad(message):
    user_id = message.author.id
    url = message.text.strip()

    button_name = user_state[user_id]["ad_data"].pop("button_name")

    user_state[user_id]["ad_data"]["buttons"].append(
        [(button_name, url)]
    )

    user_state[user_id]["state"] = "waiting_more_button"

    await message.reply(
        "*دکمه دیگری اضافه شود؟*",
        InlineKeyboard(
            [('بله', 'add_more_button'),
            ('نه', 'finish_ad_buttons')]
        )
    )


async def receive_new_ad_value(message):
    user_id = message.author.id
    text = message.text.strip()

    if not text.isdigit():
        await message.reply("عدد معتبر وارد کنید.")
        return

    new_value = int(text)
    ad_name = user_state[user_id]["set_value_ad_name"]

    user_state[user_id]["new_ad_value"] = new_value
    user_state[user_id]["state"] = "waiting_confirm_new_ad_value"

    await message.reply(
        f"*آیا مطمئن هستید که مقدار ارسال پوستر «{ad_name}» "
        f"به مقدار {new_value} تغییر پیدا کند؟*",
        InlineKeyboard(
            [('بله', 'confirm_set_value_ad')],
            [('خیر', 'cancel_set_value_ad')]
        )
    )


