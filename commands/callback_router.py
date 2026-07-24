from commands.ads import user_state
from Platform.bot_helpers import start_message, safe_answer_callback


async def handle_start_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    # با این کار مطمئن می‌شویم اگر کاربر در استیت خاصی بوده، کاملاً ریست می‌شود
    user_state[user_id] = {"state": None}

    if data.startswith("start_menu"):
        # ۱. لودینگ دکمه شیشه‌ای را می‌بندیم
        await safe_answer_callback(callback_query)

        # ۲. پیام فعلی (مثل لیست پیشنهادها) را حذف می‌کنیم تا صفحه شلوغ نشود
        try:
            await callback_query.message.delete()
        except Exception as e:
            print("Failed to delete message before returning to start menu:", e)

        # ۳. منوی عکس‌دار اصلی را دوباره می‌فرستیم
        await start_message(callback_query.message)
        return