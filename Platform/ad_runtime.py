from db_Project.db_init import db

from commands.ads import send_ad_to_user

async def send_ad_before_music(bot, chat_id, admin_id=962702339):
    ad = db.get_next_active_ad()

    if not ad:
        return

    ad_id = ad[0]
    ad_name = ad[1]

    await send_ad_to_user(
        bot=bot,
        chat_id=chat_id,
        ad=ad
    )

    db.increase_ad_sent_count(ad_id)

    progress = db.get_ad_progress(ad_id)

    sent_count = progress[2]
    max_send = progress[3]

    if sent_count >= max_send:
        db.deactivate_ad(ad_id)

        await bot.send_message(
            admin_id,
            f"📢 تبلیغ شماره {ad_id} ({ad_name}) تکمیل شد."
        )
