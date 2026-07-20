import asyncio
import signal
from datetime import datetime

from balethon import Client

from db_Project.db_init import db


def _raise_keyboard_interrupt_on_shutdown(signum, _frame):
    """Turn service stop signals into a graceful Python shutdown."""
    try:
        signal_name = signal.Signals(signum).name
    except ValueError:
        signal_name = str(signum)

    print(f"Shutdown signal received: {signal_name}")
    raise KeyboardInterrupt


def install_shutdown_signal_handlers():
    # SIGTERM is used by systemd/Docker. SIGHUP is common on Linux and
    # SIGBREAK covers Ctrl+Break on Windows. Ctrl+C already raises
    # KeyboardInterrupt by default, so SIGINT does not need overriding.
    for signal_name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is None:
            continue

        try:
            signal.signal(
                shutdown_signal,
                _raise_keyboard_interrupt_on_shutdown,
            )
        except (OSError, RuntimeError, ValueError):
            # Signal handlers can only be registered in the main thread and
            # some signals are not supported on every operating system.
            continue


async def notify_active_admins_bot_stopped(token, reason):
    active_admin_ids = sorted({
        int(admin[1])
        for admin in db.get_admins()
        if admin[4]
    })

    if not active_admin_ids:
        print("Shutdown notification skipped: no active admins found.")
        return

    notification_bot = Client(token)
    is_connected = False
    message_text = (
        "⚠️ ربات غیرفعال شد.\n"
        f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"علت: {reason}"
    )

    try:
        await notification_bot.connect()
        is_connected = True

        results = await asyncio.gather(
            *(
                notification_bot.send_message(admin_id, message_text)
                for admin_id in active_admin_ids
            ),
            return_exceptions=True,
        )

        for admin_id, result in zip(active_admin_ids, results):
            if isinstance(result, BaseException):
                print(
                    "Could not send shutdown notification to admin "
                    f"{admin_id}: {result}"
                )
    except Exception as error:
        print(f"Could not send shutdown notifications: {error}")
    finally:
        if is_connected:
            try:
                await notification_bot.disconnect()
            except Exception as error:
                print(f"Could not close notification connection: {error}")
