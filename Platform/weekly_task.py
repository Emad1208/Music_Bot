import asyncio
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from balethon.objects import InlineKeyboard

from db_Project.db_init import db

async def send_weekly_top_musics(bot):
    print("Executing Weekly Top 10 task...")
    try:
        # 1. Clean up database records older than 30 days
        deleted_rows = db.cleanup_old_history(days=30)
        print(f"DB Cleanup: Deleted {deleted_rows} old history records.")

        # 2. Extract the top 10 most downloaded tracks
        top_musics = db.get_weekly_top_musics(limit=10)
        if not top_musics:
            print("No musics found for this week.")
            return

        # 3. Save titles in settings to ensure inline buttons remain functional
        titles = [row["title"] for row in top_musics]
        db.set_setting("weekly_top_10", json.dumps(titles))

        # 4. Build the announcement text and inline keyboard buttons
        text = "🎵 این هفته همه چی گوش میدن؟ 🎵\n🔥 این لیست، ۱۰ آهنگیه که *بیشترین دانلود* رو بین کاربران ملودی یار داشته 🔥:\n\n*فقط کافیه روی اسم آهنگ موردنظرت کلیک کنی*"
        buttons = []
        for i, title in enumerate(titles):
            buttons.append([(f"🎧 {title[:30]} 🎧", f"weektp:{i}")])
        
        markup = InlineKeyboard(*buttons)

        # 5. Broadcast the message to all active users
        users = db.get_all_active_users()
        success_count = 0
        for user in users:
            user_id = user[0]
            try:
                await bot.send_video(
                    video = '962702339:5656250797157523203:0:cfe1f8543d7fe5581e76276b2d940c7e9332d64381b494e8014eb5342f463e77a3ba95a1013da9e56b5055903f4e4f6b220dbf5ee590e009',
                    chat_id = user_id,
                    caption = text,
                    reply_markup=markup)
                success_count += 1
            except Exception:
                print(f"Failed to send weekly top 10 to user {user_id}.")
                pass
            # Short delay to prevent flooding and bot blocking
            await asyncio.sleep(0.05) 

        # 6. Send summary report to all bot administrators
        admins = db.get_admins()
        for admin in admins:
            admin_id = admin["user_id"]
            try:
                await bot.send_message(
                    admin_id, 
                    f"✅ **گزارش سیستم:**\n"
                    f"لیست تاپ ۱۰ این هفته با موفقیت برای {success_count} کاربر ارسال شد.\n"
                    f"🧹 تعداد {deleted_rows} رکورد قدیمی (بیش از ۳۰ روز) از دیتابیس پاکسازی شد."
                )
            except Exception:
                pass

    except Exception as e:
        print("WEEKLY_TASK_ERROR:", repr(e))



def setup_scheduler(bot):
    """
    Initialize and configure the asynchronous scheduler.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    
    # Schedule the task to run every Friday at 21:00 Iran time
    scheduler.add_job(
        send_weekly_top_musics, 
        'cron', 
        day_of_week='fri', 
        hour=21, 
        minute=0, 
        args=[bot]
    )
    
    scheduler.start()
    print("APScheduler started! Weekly job scheduled for Friday 20:00 (Asia/Tehran).")