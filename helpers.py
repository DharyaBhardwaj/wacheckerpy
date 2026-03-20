"""Shared helpers — auth, formatting, logging"""
from __future__ import annotations
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application

import config
<<<<<<< HEAD
import database as db
=======
import core.database as db
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e

HTML = ParseMode.HTML

# ── Auth ──────────────────────────────────────────────────────────────────────

def is_owner(uid: int) -> bool:
    return uid == config.OWNER_ID

def is_admin(uid: int) -> bool:
    if is_owner(uid): return True
    if uid in config.ADMIN_IDS: return True
    u = db.get_user(uid)
    return bool(u and u.get("role") in ("admin", "owner"))

def is_authorized(uid: int) -> bool:
    if is_admin(uid): return True
    u = db.get_user(uid)
    if not u or u.get("is_blocked"): return False
    mode = db.get_setting("bot_mode", "public")
    if mode == "private":
        return u.get("role") != "user" or bool(u.get("is_allowed"))
    return True

def is_premium(uid: int) -> bool:
    return is_admin(uid) or db.is_premium_active(uid)

def is_vip(uid: int) -> bool:
    return is_admin(uid) or db.is_vip(uid)

def is_maintenance() -> bool:
    return db.get_setting("maintenance") == "on"

# ── Text helpers ──────────────────────────────────────────────────────────────

def esc(s) -> str:
    return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def fmt(n) -> str:
    return f"{int(n or 0):,}"

def progress_bar(done: int, total: int) -> str:
    pct  = 0 if total == 0 else int(done / total * 100)
    fill = round(pct / 100 * 16)
    return "▓" * fill + "░" * (16 - fill)

# ── Keyboard helpers ──────────────────────────────────────────────────────────

BACK_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back to Menu", callback_data="main_menu")]])

def kb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    """rows: list of list of (text, callback_data) or (text, url, 'url')"""
    result = []
    for row in rows:
        btns = []
        for item in row:
            if len(item) > 2 and item[2] == "url":
                btns.append(InlineKeyboardButton(item[0], url=item[1]))
            else:
                btns.append(InlineKeyboardButton(item[0], callback_data=item[1]))
        result.append(btns)
    return InlineKeyboardMarkup(result)

# ── Logging ───────────────────────────────────────────────────────────────────

async def send_log(app: Application, text: str):
    gid = config.LOG_GROUP or int(db.get_setting("log_group_id", "0"))
    if not gid: return
    try: await app.bot.send_message(gid, text, parse_mode=HTML)
    except: pass

async def broadcast_owner(app: Application, text: str):
    if config.OWNER_ID:
        try: await app.bot.send_message(config.OWNER_ID, text, parse_mode=HTML)
        except: pass

# ── Edit message ──────────────────────────────────────────────────────────────

async def edit_msg(query, text: str, markup: InlineKeyboardMarkup):
    from telegram.error import BadRequest
    try:
        await query.edit_message_text(text, parse_mode=HTML, reply_markup=markup, disable_web_page_preview=True)
        return
    except BadRequest:
        pass
    try:
        await query.edit_message_caption(text, parse_mode=HTML, reply_markup=markup)
        return
    except BadRequest:
        pass
    try: await query.delete_message()
    except: pass
    await query.get_bot().send_message(
        query.message.chat_id, text, parse_mode=HTML,
        reply_markup=markup, disable_web_page_preview=True
<<<<<<< HEAD
    )
=======
    )
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
