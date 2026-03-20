"""Main menu, welcome text, FSub logic"""
from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from telegram.constants import ParseMode

<<<<<<< HEAD
import database as db
import wa_engine as wa
from helpers import esc, is_admin, is_premium, is_vip, BACK_BTN
=======
import core.database as db
import core.wa_engine as wa
from core.helpers import esc, is_admin, is_premium, is_vip, BACK_BTN
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e

HTML = ParseMode.HTML

# ── Welcome ───────────────────────────────────────────────────────────────────

def welcome_text(uid: int) -> str:
    checkers = wa.get_checkers()
    status   = (f"<b>🟢 Online</b> — <i>{len(checkers)} checker(s) active</i>"
                if checkers else "<b>🔴 Offline</b> — <i>No accounts connected</i>")
    u     = db.get_user(uid)
    name  = f" {esc(u['first_name'])}" if u and u.get("first_name") else ""
    prem  = db.is_premium_active(uid)
    vip   = db.is_vip(uid)
    badge = "👑" if vip else ("💎" if prem else "👤")
    tier  = "<b>VIP Member</b>" if vip else ("<b>Premium Member</b>" if prem else "<b>Free User</b>")
    return (
        f"╔══════════════════════╗\n"
        f"  🔍  <b>WA Number Checker</b>\n"
        f"╚══════════════════════╝\n\n"
        f"{badge} Hello{name}! — {tier}\n"
        f"{status}\n\n"
        f"<i>Instantly verify whether any phone number\nis registered on WhatsApp.</i>\n\n"
        f"<b>┌ Features</b>\n"
        f"<b>│</b> ✅ Single & Bulk number check\n"
        f"<b>│</b> ⚡ Fast load-balanced checking\n"
        f"<b>│</b> 📁 File upload support\n"
        f"<b>│</b> 🎁 Referral rewards\n"
        f"<b>└</b> 💎 Premium plans available\n\n"
        f"<i>Choose an option below to get started:</i>"
    )

def main_menu(uid: int) -> InlineKeyboardMarkup:
    admin       = is_admin(uid)
    user_wa_on  = db.get_setting("user_wa_mode") == "on"
    rows = [
        [InlineKeyboardButton("🔍 Check Number", callback_data="check_number"),
         InlineKeyboardButton("📋 Bulk Check",   callback_data="bulk_check")],
        [InlineKeyboardButton("🧰 Tools",         callback_data="tools"),
         InlineKeyboardButton("👤 My Profile",    callback_data="profile")],
        [InlineKeyboardButton("💎 Premium Plans", callback_data="premium_info"),
         InlineKeyboardButton("🎁 Referral",      callback_data="referral")],
        [InlineKeyboardButton("🎟 Redeem Code",   callback_data="redeem")],
        [InlineKeyboardButton("📡 Bot Status",    callback_data="status"),
         InlineKeyboardButton("📖 Help",          callback_data="help")],
    ]
    if not admin and user_wa_on:
        rows.append([InlineKeyboardButton("📱 Connect WhatsApp", callback_data="user_wa_panel")])
    if admin:
        rows.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="owner_panel")])
    return InlineKeyboardMarkup(rows)

async def send_welcome(chat_id: int, uid: int, app: Application):
    img  = db.get_setting("menu_image")
    text = welcome_text(uid)
    markup = main_menu(uid)
    if img:
        try:
            await app.bot.send_photo(chat_id, img, caption=text, parse_mode=HTML, reply_markup=markup)
            return
        except:
            db.set_setting("menu_image", "")
    await app.bot.send_message(chat_id, text, parse_mode=HTML, reply_markup=markup)

# ── FSub ──────────────────────────────────────────────────────────────────────

async def refresh_fsub(app: Application, channel_id: str) -> dict:
    try:
        chat  = await app.bot.get_chat(channel_id)
        title = chat.title or chat.username or channel_id
        link  = None
        if chat.username:
            link = f"https://t.me/{chat.username}"
        if not link and getattr(chat, "invite_link", None):
            link = chat.invite_link
        if not link:
            try: link = await app.bot.export_chat_invite_link(channel_id)
            except: pass
        if not link:
            num_id = str(channel_id).replace("-100", "")
            link   = f"https://t.me/c/{num_id}/1"
        db.update_fsub(channel_id, title, link or "")
        return {"channel_id": channel_id, "title": title, "link": link}
    except:
        num_id = str(channel_id).replace("-100", "")
        link   = (f"https://t.me/{channel_id.replace('@','')}"
                  if str(channel_id).startswith("@")
                  else f"https://t.me/c/{num_id}/1")
        return {"channel_id": channel_id, "title": channel_id, "link": link}

async def check_fsub(app: Application, uid: int) -> bool:
    if is_admin(uid): return True
    channels = db.get_all_fsub()
    if not channels: return True
    for ch in channels:
        try:
            m = await app.bot.get_chat_member(ch["channel_id"], uid)
            if m.status not in ("member","administrator","creator"):
                return False
        except: pass
    return True

async def get_missing_fsub(app: Application, uid: int) -> list[dict]:
    if is_admin(uid): return []
    missing = []
    for ch in db.get_all_fsub():
        try:
            m = await app.bot.get_chat_member(ch["channel_id"], uid)
            if m.status not in ("member","administrator","creator"):
                missing.append(dict(ch))
        except: pass
    return missing

async def send_fsub_prompt(chat_id: int, uid: int, app: Application):
    channels = db.get_all_fsub()
    fsub_img = db.get_setting("fsub_image")

    # Refresh names
    for ch in channels:
        if not ch.get("title") or ch["title"] == ch["channel_id"]:
            await refresh_fsub(app, ch["channel_id"])
    channels = db.get_all_fsub()

    # Check statuses
    statuses = []
    for ch in channels:
        try:
            m = await app.bot.get_chat_member(ch["channel_id"], uid)
            joined = m.status in ("member","administrator","creator")
        except:
            joined = False
        statuses.append({**dict(ch), "joined": joined})

    joined_count = sum(1 for s in statuses if s["joined"])
    total        = len(statuses)

    body = (
        f"🔐 <b>Access Restricted</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"To use <b>WA Number Checker</b> you must\n"
        f"join <b>all</b> channels below.\n\n"
        f"<b>📊 Progress: {joined_count}/{total} joined</b>\n\n"
    )
    rows = []
    for s in statuses:
        link = s.get("link") or f"https://t.me/c/{str(s['channel_id']).replace('-100','')}/1"
        name = s.get("title") or s["channel_id"]
        icon = "✅" if s["joined"] else "❌"
        body += f"{icon} <a href=\"{esc(link)}\"><b>{esc(name)}</b></a>\n"
        if not s["joined"]:
            rows.append([InlineKeyboardButton(f"➕ Join {esc(name)}", url=link)])
    body += "\n<i>Join all ❌ channels, then tap Verify below.</i>"
    rows.append([InlineKeyboardButton("🔄 Verify — Check Again", callback_data="fsub_verify")])
    markup = InlineKeyboardMarkup(rows)

    if fsub_img:
        try:
            await app.bot.send_photo(chat_id, fsub_img, caption=body, parse_mode=HTML, reply_markup=markup)
            return
        except: pass
<<<<<<< HEAD
    await app.bot.send_message(chat_id, body, parse_mode=HTML, reply_markup=markup, disable_web_page_preview=True)
=======
    await app.bot.send_message(chat_id, body, parse_mode=HTML, reply_markup=markup, disable_web_page_preview=True)
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
