from balethon.objects import InlineKeyboard

from db_Project.db_init import db


def build_source_report():
    rows = db.get_all_source_stats()

    if not rows:
        return "📊 هنوز آماری برای سایت‌ها ثبت نشده."

    text = "📊 گزارش سرعت منابع آهنگ\n\n"

    for row in rows:
        source, dl, up, success, fail, rate, last_update = row

        download = f"{dl:.2f} MB/s" if dl else "--"
        upload = f"{up:.2f} MB/s" if up else "--"

        text += (
            f"🌐 منبع: {source}\n"
            f"⬇️ سرعت دانلود: {download}\n"
            f"⬆️ سرعت آپلود به بله: {upload}\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {fail}\n"
            f"📈 نرخ موفقیت: {rate * 100:.0f}%\n"
            f"🕒 آخرین بروزرسانی: {last_update}\n"
            f"──────────────\n"
        )

    return text


def build_bot_report():
    text = (
        "📊 گزارش ربات\n\n"

        "━━━━━━━━━━━━━━\n"
        "👥 کاربران\n"
        "━━━━━━━━━━━━━━\n"
        f"👤 کل کاربران: {db.get_users_count()}\n"
        f"🟢 کاربران فعال: {db.get_active_users_count()}\n"
        f"🔴 کاربران غیرفعال: {db.get_users_count() - db.get_active_users_count()}\n"
        f"👮 ادمین‌ها: {db.get_admins_count()}\n\n"

        "━━━━━━━━━━━━━━\n"
        "🎵 موسیقی\n"
        "━━━━━━━━━━━━━━\n"
        f"🎼 آهنگ‌های ذخیره شده: {db.get_musics_count()}\n"
        f"📤 کل آهنگ‌های ارسال شده: {db.get_sended_musics_count()}\n\n"

        "━━━━━━━━━━━━━━\n"
        "📢 تبلیغات\n"
        "━━━━━━━━━━━━━━\n"
        f"📣 کل تبلیغات: {db.get_ads_count()}\n"
        f"🟢 تبلیغات فعال: {db.get_active_ads_count()}\n"
        f"🔴 تبلیغات غیرفعال: {db.get_ads_count() - db.get_active_ads_count()}\n\n"

        "━━━━━━━━━━━━━━\n"
        "✉️ پیام‌ها\n"
        "━━━━━━━━━━━━━━\n"
        f"💬 پیام‌های ذخیره شده: {db.get_messages_count()}"
    )

    return text


async def show_bot_report(callback_query):
    await callback_query.message.edit(
        build_bot_report(),
        InlineKeyboard(
            [('برگشت', 'back_report')]
        )
    )


async def show_source_report(callback_query):
    await callback_query.message.edit(
        build_source_report(),
        InlineKeyboard(
            [('برگشت', 'back_report')]
        )
    )


async def back_report(callback_query):
    await callback_query.message.edit(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('نمایش گزارش ربات', 'show_bot_rep')],
            [('نمایش گزارش وضعیت منبع', 'show_source_rep')],

            [('بستن', 'close')]
        )
    )



REPO_CALLBACK = {
    "show_bot_rep": show_bot_report,
    "show_source_rep": show_source_report,
    "back_report": back_report,
}