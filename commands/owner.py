from balethon.objects import InlineKeyboard

from .ads import safe_answer, init_user_state, user_state

# import sys
# from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(BASE_DIR))

from db_Project.db_init import db

# ---------------------
# Show Admin
# ---------------------
async def show_admins(callback_query):
    admins = db.get_admins()

    if not admins:
        await callback_query.message.edit(
            "*هیچ ادمینی ثبت نشده است.*",
            InlineKeyboard(
            [("برگشت", "back_adm")]
            )
        )
        return

    await safe_answer(callback_query, "لیست ادمین ها")

    await callback_query.message.edit(
        "*یکی از ادمین ها را انتخاب کنید:*",
        build_admins_keyboard(
            admins,
            "show_admin"
        )
    )


async def show_admin_info(callback_query, admin_id):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        return
    
    admin_id = admin[0]
    user_id = admin[1]
    name = admin[2]
    role = admin[3]
    is_active = admin[4]
    hire_time = admin[5]

    status = "فعال 🟢" if is_active else "غیرفعال 🔴"

    await callback_query.message.edit(
        f"*مشخصات ادمین*\n\n"
        f"شناسه: {admin_id}\n"
        f"نام: {name}\n"
        f"آیدی کاربر: {user_id}\n"
        f"نقش: {role}\n"
        f"وضعیت: {status}\n"
        f"تاریخ انتصاب: {hire_time}",
        InlineKeyboard(
            [('برگشت به لیست', 'show_adm')]
        )
    )

# ---------------------
# Adding Admin
# ---------------------
async def add_admin(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_admin_user_id"

    await safe_answer(callback_query, "افزودن ادمین")

    await callback_query.message.edit(
        "*لطفا آیدی کاربر را وارد کنید:*",
            InlineKeyboard(
            [("برگشت", "back_adm")]
            )
    )


async def confirm_add_admin(callback_query):
    owner_id = callback_query.author.id

    target_user_id = user_state[owner_id]["new_admin_user_id"]
    admin_name = user_state[owner_id]["new_admin_name"]

    db.add_admin(
        user_id=target_user_id,
        name=admin_name,
        role="admin"
    )

    user_state[owner_id] = {"state": None}

    await safe_answer(callback_query, "ادمین اضافه شد")

    await callback_query.message.edit(
        f"*ادمین {admin_name} با موفقیت اضافه شد.*"
    )


async def cancel_add_admin(callback_query):
    owner_id = callback_query.author.id

    admin_name = user_state[owner_id].get(
        "new_admin_name",
        "نامشخص"
    )

    user_state[owner_id] = {"state": None}

    await safe_answer(callback_query, "لغو عملیات")

    await callback_query.message.edit(
        f"*عملیات اضافه کردن ادمین {admin_name} لغو شد.*"
    )

# ---------------------
# Deleting Admin
# ---------------------
async def delete_admin(callback_query):
    admins = db.get_admins()

    removable_admins = [admin for admin in admins if admin[3] != "owner"]

    if not removable_admins:
        await safe_answer(callback_query, "ادمینی برای حذف وجود ندارد")
        await callback_query.message.edit("*هیچ ادمینی برای حذف وجود ندارد.*",
            InlineKeyboard(
            [("برگشت", "back_adm")]
            ))
        return

    await safe_answer(callback_query, "حذف ادمین")
    await callback_query.message.edit(
        "*ادمین مورد نظر برای حذف را انتخاب کنید:*",
        build_admins_keyboard(removable_admins, "delete_admin")
    )


async def ask_delete_admin_confirm(callback_query, admin_id):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    name = admin[2]
    role = admin[3]

    if role == "owner":
        await callback_query.message.edit("*Owner قابل حذف نیست.*")
        return

    await safe_answer(callback_query, "تأیید حذف ادمین")
    await callback_query.message.edit(
        f"*آیا مطمئن هستید که می‌خواهید ادمین «{name}» را حذف کنید؟*",
        InlineKeyboard(
            [('بله', f'confirm_delete_admin:{admin_id}')],
            [('خیر', f'cancel_delete_admin:{admin_id}')]
        )
    )


async def confirm_delete_admin(callback_query, admin_id):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    name = admin[2]

    deleted = db.delete_admin_by_id(admin_id)

    await safe_answer(callback_query, "حذف ادمین")

    if deleted:
        await callback_query.message.edit(
            f"*ادمین «{name}» با موفقیت حذف شد.*"
        )
    else:
        await callback_query.message.edit(
            f"*ادمین «{name}» حذف نشد.*"
        )


async def cancel_delete_admin(callback_query, admin_id):
    admin = db.get_admin_by_id(admin_id)
    name = admin[2] if admin else "نامشخص"

    await safe_answer(callback_query, "لغو حذف")
    await callback_query.message.edit(
        f"*حذف ادمین «{name}» لغو شد.*"
    )

# ---------------------
# Active Admin
# ---------------------
async def active_admin(callback_query):
    admins = db.get_admins()

    inactive_admins = [
        admin for admin in admins
        if admin[4] == 0
    ]

    if not inactive_admins:
        await safe_answer(callback_query, "ادمین غیرفعالی وجود ندارد")

        await callback_query.message.edit(
            "*هیچ ادمین غیرفعالی وجود ندارد.*",
            InlineKeyboard(
            [("برگشت", "back_adm")]
            )
        )
        return

    await safe_answer(callback_query, "فعال کردن ادمین")

    await callback_query.message.edit(
        "*ادمین مورد نظر را انتخاب کنید:*",
        build_admins_keyboard(
            inactive_admins,
            "active_admin"
        )
    )


async def ask_active_admin_confirm(
        callback_query,
        admin_id
        ):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    admin_name = admin[2]

    await safe_answer(
        callback_query,
        "تایید فعال سازی"
    )

    await callback_query.message.edit(
        f"*آیا مطمئن هستید که میخواهید ادمین {admin_name} را فعال کنید؟*",
        InlineKeyboard(
            [('بله',
              f'confirm_active_admin:{admin_id}')],
            [('خیر',
              f'cancel_active_admin:{admin_id}')]
        )
    )


async def confirm_active_admin(
        callback_query,
        admin_id
):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    admin_name = admin[2]

    db.update_admin_status(
        admin_id,
        1
    )

    await safe_answer(
        callback_query,
        "ادمین فعال شد"
    )

    await callback_query.message.edit(
        f"*ادمین {admin_name} با موفقیت فعال شد.*"
    )


async def cancel_active_admin(
        callback_query,
        admin_id
):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    admin_name = admin[2]

    await safe_answer(
        callback_query,
        "عملیات لغو شد"
    )

    await callback_query.message.edit(
        f"*فعال کردن ادمین {admin_name} لغو شد.*"
    )

# ---------------------
# Deactive Admin
# ---------------------
async def deactive_admin(callback_query):
    admins = db.get_admins()

    active_admins = [
        admin for admin in admins
        if admin[4] == 1 and admin[3] != "owner"
    ]

    if not active_admins:
        await safe_answer(callback_query, "ادمین فعالی وجود ندارد")

        await callback_query.message.edit(
            "*هیچ ادمین فعالی برای غیرفعال کردن وجود ندارد.*",
            InlineKeyboard(
            [("برگشت", "back_adm")]
            )
        )
        return

    await safe_answer(callback_query, "غیرفعال کردن ادمین")

    await callback_query.message.edit(
        "*ادمین مورد نظر را انتخاب کنید:*",
        build_admins_keyboard(
            active_admins,
            "deactive_admin"
        )
    )


async def ask_deactive_admin_confirm(
        callback_query,
        admin_id
):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    admin_name = admin[2]

    # جلوگیری از غیرفعال کردن Owner
    if admin[3] == "owner":
        await safe_answer(callback_query, "مجاز نیست")

        await callback_query.message.edit(
            "*امکان غیرفعال کردن Owner وجود ندارد.*"
        )
        return

    await safe_answer(
        callback_query,
        "تایید غیرفعال سازی"
    )

    await callback_query.message.edit(
        f"*آیا مطمئن هستید که میخواهید ادمین {admin_name} را غیرفعال کنید؟*",
        InlineKeyboard(
            [('بله',
              f'confirm_deactive_admin:{admin_id}')],
            [('خیر',
              f'cancel_deactive_admin:{admin_id}')]
        )
    )


async def confirm_deactive_admin(
        callback_query,
        admin_id
):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    if admin[3] == "owner":
        await callback_query.message.edit(
            "*Owner قابل غیرفعال شدن نیست.*"
        )
        return
    if admin[1] == callback_query.author.id:
        await callback_query.message.edit(
            "*نمی‌توانید خودتان را غیرفعال کنید.*"
        )
        return

    admin_name = admin[2]

    db.update_admin_status(
        admin_id,
        0
    )

    await safe_answer(
        callback_query,
        "ادمین غیرفعال شد"
    )

    await callback_query.message.edit(
        f"*ادمین {admin_name} با موفقیت غیرفعال شد.*"
    )


async def cancel_deactive_admin(
        callback_query,
        admin_id
):
    admin = db.get_admin_by_id(admin_id)

    if not admin:
        await safe_answer(callback_query, "ادمین پیدا نشد")
        return

    admin_name = admin[2]

    await safe_answer(
        callback_query,
        "عملیات لغو شد"
    )

    await callback_query.message.edit(
        f"*غیرفعال کردن ادمین {admin_name} لغو شد.*"
    )

# ---------------------
# Building Keyborad
# ---------------------
def build_admins_keyboard(admins, action):
    buttons = []

    for admin in admins:
        admin_id = admin[0]
        name = admin[2]
        role = admin[3]
        is_active = admin[4]

        if role == "owner":
            icon = "👑"
        else:
            icon = "👤"

        status = "🟢" if is_active else "🔴"

        buttons.append([
            (
                f"{icon} {name} {status}",
                f"{action}:{admin_id}"
            )
        ])

    buttons.append([
        ("برگشت", "back_adm")
    ])

    return InlineKeyboard(*buttons)


async def back_adm(callback_query):
    user_id = callback_query.author.id
    init_user_state(user_id)

    user_state[user_id]["state"] = None
    await callback_query.message.edit(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('اضافه کردن ادمین', 'add_adm')],
            [('حذف کردن ادمین', 'del_adm')],
            [('فعال کردن ادمین','active_adm'),
            ('غیر فعال کردن ادمین','deactive_adm')],
            [('نمایش لیست ادمین ها', 'show_adm')],
            [('بستن', 'close')]
        )
    )


OWNER_CALLBACKS = {
    "show_adm": show_admins,

    "add_adm": add_admin,
    "confirm_add_admin": confirm_add_admin,
    "cancel_add_admin": cancel_add_admin,

    "del_adm": delete_admin,

    "active_adm": active_admin,

    "deactive_adm": deactive_admin,

    'back_adm': back_adm,
}


OWNER_DYNAMIC_CALLBACKS = {
    "show_admin": show_admin_info,

    "delete_admin": ask_delete_admin_confirm,
    "confirm_delete_admin": confirm_delete_admin,
    "cancel_delete_admin": cancel_delete_admin,

    "active_admin": ask_active_admin_confirm,
    "confirm_active_admin": confirm_active_admin,
    "cancel_active_admin": cancel_active_admin,

    "deactive_admin": ask_deactive_admin_confirm,
    "confirm_deactive_admin": confirm_deactive_admin,
    "cancel_deactive_admin": cancel_deactive_admin,
}