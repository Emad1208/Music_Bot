import sqlite3
from urllib.parse import urlparse

from balethon.enums import ChatMemberStatus
from balethon.objects import InlineKeyboard, InlineKeyboardButton

from db_Project.db_init import db

from .ads import init_user_state, safe_answer, user_state


ACCEPTED_MEMBER_STATUSES = (
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
)


def _channel_menu_keyboard():
    return InlineKeyboard(
        [("تنظیم کانال عضویت اجباری", "channel_set")],
        [("حذف کانال عضویت اجباری", "channel_delete")],
        [("نمایش لیست کانال‌ها", "channel_list")],
        [("بستن", "channel_close")],
    )


def _channel_join_url(channel_name):
    channel_name = channel_name.strip()

    if channel_name.startswith(("http://", "https://")):
        parsed = urlparse(channel_name)
        return channel_name if parsed.netloc else None

    username = channel_name.lstrip("@").strip()
    if username and not any(character.isspace() for character in username):
        return f"https://ble.ir/{username}"

    return None


def _membership_prompt(missing_channels):
    text = (
        "*برای استفاده از بازو ابتدا در کانال‌های زیر عضو شوید:*\n"
        "بعد از عضویت، دکمه «بررسی عضویت» را بزنید."
    )

    rows = []
    for channel in missing_channels:
        join_url = _channel_join_url(channel["username"] or channel["name"])
        if join_url:
            rows.append([
                InlineKeyboardButton(
                    text=f"عضویت در {channel['name']}",
                    url=join_url,
                )
            ])

    rows.append([("بررسی عضویت", "channel_check_membership")])
    return text, InlineKeyboard(*rows)


async def _get_missing_channels(event):
    user_id = event.author.id
    if db.is_admin(user_id):
        return []

    required_channels = db.get_required_channels()
    if not required_channels:
        return []

    client = event.client
    missing_channels = []

    for channel in required_channels:
        try:
            member = await client.get_chat_member(
                channel["channel_id"],
                user_id,
            )
            is_joined = (
                member.is_member is True
                or member.status in ACCEPTED_MEMBER_STATUSES
            )
        except Exception as error:
            print(
                "Required channel membership check failed:",
                channel["channel_id"],
                error,
            )
            is_joined = False

        if not is_joined:
            missing_channels.append(channel)

    return missing_channels


async def ensure_required_channel_membership(event):
    missing_channels = await _get_missing_channels(event)
    if not missing_channels:
        return True

    text, keyboard = _membership_prompt(missing_channels)

    if hasattr(event, "data"):
        await safe_answer(event, "ابتدا در کانال‌ها عضو شوید")
        await event.message.reply(text, keyboard)
    else:
        await event.reply(text, keyboard)

    return False


async def channel_command(message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply("شما دسترسی به این بخش را ندارید.")
        return

    user_state[user_id] = {"state": None}
    await message.reply(
        "*مدیریت کانال‌های عضویت اجباری*",
        _channel_menu_keyboard(),
    )


async def start_setting_channel(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)
    user_state[user_id] = {"state": "waiting_required_channel_name"}

    await safe_answer(callback_query, "تنظیم کانال")
    await callback_query.message.edit(
        "*نام کانال را ارسال کنید.*\n\n"
        "توجه: بازو باید در کانال ادمین باشد تا بتواند عضویت کاربران را بررسی کند."
    )


async def receive_channel_name(message):
    user_id = message.author.id
    channel_name = (message.text or "").strip()

    if not channel_name:
        await message.reply("نام کانال نمی‌تواند خالی باشد.")
        return

    if len(channel_name) > 200:
        await message.reply("نام کانال بیش از حد طولانی است.")
        return

    user_state[user_id]["required_channel_name"] = channel_name
    user_state[user_id]["state"] = "waiting_required_channel_username"
    await message.reply("*حالا آیدی کانال را ارسال کنید؛ برای نمونه:* `@example`")


async def receive_channel_username(message):
    user_id = message.author.id
    channel_username = (message.text or "").strip()

    is_valid_username = (
        channel_username.startswith("@")
        and len(channel_username) > 1
        and all(
            character.isascii()
            and (character.isalnum() or character == "_")
            for character in channel_username[1:]
        )
    )

    if not is_valid_username:
        await message.reply(
            "آیدی کانال معتبر نیست. آن را مانند `@example` و فقط با حروف "
            "انگلیسی، عدد یا زیرخط ارسال کنید."
        )
        return

    user_state[user_id]["required_channel_username"] = channel_username
    user_state[user_id]["state"] = "waiting_required_channel_id"
    await message.reply("*حالا شناسه عددی کانال را ارسال کنید:*")


async def receive_channel_id(message):
    user_id = message.author.id
    channel_id_text = (message.text or "").strip()

    try:
        channel_id = int(channel_id_text)
    except (TypeError, ValueError):
        await message.reply("شناسه کانال باید یک عدد معتبر باشد.")
        return

    if channel_id == 0:
        await message.reply("شناسه صفر معتبر نیست.")
        return

    channel_name = user_state[user_id].get("required_channel_name")
    channel_username = user_state[user_id].get("required_channel_username")
    if not channel_name or not channel_username:
        user_state[user_id] = {"state": None}
        await message.reply(
            "اطلاعات کانال کامل نیست. لطفاً دوباره دستور /channel را اجرا کنید."
        )
        return

    user_state[user_id]["required_channel_id"] = channel_id
    user_state[user_id]["state"] = None

    await message.reply(
        "*آیا مطمئن هستید کانال زیر برای بازو تنظیم شود؟*\n\n"
        f"نام کانال: {channel_name}\n"
        f"آیدی کانال: `{channel_username}`\n"
        f"شناسه عددی: `{channel_id}`",
        InlineKeyboard(
            [("بله", "channel_confirm_set")],
            [("خیر", "channel_cancel_set")],
        ),
    )


async def confirm_setting_channel(callback_query):
    user_id = callback_query.author.id
    state = user_state.get(user_id, {})
    channel_name = state.get("required_channel_name")
    channel_username = state.get("required_channel_username")
    channel_id = state.get("required_channel_id")

    if not channel_name or not channel_username or channel_id is None:
        await safe_answer(callback_query, "اطلاعات کانال پیدا نشد")
        await callback_query.message.edit(
            "*اطلاعات کانال منقضی شده است. دوباره /channel را اجرا کنید.*"
        )
        return

    try:
        db.add_required_channel(
            channel_name,
            channel_username,
            channel_id,
            user_id,
        )
    except sqlite3.IntegrityError:
        await safe_answer(callback_query, "این کانال قبلاً ثبت شده است")
        await callback_query.message.edit(
            f"*کانال «{channel_name}» با آیدی `{channel_username}` یا شناسه "
            f"`{channel_id}` قبلاً ثبت شده است.*",
            InlineKeyboard([("برگشت", "channel_back")]),
        )
        return

    user_state[user_id] = {"state": None}
    await safe_answer(callback_query, "کانال ثبت شد")
    await callback_query.message.edit(
        f"*کانال «{channel_name}» با آیدی `{channel_username}` و شناسه "
        f"`{channel_id}` با موفقیت تنظیم شد.*\n\n"
        "بازو باید در این کانال ادمین باشد.",
        InlineKeyboard([("برگشت", "channel_back")]),
    )


async def cancel_setting_channel(callback_query):
    user_id = callback_query.author.id
    user_state[user_id] = {"state": None}

    await safe_answer(callback_query, "تنظیم کانال لغو شد")
    await callback_query.message.edit(
        "*تنظیم کانال لغو شد.*",
        InlineKeyboard([("برگشت", "channel_back")]),
    )


def _channels_keyboard(channels):
    rows = [
        [
            (
                f"{channel['name']} | {channel['username'] or channel['name']}",
                f"channel_select_delete:{channel['id']}",
            )
        ]
        for channel in channels
    ]
    rows.append([("برگشت", "channel_back")])
    return InlineKeyboard(*rows)


async def show_channels(callback_query):
    channels = db.get_required_channels()

    await safe_answer(callback_query, "لیست کانال‌ها")
    if not channels:
        await callback_query.message.edit(
            "*هیچ کانال عضویت اجباری ثبت نشده است.*",
            InlineKeyboard([("برگشت", "channel_back")]),
        )
        return

    channel_details = []
    for index, channel in enumerate(channels, start=1):
        channel_details.append(
            f"*{index}. {channel['name']}*\n"
            f"آیدی کانال: `{channel['username'] or channel['name']}`\n"
            f"شناسه عددی: `{channel['channel_id']}`"
        )

    await callback_query.message.edit(
        "*لیست کانال‌های عضویت اجباری:*\n\n"
        + "\n\n".join(channel_details),
        InlineKeyboard([("برگشت", "channel_back")]),
    )


async def show_channels_for_delete(callback_query):
    channels = db.get_required_channels()

    await safe_answer(callback_query, "حذف کانال")
    if not channels:
        await callback_query.message.edit(
            "*هیچ کانال عضویت اجباری ثبت نشده است.*",
            InlineKeyboard([("برگشت", "channel_back")]),
        )
        return

    await callback_query.message.edit(
        "*کانالی را که می‌خواهید حذف شود انتخاب کنید:*",
        _channels_keyboard(channels),
    )


async def ask_delete_channel_confirm(callback_query, required_channel_id):
    channel = db.get_required_channel_by_id(required_channel_id)
    if not channel:
        await safe_answer(callback_query, "کانال پیدا نشد")
        await callback_query.message.edit(
            "*این کانال دیگر وجود ندارد.*",
            InlineKeyboard([("برگشت", "channel_delete")]),
        )
        return

    await safe_answer(callback_query, "تأیید حذف کانال")
    await callback_query.message.edit(
        f"*آیا مطمئن هستید کانال «{channel['name']}» حذف شود؟*",
        InlineKeyboard(
            [("بله", f"channel_confirm_delete:{channel['id']}")],
            [("خیر", f"channel_cancel_delete:{channel['id']}")],
        ),
    )


async def confirm_delete_channel(callback_query, required_channel_id):
    channel = db.get_required_channel_by_id(required_channel_id)
    if not channel:
        await safe_answer(callback_query, "کانال پیدا نشد")
        await callback_query.message.edit(
            "*این کانال قبلاً حذف شده است.*",
            InlineKeyboard([("برگشت", "channel_delete")]),
        )
        return

    deleted = db.delete_required_channel(required_channel_id)
    await safe_answer(callback_query, "کانال حذف شد" if deleted else "حذف انجام نشد")
    await callback_query.message.edit(
        (
            f"*کانال «{channel['name']}» با موفقیت حذف شد.*"
            if deleted
            else f"*حذف کانال «{channel['name']}» انجام نشد.*"
        ),
        InlineKeyboard([("برگشت به فهرست", "channel_delete")]),
    )


async def cancel_delete_channel(callback_query, required_channel_id):
    channel = db.get_required_channel_by_id(required_channel_id)
    channel_name = channel["name"] if channel else "نامشخص"

    await safe_answer(callback_query, "حذف کانال لغو شد")
    await callback_query.message.edit(
        f"*حذف کانال «{channel_name}» لغو شد.*",
        InlineKeyboard([("برگشت به فهرست", "channel_delete")]),
    )


async def back_to_channel_menu(callback_query):
    user_id = callback_query.author.id
    user_state[user_id] = {"state": None}

    await safe_answer(callback_query, "بازگشت")
    await callback_query.message.edit(
        "*مدیریت کانال‌های عضویت اجباری*",
        _channel_menu_keyboard(),
    )


async def close_channel_menu(callback_query):
    user_id = callback_query.author.id
    user_state[user_id] = {"state": None}

    await safe_answer(callback_query, "بستن صفحه")
    await callback_query.message.edit("*صفحه مدیریت کانال بسته شد.*")


async def check_membership_callback(callback_query):
    missing_channels = await _get_missing_channels(callback_query)

    if missing_channels:
        text, keyboard = _membership_prompt(missing_channels)
        await safe_answer(callback_query, "عضویت شما هنوز کامل نیست")
        await callback_query.message.edit(text, keyboard)
        return

    await safe_answer(callback_query, "عضویت تأیید شد")
    await callback_query.message.edit(
        "*عضویت شما تأیید شد. اکنون می‌توانید از بازو استفاده کنید.*",
        InlineKeyboard([("شروع کار با بازو", "start_menu")]),
    )


CHANNEL_CALLBACKS = {
    "channel_set": start_setting_channel,
    "channel_confirm_set": confirm_setting_channel,
    "channel_cancel_set": cancel_setting_channel,
    "channel_delete": show_channels_for_delete,
    "channel_list": show_channels,
    "channel_back": back_to_channel_menu,
    "channel_close": close_channel_menu,
}


CHANNEL_DYNAMIC_CALLBACKS = {
    "channel_select_delete": ask_delete_channel_confirm,
    "channel_confirm_delete": confirm_delete_channel,
    "channel_cancel_delete": cancel_delete_channel,
}


CHANNEL_ADMIN_HANDLERS = {
    "waiting_required_channel_name": receive_channel_name,
    "waiting_required_channel_username": receive_channel_username,
    "waiting_required_channel_id": receive_channel_id,
}


def is_channel_setup_state(state):
    return state in CHANNEL_ADMIN_HANDLERS


async def handle_channel_callback(callback_query):
    data = callback_query.data

    if data == "channel_check_membership":
        await check_membership_callback(callback_query)
        return True

    handler = CHANNEL_CALLBACKS.get(data)
    value = None

    if handler is None and ":" in data:
        action, raw_value = data.split(":", 1)
        handler = CHANNEL_DYNAMIC_CALLBACKS.get(action)
        if handler:
            try:
                value = int(raw_value)
            except ValueError:
                await safe_answer(callback_query, "درخواست نامعتبر است")
                return True

    if handler is None:
        return False

    if not db.is_admin(callback_query.author.id):
        await safe_answer(callback_query, "شما دسترسی ندارید")
        await callback_query.message.reply("شما دسترسی به این بخش را ندارید.")
        return True

    if value is None:
        await handler(callback_query)
    else:
        await handler(callback_query, value)

    return True
