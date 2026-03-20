"""
WA Number Checker Bot — Python Edition
Entry point — starts both Telegram bot and REST API
"""
import asyncio
import logging
import uvicorn

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import config
<<<<<<< HEAD
import database as db
import wa_engine as wa
from helpers import send_log, broadcast_owner
from menus import refresh_fsub

from handlers.commands  import cmd_start, cmd_ban, cmd_unban, cmd_addprem, cmd_user, cmd_broadcast
from callbacks import on_callback
from handlers.messages  import on_message, on_photo, on_document

from server import app as api_app
=======
import core.database as db
import core.wa_engine as wa
from core.helpers import send_log, broadcast_owner
from core.menus import refresh_fsub

from handlers.commands  import cmd_start, cmd_ban, cmd_unban, cmd_addprem, cmd_user, cmd_broadcast
from handlers.callbacks import on_callback
from handlers.messages  import on_message, on_photo, on_document

from api.server import app as api_app
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)


def setup_wa_callbacks(app: Application):
    """Wire WA engine events to Telegram notifications"""

    async def on_connect(account_id: str, atype: str, phone: str):
        is_user = account_id.startswith("user_")
        if is_user:
            owner_id = int(account_id.replace("user_", ""))
            u = db.get_user(owner_id)
            msg = (f"✅ <b>User WA Connected</b>\n"
                   f"👤 @{u.get('username','?') if u else '?'} (<code>{owner_id}</code>)\n"
                   f"📱 <code>+{phone}</code>")
            try: await app.bot.send_message(owner_id, "✅ <b>WhatsApp Connected!</b>", parse_mode="HTML")
            except: pass
        else:
            msg = f"✅ <b>Account Connected</b>\n🆔 <code>{account_id}</code>\n📱 <code>+{phone}</code>\nType: {atype}"
        await send_log(app, msg)
        await broadcast_owner(app, msg)

    async def on_disconnect(account_id: str, atype: str):
        checkers = wa.get_checkers()
        phone    = wa.accounts.get(account_id)
        ph_str   = f"+{phone.phone}" if phone and phone.phone else account_id
        if atype == "checker" and not checkers:
            msg = (f"🔴 <b>All Checkers Offline!</b>\n\n"
                   f"📱 <code>{ph_str}</code> disconnected\n⚠️ Promoting backup...")
            await send_log(app, msg)
            await broadcast_owner(app, msg)
            await wa.promote_backup()
        else:
            msg = (f"⚠️ <b>Account Disconnected</b>\n\n"
                   f"📱 <code>{ph_str}</code>\n✅ {len(checkers)} checker(s) still active")
            await send_log(app, msg)
            await broadcast_owner(app, msg)

    async def on_ban(account_id: str, atype: str):
        is_user = account_id.startswith("user_")
        if is_user:
            owner_id = int(account_id.replace("user_", ""))
            u = db.get_user(owner_id)
            msg = f"🚫 <b>User WA Banned</b>\n👤 @{u.get('username','?') if u else '?'} (<code>{owner_id}</code>)"
            try: await app.bot.send_message(owner_id, "⚠️ <b>Your WhatsApp was banned.</b>", parse_mode="HTML")
            except: pass
        else:
            msg = f"🚫 <b>Account Banned</b>\n🆔 <code>{account_id}</code>"
        await send_log(app, msg)
        await broadcast_owner(app, msg)

    wa.set_callbacks(on_connect=on_connect, on_disconnect=on_disconnect, on_ban=on_ban)


async def post_init(app: Application):
    """Called after bot starts"""
    logger.info("Initializing...")

    # Load DB
    await db.init()

    # Refresh FSub channel names
    for ch in db.get_all_fsub():
        await refresh_fsub(app, ch["channel_id"])

    # Setup WA callbacks
    setup_wa_callbacks(app)

    # Connect WA accounts
    await wa.connect_all_saved()

    logger.info("✅ Bot ready!")


async def post_shutdown(app: Application):
    logger.info("Shutting down...")


def build_bot() -> Application:
    if not config.BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")

    app = (Application.builder()
           .token(config.BOT_TOKEN)
           .post_init(post_init)
           .post_shutdown(post_shutdown)
           .build())

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ban",       cmd_ban))
    app.add_handler(CommandHandler("unban",     cmd_unban))
    app.add_handler(CommandHandler("addprem",   cmd_addprem))
    app.add_handler(CommandHandler("user",      cmd_user))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_callback))

    # Messages
    app.add_handler(MessageHandler(filters.PHOTO,        on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    return app


async def run_api():
    """Run FastAPI server"""
    config_uv = uvicorn.Config(
        api_app,
        host="0.0.0.0",
        port=config.PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config_uv)
    await server.serve()


async def main():
    bot = build_bot()
    # Run bot polling + API server concurrently
    async with bot:
        await bot.initialize()
        await bot.start()
        await bot.updater.start_polling(drop_pending_updates=True)
        logger.info(f"✅ Bot started! API on port {config.PORT}")
        # Run API alongside bot
        await run_api()
        await bot.updater.stop()
        await bot.stop()


if __name__ == "__main__":
<<<<<<< HEAD
    asyncio.run(main())
=======
    asyncio.run(main())
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
