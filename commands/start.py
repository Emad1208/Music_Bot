from .ads import user_state


async def change_start_state(callback_query, state, text, answer):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = state

    await callback_query.message.edit(text)
    await callback_query.answer(answer)


async def start_waiting_for_name(callback_query):
    await change_start_state(
        callback_query,
        "waiting_for_name",
        "لطفا نام آهنگ و خواننده مورد نظر را وارد کنید",
        "جستجو با اسم آهنگ و خواننده"
    )


async def start_waiting_for_text(callback_query):
    await change_start_state(
        callback_query,
        "waiting_for_text",
        "موقتا در دسترس نمیباشد",
        "جستجو با متن آهنگ"
    )


async def start_waiting_for_voice(callback_query):
    await change_start_state(
        callback_query,
        "waiting_for_voice",
        "موقتا در دسترس نمیباشد",
        "جستجو با وویس آهنگ"
    )


async def start_waiting_for_link(callback_query):
    await change_start_state(
        callback_query,
        "waiting_for_link",
        "موقتا در دسترس نمیباشد",
        "جستجو با لینک آهنگ"
    )


START_CALLBACKS = {
    "waiting_for_name": start_waiting_for_name,
    "waiting_for_text": start_waiting_for_text,
    "waiting_for_voice": start_waiting_for_voice,
    "waiting_for_link": start_waiting_for_link,
}