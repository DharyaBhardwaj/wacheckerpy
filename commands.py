"""Command handlers — /start, /ban, /unban, /user, /addprem"""
from __future__ import annotations
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
import wa_engine as wa
from helpers import is_admin, is_owner, esc, fmt, BACK_BTN, send_log, broadcast_owner
from menus import send_welcome, send_fsub_prompt, check_fsub
from admin import show_user_panel

HTML = ParseMode.HTML

# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg      = update.message
    uid      = msg.from_user.id
    username = msg.from_user.username or ""
    fname    = msg.from_user.first_name or ""
    args     = ctx.args

    from helpers import is_maintenance
    if is_maintenance() and not is_admin(uid):
        await msg.reply_text("🔧 <b>Maintenance Mode</b>\n\nPlease try again later.", parse_mode=HTML)
        return

    is_new = db.create_user(uid, username, fname)

    # Referral
    if is_new and args:
        code = args[0].strip()
        ref  = db.get_user_by_refer(code)
        if ref and ref["telegram_id"] != uid:
            bonus = int(db.get_setting("refer_bonus", "10"))
            if db.apply_referral(ref["telegram_id"], uid, bonus):
                await send_log(ctx.application,
                    f"🔗 <b>Referral</b>\n👤 @{esc(username)} (<code>{uid}</code>)\nBy: <code>{ref['telegram_id']}</code>")
                try:
                    await ctx.bot.send_message(ref["telegram_id"],
                        f"🎉 <b>New Referral!</b>\n\n@{esc(username) or uid} joined!\nYou earned <b>+{bonus}</b> bonus checks!",
                        parse_mode=HTML)
                except: pass

    if is_new:
        await send_log(ctx.application,
            f"👋 <b>New User</b>\n👤 @{esc(username)} (<code>{uid}</code>)\nName: {esc(fname)}")

    if not await check_fsub(ctx.application, uid):
        await send_fsub_prompt(msg.chat_id, uid, ctx.application)
        return

    ctx.user_data.clear()
    await send_welcome(msg.chat_id, uid, ctx.application)

# ── /ban /unban ───────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id): return
    if not ctx.args: return await update.message.reply_text("Usage: /ban <id>")
    uid = int(ctx.args[0])
    db.block_user(uid, True)
    try: await ctx.bot.send_message(uid, "🚫 <b>You have been banned.</b>", parse_mode=HTML)
    except: pass
    await update.message.reply_text(f"✅ Banned <code>{uid}</code>", parse_mode=HTML)

async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id): return
    if not ctx.args: return await update.message.reply_text("Usage: /unban <id>")
    uid = int(ctx.args[0])
    db.block_user(uid, False)
    try: await ctx.bot.send_message(uid, "✅ <b>Your ban has been lifted.</b> Type /start", parse_mode=HTML)
    except: pass
    await update.message.reply_text(f"✅ Unbanned <code>{uid}</code>", parse_mode=HTML)

# ── /addprem ──────────────────────────────────────────────────────────────────

async def cmd_addprem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id): return
    if len(ctx.args) < 2:
        return await update.message.reply_text("Usage: /addprem <id> <days|lifetime>")
    uid = int(ctx.args[0])
    dur = ctx.args[1].lower()
    until = None if dur == "lifetime" else datetime.now() + timedelta(days=int(dur))
    db.create_user(uid, "", "")
    db.set_premium(uid, until)
    exp = until.strftime("%d %b %Y") if until else "Lifetime"
    try: await ctx.bot.send_message(uid, f"💎 <b>Premium Activated!</b>\n\n{exp}", parse_mode=HTML)
    except: pass
    await update.message.reply_text(f"✅ Premium granted to <code>{uid}</code> — {exp}", parse_mode=HTML)

# ── /user ─────────────────────────────────────────────────────────────────────

async def cmd_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id): return
    if not ctx.args:
        return await update.message.reply_text("Usage: /user <id>")
    target_id = int(ctx.args[0])
    await show_user_panel(update.message.chat_id, update.message.from_user.id, None, target_id, ctx.application, send_new=True)

# ── /broadcast ────────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id): return
    if not ctx.args:
        return await update.message.reply_text("Usage: /broadcast <message>")
    text  = " ".join(ctx.args)
    users = db.get_all_users()
    sent = failed = 0
    sm = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    for u in users:
        try:
            await ctx.bot.send_message(u["telegram_id"], text, parse_mode=HTML)
            sent += 1
        except:
            failed += 1
    await sm.edit_text(f"📢 <b>Done!</b>\n✅ {sent} | ❌ {failed}", parse_mode=HTML)