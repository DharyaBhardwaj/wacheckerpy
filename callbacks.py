"""Callback query router"""
from __future__ import annotations
import io
import secrets
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
import wa_engine as wa
from helpers import (is_admin, is_owner, is_premium, is_vip,
                          is_maintenance, esc, fmt, BACK_BTN,
                          edit_msg, send_log, broadcast_owner, kb)
from menus import (welcome_text, main_menu, send_welcome,
                        send_fsub_prompt, refresh_fsub, get_missing_fsub)
from admin import (show_owner_panel, show_wa_accounts, show_users_list,
                              show_user_panel, show_fsub_settings, show_bot_settings,
                              show_stats, show_redeem_panel, show_api_keys, show_api_settings,
                              handle_user_ban, handle_add_premium, handle_remove_premium,
                              handle_add_bonus, handle_clear_bonus, handle_user_role)
from user_screens import (show_check_number, show_bulk_check, show_tools,
                                     show_profile, show_premium_info, show_plan_detail,
                                     show_bundle_detail, show_referral, show_status,
                                     show_help, show_redeem_screen)

HTML = ParseMode.HTML

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    uid  = q.from_user.id
    data = q.data
    cid  = q.message.chat_id

    if is_maintenance() and not is_admin(uid):
        await q.answer("🔧 Maintenance mode.", show_alert=True)
        return

    if not await _check_fsub(q, uid, cid, ctx):
        return

    db.create_user(uid, q.from_user.username or "", q.from_user.first_name or "")

    from helpers import is_authorized
    if not is_authorized(uid):
        await q.answer("🔒 Access denied.", show_alert=True)
        return

    await q.answer()

    # ── Dynamic prefixes ──────────────────────────────────────────────────────
    if data.startswith("wa_qr_"):        return await _wa_qr(q, uid, data[6:], ctx)
    if data.startswith("wa_pair_"):      return await _wa_pair_prompt(q, uid, data[8:], ctx)
    if data.startswith("wa_dis_"):       return await _wa_disconnect(q, uid, data[7:], ctx)
    if data.startswith("wa_del_"):       return await _wa_delete(q, uid, data[7:], ctx)
    if data.startswith("wa_type_ck_"):   return await _wa_type(q, uid, data[10:], "checker")
    if data.startswith("wa_type_bk_"):   return await _wa_type(q, uid, data[10:], "backup")
    if data.startswith("user_ban_"):     return await handle_user_ban(cid, uid, int(data[9:]), True, ctx.application)
    if data.startswith("user_unban_"):   return await handle_user_ban(cid, uid, int(data[11:]), False, ctx.application)
    if data.startswith("user_promote_"): return await handle_user_role(cid, uid, int(data[14:]), "admin", ctx.application)
    if data.startswith("user_demote_"):  return await handle_user_role(cid, uid, int(data[13:]), "user", ctx.application)
    if data.startswith("user_remprem_"): return await handle_remove_premium(cid, uid, int(data[13:]), ctx.application)
    if data.startswith("user_prem30_"):  return await handle_add_premium(cid, uid, int(data[11:]), 30, "premium", ctx.application)
    if data.startswith("user_premlife_"):return await handle_add_premium(cid, uid, int(data[14:]), "lifetime", "premium", ctx.application)
    if data.startswith("user_vip30_"):   return await handle_add_premium(cid, uid, int(data[11:]), 30, "vip", ctx.application)
    if data.startswith("user_viplife_"): return await handle_add_premium(cid, uid, int(data[14:]), "lifetime", "vip", ctx.application)
    if data.startswith("user_bonus_"):
        parts = data.replace("user_bonus_", "").split("_")
        return await handle_add_bonus(cid, uid, int(parts[1]), int(parts[0]), ctx.application)
    if data.startswith("user_clrbonus_"):return await handle_clear_bonus(cid, uid, int(data[15:]), ctx.application)
    if data.startswith("fsub_del_"):
        if not is_admin(uid): return
        db.remove_fsub(data[9:])
        return await show_fsub_settings(q, uid)
    if data.startswith("revoke_api_"):
        if not is_admin(uid): return
        db.delete_api_key(data[11:])
        return await show_api_keys(q, uid)
    if data.startswith("user_wa_"):      return await _user_wa(q, uid, data, ctx)

    # ── Switch ────────────────────────────────────────────────────────────────
    match data:
        case "main_menu":      ctx.user_data.clear(); return await edit_msg(q, welcome_text(uid), main_menu(uid))
        case "check_number":   return await show_check_number(q, uid, ctx)
        case "bulk_check":     return await show_bulk_check(q, uid, ctx)
        case "tools":          return await show_tools(q, uid, ctx)
        case "profile":        return await show_profile(q, uid, ctx)
        case "premium_info":   return await show_premium_info(q, uid)
        case "premium_plans":  return await show_premium_info(q, uid)
        case "buy_basic":      return await show_plan_detail(q, uid, "basic")
        case "buy_pro":        return await show_plan_detail(q, uid, "pro")
        case "buy_business":   return await show_plan_detail(q, uid, "business")
        case "buy_bundles":    return await show_bundle_detail(q, uid)
        case "referral":       return await show_referral(q, uid, ctx)
        case "redeem":         return await show_redeem_screen(q, uid, ctx)
        case "status":         return await show_status(q, uid)
        case "help":           return await show_help(q, uid)
        case "export_profile": return await _export_profile(q, uid, ctx)
        case "fsub_verify":    return await _fsub_verify(q, uid, ctx)
        case "owner_panel":    return await show_owner_panel(cid, uid, q.message.message_id, ctx.application)
        case "op_accounts":    return await show_wa_accounts(q, uid)
        case "op_add_acct":
            ctx.user_data["state"] = "add_account"
            return await edit_msg(q, "➕ <b>Add Account</b>\n\nSend a name (lowercase, numbers, underscores):", BACK_BTN)
        case "op_users":       return await show_users_list(q, uid)
        case "op_users_dl":    return await _users_download(q, uid, ctx)
        case "op_fsub":        return await show_fsub_settings(q, uid)
        case "op_settings":    return await show_bot_settings(q, uid)
        case "op_stats":       return await show_stats(q, uid)
        case "op_redeem":      return await show_redeem_panel(q, uid)
        case "op_create_code":
            ctx.user_data["state"] = "create_code"
            return await edit_msg(q,
                "🎟 <b>Create Redeem Code</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "Format: <code>CODE CHECKS MAXUSERS</code>\n\n"
                "Examples:\n• <code>SUMMER25 50 10</code>\n• <code>VIP100 100 1</code>\n• <code>auto 50 0</code> (unlimited)", BACK_BTN)
        case "op_api_keys":    return await show_api_keys(q, uid)
        case "op_api_settings":return await show_api_settings(q, uid)
        case "op_create_api_key":
            ctx.user_data["state"] = "create_api_key"
            return await edit_msg(q,
                "🔑 <b>Create API Key</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "Format: <code>LABEL PLAN DAYS</code>\n\n"
                "Plans: <code>basic</code> / <code>pro</code> / <code>business</code>\n\n"
                "Examples:\n• <code>John basic 30</code>\n• <code>Agency pro 90</code>\n• <code>Client business 0</code>", BACK_BTN)
        case "op_add_premium":
            ctx.user_data["state"] = "add_premium_uid"
            return await edit_msg(q, "💎 <b>Add Premium</b>\n\nSend the user's Telegram ID:", BACK_BTN)
        case "op_add_checks":
            ctx.user_data["state"] = "add_checks"
            return await edit_msg(q,
                "🎟 <b>Add Checks</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "Format: <code>USER_ID CHECKS</code>\n\n"
                "Example: <code>123456789 500</code>", BACK_BTN)
        case "op_broadcast":
            ctx.user_data["state"] = "broadcast"
            return await edit_msg(q, "📢 <b>Broadcast</b>\n\nSend the message:", BACK_BTN)
        case "op_logs":
            ctx.user_data["state"] = "set_log_group"
            return await edit_msg(q, f"📋 <b>Set Log Group</b>\n\nCurrent: <code>{db.get_setting('log_group_id','Not set')}</code>\n\nSend group/channel ID:", BACK_BTN)
        case "tools_upload":
            ctx.user_data["state"] = "upload"
            return await edit_msg(q, "📤 <b>Upload Numbers</b>\n\nSend numbers (one per line) or .txt file:", BACK_BTN)
        case "tools_get":      return await _get_number(q, uid, ctx)
        case "tools_change":   return await _next_number(q, uid, ctx)
        case "tools_filter":
            ctx.user_data["state"] = "filter_pending_file"
            return await edit_msg(q, "🔍 <b>Filter by Ending Digits</b>\n\nStep 1: Send your .txt file\nStep 2: Send the ending digits", BACK_BTN)
        case "set_fsub_input":
            ctx.user_data["state"] = "set_fsub"
            return await edit_msg(q, "📢 <b>Add FSub Channel</b>\n\nSend username or ID:\n<code>@channel</code> or <code>-100xxxxxxxxx</code>", BACK_BTN)
        case "set_fsub_image":
            ctx.user_data["state"] = "set_fsub_image"
            return await edit_msg(q, "🖼 <b>Set FSub Image</b>\n\nSend a photo or URL:", BACK_BTN)
        case "fsub_img_remove":
            db.set_setting("fsub_image", "")
            return await show_fsub_settings(q, uid)
        case "set_menu_image":
            ctx.user_data["state"] = "set_menu_image"
            return await edit_msg(q, "🖼 <b>Set Menu Image</b>\n\nSend a photo or URL:", BACK_BTN)
        case "menu_img_remove":
            db.set_setting("menu_image", "")
            return await show_bot_settings(q, uid)
        case "set_public":     db.set_setting("bot_mode","public");   return await show_bot_settings(q, uid)
        case "set_private":    db.set_setting("bot_mode","private");  return await show_bot_settings(q, uid)
        case "maint_on":       db.set_setting("maintenance","on");    return await show_bot_settings(q, uid)
        case "maint_off":      db.set_setting("maintenance","off");   return await show_bot_settings(q, uid)
        case "paid_on":        db.set_setting("paid_mode","true");    return await show_bot_settings(q, uid)
        case "paid_off":       db.set_setting("paid_mode","false");   return await show_bot_settings(q, uid)
        case "toggle_user_wa":
            cur = db.get_setting("user_wa_mode") == "on"
            db.set_setting("user_wa_mode", "off" if cur else "on")
            return await show_owner_panel(cid, uid, None, ctx.application)
        case _:
            # Setting inputs
            setting_map = {
                "set_free_limit":    ("set_free_limit",    "free_limit",    "👤 Free Limit"),
                "set_prem_limit":    ("set_prem_limit",    "prem_limit",    "💎 Premium Limit"),
                "set_bulk_limit":    ("set_bulk_limit",    "bulk_limit",    "📁 Bulk Limit"),
                "set_refer_bonus":   ("set_refer_bonus",   "refer_bonus",   "🔗 Refer Bonus"),
                "set_vip_limit":     ("set_vip_limit",     "vip_limit",     "👑 VIP Daily"),
                "set_vip_bulk":      ("set_vip_bulk",      "vip_bulk",      "👑 VIP Bulk"),
                "set_upi_id":        ("set_upi_id",        "upi_id",        "💳 UPI ID"),
                "set_api_key":       ("set_api_key",       "api_key",       "🔑 API Key"),
                "set_brand_channel": ("set_brand_channel", "brand_channel", "📢 Brand Channel"),
                "set_brand_name":    ("set_brand_name",    "brand_name",    "🏷 Brand Name"),
                "set_api_rps_basic": ("set_api_rps_basic", "api_rps_basic", "⚡ Basic RPS"),
                "set_api_rps_pro":   ("set_api_rps_pro",   "api_rps_pro",   "⚡ Pro RPS"),
                "set_api_rps_business": ("set_api_rps_business","api_rps_business","⚡ Business RPS"),
                "set_api_bulk_basic":("set_api_bulk_basic","api_bulk_basic","📦 Basic Bulk"),
                "set_api_bulk_pro":  ("set_api_bulk_pro",  "api_bulk_pro",  "📦 Pro Bulk"),
                "set_api_bulk_business":("set_api_bulk_business","api_bulk_business","📦 Business Bulk"),
            }
            if data in setting_map:
                if not is_admin(uid): return
                state, _, label = setting_map[data]
                ctx.user_data["state"] = state
                current = db.get_setting(setting_map[data][1]) or "Not set"
                return await edit_msg(q, f"<b>{label}</b>\n\nCurrent: <code>{esc(current)}</code>\n\nSend new value:", BACK_BTN)

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_fsub(q, uid, cid, ctx):
    from menus import check_fsub as _cf
    ok = await _cf(ctx.application, uid)
    if not ok:
        await q.answer("🔒 Join required channels first!", show_alert=True)
    return ok

async def _fsub_verify(q, uid: int, ctx):
    missing = await get_missing_fsub(ctx.application, uid)
    if not missing:
        ctx.user_data.clear()
        await q.answer("✅ All channels joined! Access granted.")
        return await edit_msg(q, welcome_text(uid), main_menu(uid))
    names = ", ".join(ch.get("title") or ch["channel_id"] for ch in missing)
    await q.answer(f"❌ Still need to join: {names}", show_alert=True)

async def _export_profile(q, uid: int, ctx):
    u = db.get_user(uid)
    if not u: return
    prem = db.is_premium_active(uid)
    txt  = (f"WA Checker — Profile\n{'='*40}\n"
            f"ID: {u['telegram_id']}\nUsername: @{u.get('username','N/A')}\n"
            f"Premium: {'Yes' if prem else 'No'}\nChecks: {u.get('numbers_checked',0)}\n"
            f"Bonus: {u.get('bonus_checks',0)}\nRefer code: {u.get('refer_code','N/A')}\n"
            f"Joined: {str(u.get('joined_at',''))[:10]}")
    buf = io.BytesIO(txt.encode()); buf.name = f"profile_{uid}.txt"
    await ctx.bot.send_document(q.message.chat_id, buf, caption="📄 Your profile data")

async def _users_download(q, uid: int, ctx):
    if not is_admin(uid): return
    users = db.get_all_users()
    lines = [f"WA Checker Users ({len(users)})\n{'='*50}"]
    for u in users:
        prem = db.is_premium_active(u["telegram_id"])
        lines.append(f"{u['telegram_id']} | @{u.get('username','N/A')} | {u.get('role','user')} | {'Prem' if prem else 'Free'} | {'Banned' if u.get('is_blocked') else 'Active'} | {u.get('numbers_checked',0)} checks")
    buf = io.BytesIO("\n".join(lines).encode()); buf.name = "users.txt"
    await ctx.bot.send_document(q.message.chat_id, buf, caption=f"📥 {len(users)} users")

async def _get_number(q, uid: int, ctx):
    n = await db.get_next_number(uid)
    if not n:
        return await edit_msg(q, "🎲 <b>Pool Empty</b>\n\n❌ No numbers left.",
            InlineKeyboardMarkup([[InlineKeyboardButton("📤 Upload", callback_data="tools_upload")],
                                   [InlineKeyboardButton("‹ Back", callback_data="tools")]]))
    count = await db.get_number_count(uid)
    await edit_msg(q, f"🎲 <b>Your Number</b>\n\n📱 <code>{n['phone_number']}</code>\n\n📦 Remaining: {count}",
        InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Next", callback_data="tools_change")],
                               [InlineKeyboardButton("‹ Back", callback_data="tools")]]))

async def _next_number(q, uid: int, ctx):
    n = await db.get_next_number(uid)
    if not n:
        return await edit_msg(q, "⏭ No more numbers.",
            InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="tools")]]))
    count = await db.get_number_count(uid)
    await edit_msg(q, f"⏭ <b>Next Number</b>\n\n📱 <code>{n['phone_number']}</code>\n\n📦 Remaining: {count}",
        InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Next", callback_data="tools_change")],
                               [InlineKeyboardButton("‹ Back", callback_data="tools")]]))

# ── WA Account handlers ───────────────────────────────────────────────────────

async def _wa_qr(q, uid: int, account_id: str, ctx):
    if not is_admin(uid): return
    await q.edit_message_text(f"⏳ <b>Generating QR for {esc(account_id)}...</b>", parse_mode=HTML)
    qr_evt  = asyncio.Event()
    qr_data = {}
    orig = wa._cb_qr

    async def tmp_qr(aid, img):
        if aid == account_id: qr_data["img"] = img; qr_evt.set()
        if orig: await orig(aid, img)
    wa._cb_qr = tmp_qr

    import asyncio
    asyncio.create_task(wa.connect_account(account_id))
    try:
        await asyncio.wait_for(qr_evt.wait(), 20)
        wa._cb_qr = orig
        buf = io.BytesIO(qr_data["img"]); buf.name = "qr.png"
        await q.delete_message()
        await ctx.bot.send_photo(q.message.chat_id, buf,
            caption=f"📱 <b>Scan QR — {esc(account_id)}</b>\n\nWhatsApp → Settings → Linked Devices\n\n⏳ Expires in ~60s",
            parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="op_accounts")]]))
    except asyncio.TimeoutError:
        wa._cb_qr = orig
        await ctx.bot.send_message(q.message.chat_id, "❌ QR timed out. Try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="op_accounts")]]))

async def _wa_pair_prompt(q, uid: int, account_id: str, ctx):
    if not is_admin(uid): return
    ctx.user_data["state"] = "pair_wa"
    ctx.user_data["pair_account"] = account_id
    await edit_msg(q, f"🔗 <b>Pair — {esc(account_id)}</b>\n\nSend WhatsApp number with country code:\n<code>919876543210</code>", BACK_BTN)

async def _wa_disconnect(q, uid: int, account_id: str, ctx):
    if not is_admin(uid): return
    await wa.disconnect_account(account_id)
    log = f"🔌 <b>Disconnected</b>\n🆔 <code>{esc(account_id)}</code>"
    await send_log(ctx.application, log)
    await broadcast_owner(ctx.application, log)
    await show_wa_accounts(q, uid)

async def _wa_delete(q, uid: int, account_id: str, ctx):
    if not is_admin(uid): return
    await wa.disconnect_account(account_id)
    wa.accounts.pop(account_id, None)
    db.remove_account(account_id)
    log = f"🗑 <b>Account Deleted</b>\n🆔 <code>{esc(account_id)}</code>"
    await send_log(ctx.application, log)
    await show_wa_accounts(q, uid)

async def _wa_type(q, uid: int, account_id: str, atype: str):
    if not is_admin(uid): return
    db.set_account_type(account_id, atype)
    a = wa.accounts.get(account_id)
    if a: a.account_type = atype
    await show_wa_accounts(q, uid)

async def _user_wa(q, uid: int, data: str, ctx):
    account_id = f"user_{uid}"
    cid = q.message.chat_id

    if data == "user_wa_panel":
        if db.get_setting("user_wa_mode") != "on" and not is_admin(uid):
            return await edit_msg(q, "❌ Feature disabled.", BACK_BTN)
        a  = wa.accounts.get(account_id)
        st = a.status if a else "disconnected"
        em = {"connected":"🟢","waiting_qr":"⏳","connecting":"🔄","banned":"🚫","disconnected":"🔴"}.get(st,"🔴")
        ph = (a.phone if a else None) or (db.get_account(account_id) or {}).get("phone_number","")
        rows = []
        if st == "connected":
            rows.append([InlineKeyboardButton("⏹ Disconnect", callback_data="user_wa_disconnect")])
        else:
            rows.append([InlineKeyboardButton("📷 QR", callback_data="user_wa_qr"),
                         InlineKeyboardButton("🔗 Pair", callback_data="user_wa_pair")])
        rows += [[InlineKeyboardButton("🔄 Refresh", callback_data="user_wa_panel")],
                 [InlineKeyboardButton("‹ Back", callback_data="main_menu")]]
        return await edit_msg(q,
            f"📱 <b>My WhatsApp</b>\n\n{em} <b>{st}</b>\n"
            f"{f'📞 +{ph}' if ph else ''}",
            InlineKeyboardMarkup(rows))

    if data == "user_wa_disconnect":
        await wa.disconnect_account(account_id)
        log = f"🔌 <b>User WA Disconnected</b>\n🆔 <code>{uid}</code>"
        await send_log(ctx.application, log)
        await broadcast_owner(ctx.application, log)
        return await edit_msg(q, "✅ WhatsApp Disconnected",
            InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="user_wa_panel")]]))

    if data == "user_wa_pair":
        ctx.user_data["state"] = "user_wa_pair"
        return await edit_msg(q, "🔗 <b>Pairing Code</b>\n\nSend your number:\n<code>919876543210</code>", BACK_BTN)

    if data == "user_wa_qr":
        import asyncio
        await q.edit_message_text("⏳ <b>Generating QR...</b>", parse_mode=HTML)
        db.add_account(account_id, f"user_{uid}", "checker")
        qr_evt  = asyncio.Event()
        qr_data = {}
        orig = wa._cb_qr
        async def tmp_qr(aid, img):
            if aid == account_id: qr_data["img"] = img; qr_evt.set()
            if orig: await orig(aid, img)
        wa._cb_qr = tmp_qr
        asyncio.create_task(wa.connect_account(account_id, "checker"))
        try:
            await asyncio.wait_for(qr_evt.wait(), 20)
            wa._cb_qr = orig
            buf = io.BytesIO(qr_data["img"]); buf.name = "qr.png"
            await q.delete_message()
            await ctx.bot.send_photo(cid, buf,
                caption="📱 <b>Scan QR</b>\n\nWhatsApp → Settings → Linked Devices\n\n⏳ Expires ~60s",
                parse_mode=HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="user_wa_panel")]]))
        except asyncio.TimeoutError:
            wa._cb_qr = orig
            await ctx.bot.send_message(cid, "❌ Timed out.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="user_wa_panel")]]))