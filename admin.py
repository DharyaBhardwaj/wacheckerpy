"""Admin panel — accounts, users, settings, fsub, stats, redeem, API keys"""
from __future__ import annotations
import io
import secrets
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, Application
from telegram.constants import ParseMode
from telegram.error import BadRequest

import core.database as db
import core.wa_engine as wa
from core.helpers import (is_admin, is_owner, esc, fmt, BACK_BTN,
                          send_log, broadcast_owner, edit_msg, kb)
from core.menus import welcome_text, main_menu, refresh_fsub

HTML = ParseMode.HTML

# ── Owner Panel ───────────────────────────────────────────────────────────────

async def show_owner_panel(chat_id: int, uid: int, msgid, app: Application):
    if not is_admin(uid): return
    users     = db.get_all_users()
    total     = len(users)
    prems     = sum(1 for u in users if db.is_premium_active(u["telegram_id"]))
    active_wa = len(wa.get_checkers())
    maint     = "🔧 ON" if db.get_setting("maintenance") == "on" else "✅ OFF"
    paid      = "💰 ON" if db.get_setting("paid_mode") == "true" else "🆓 OFF"
    wa_on     = db.get_setting("user_wa_mode") == "on"

    text = (
        f"⚙️ <b>Admin Panel</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{total}</b>  |  💎 Premium: <b>{prems}</b>\n"
        f"📱 WA online: <b>{active_wa}</b>  |  🔧 Maint: {maint}\n"
        f"💰 Paid Mode: {paid}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 WA Accounts", callback_data="op_accounts"),
         InlineKeyboardButton("➕ Add Account",  callback_data="op_add_acct")],
        [InlineKeyboardButton("🟢 User WA: ON — Disable" if wa_on else "🔴 User WA: OFF — Enable",
                              callback_data="toggle_user_wa")],
        [InlineKeyboardButton("👥 Users",          callback_data="op_users"),
         InlineKeyboardButton("💎 Add Premium",    callback_data="op_add_premium")],
        [InlineKeyboardButton("🎟 Add Checks",     callback_data="op_add_checks"),
         InlineKeyboardButton("📢 Broadcast",      callback_data="op_broadcast")],
        [InlineKeyboardButton("📋 Logs",           callback_data="op_logs"),
         InlineKeyboardButton("📊 Stats",          callback_data="op_stats")],
        [InlineKeyboardButton("🎟 Redeem Codes",   callback_data="op_redeem"),
         InlineKeyboardButton("🔑 API Keys",       callback_data="op_api_keys")],
        [InlineKeyboardButton("🔒 Force Sub",      callback_data="op_fsub"),
         InlineKeyboardButton("⚙️ Settings",       callback_data="op_settings")],
        [InlineKeyboardButton("‹ Back to Menu",    callback_data="main_menu")],
    ])
    await app.bot.send_message(chat_id, text, parse_mode=HTML, reply_markup=markup)

# ── WA Accounts ───────────────────────────────────────────────────────────────

async def show_wa_accounts(q, uid: int):
    if not is_admin(uid): return
    all_accts = db.get_all_accounts()
    body  = "" if all_accts else "No accounts yet.\n"
    rows  = []
    icons = {"connected":"🟢","waiting_qr":"⏳","connecting":"🔄","banned":"🚫","disconnected":"🔴"}
    for a in all_accts:
        s   = wa.accounts.get(a["account_id"])
        st  = s.status if s else ("connected" if a.get("is_connected") else "disconnected" if a.get("is_enabled") else "banned")
        em  = icons.get(st, "🔴")
        ph  = f"+{a['phone_number']}" if a.get("phone_number") else "Not linked"
        typ = "🔒 Backup" if a.get("account_type") == "backup" else "✅ Checker"
        body += f"{em} <b>{esc(a['label'])}</b> — {typ}\n   📞 {ph} | ✓ {a.get('total_checks',0)} | ⚠️ {a.get('ban_count',0)}\n\n"
        row = []
        if st != "connected":
            row += [InlineKeyboardButton("📷 QR", callback_data=f"wa_qr_{a['account_id']}"),
                    InlineKeyboardButton("🔗 Pair", callback_data=f"wa_pair_{a['account_id']}")]
        else:
            row.append(InlineKeyboardButton("⏹ Disconnect", callback_data=f"wa_dis_{a['account_id']}"))
        row.append(InlineKeyboardButton(
            "→ Backup" if a.get("account_type") == "checker" else "→ Checker",
            callback_data=f"wa_type_{'bk' if a.get('account_type')=='checker' else 'ck'}_{a['account_id']}"))
        row.append(InlineKeyboardButton("🗑", callback_data=f"wa_del_{a['account_id']}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("➕ Add Account", callback_data="op_add_acct"),
                 InlineKeyboardButton("🔄 Refresh",    callback_data="op_accounts")])
    rows.append([InlineKeyboardButton("‹ Back", callback_data="owner_panel")])
    await edit_msg(q, f"📱 <b>WhatsApp Accounts</b>\n\n{body}", InlineKeyboardMarkup(rows))

# ── Users List ────────────────────────────────────────────────────────────────

async def show_users_list(q, uid: int):
    if not is_admin(uid): return
    all_u = db.get_all_users()
    total = len(all_u)
    lines = [f"👥 <b>Users ({total} total)</b>\n"]
    for u in all_u[:50]:
        icon = "👑" if u.get("role")=="owner" else "⭐" if u.get("role")=="admin" else \
               "💎" if db.is_premium_active(u["telegram_id"]) else "🚫" if u.get("is_blocked") else "👤"
        name = f"@{u['username']}" if u.get("username") else "no_username"
        prem = " [P]"   if db.is_premium_active(u["telegram_id"]) else ""
        ban  = " [BAN]" if u.get("is_blocked") else ""
        lines.append(f"{icon} <code>{u['telegram_id']}</code> {esc(name)}{prem}{ban}")
    if total > 50: lines.append(f"\n<i>...and {total-50} more</i>")
    lines.append("\n<i>Use /user &lt;id&gt; to manage</i>")
    await edit_msg(q, "\n".join(lines), InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download All", callback_data="op_users_dl"),
         InlineKeyboardButton("🔄 Refresh",      callback_data="op_users")],
        [InlineKeyboardButton("‹ Back", callback_data="owner_panel")],
    ]))

async def show_user_panel(chat_id: int, admin_id: int, msgid, target_id: int, app: Application, send_new: bool = False):
    if not is_admin(admin_id): return
    u = db.get_user(target_id)
    if not u:
        await app.bot.send_message(chat_id, f"❌ User not found: <code>{target_id}</code>", parse_mode=HTML)
        return

    prem    = db.is_premium_active(target_id)
    vip_u   = db.is_vip(target_id)
    role    = "👑 Owner" if u.get("role")=="owner" else "⭐ Admin" if u.get("role")=="admin" else "👤 User"
    prem_t  = ("✅ VIP" if vip_u else "✅ Premium") + (" Lifetime" if not u.get("premium_until") else f" until {u['premium_until'][:10]}") if prem else "❌ None"
    today   = datetime.now().date().isoformat()
    used    = u.get("daily_checks", 0) if u.get("daily_reset") == today else 0

    ban_row  = [InlineKeyboardButton("✅ Unban" if u.get("is_blocked") else "🚫 Ban",
               callback_data=f"user_{'unban' if u.get('is_blocked') else 'ban'}_{target_id}")]
    prem_row = ([InlineKeyboardButton(f"{'👑 VIP' if vip_u else '💎 Prem'} — Remove", callback_data=f"user_remprem_{target_id}"),
                 InlineKeyboardButton("💎 To Prem" if vip_u else "👑 To VIP",
                                      callback_data=f"user_prem30_{target_id}" if vip_u else f"user_vip30_{target_id}")]
                if prem else
                [InlineKeyboardButton("💎 +30d Prem",  callback_data=f"user_prem30_{target_id}"),
                 InlineKeyboardButton("♾ Prem Life",  callback_data=f"user_premlife_{target_id}")])
    vip_row  = ([InlineKeyboardButton("👑 +30d VIP", callback_data=f"user_vip30_{target_id}"),
                 InlineKeyboardButton("♾ VIP Life",  callback_data=f"user_viplife_{target_id}")]
                if not prem else [])
    bonus_r1 = [InlineKeyboardButton("🎟 +100",  callback_data=f"user_bonus_100_{target_id}"),
                InlineKeyboardButton("🎟 +500",  callback_data=f"user_bonus_500_{target_id}"),
                InlineKeyboardButton("🎟 +1000", callback_data=f"user_bonus_1000_{target_id}")]
    bonus_r2 = [InlineKeyboardButton("🎟 +5000",         callback_data=f"user_bonus_5000_{target_id}"),
                InlineKeyboardButton("❌ Remove Checks", callback_data=f"user_clrbonus_{target_id}")]
    role_row = ([InlineKeyboardButton("⬇️ Demote", callback_data=f"user_demote_{target_id}")]
                if u.get("role") == "admin"
                else [InlineKeyboardButton("⬆️ Promote to Admin", callback_data=f"user_promote_{target_id}")])

    rows = [ban_row, prem_row]
    if vip_row: rows.append(vip_row)
    rows += [bonus_r1, bonus_r2, role_row,
             [InlineKeyboardButton("‹ Back to Users", callback_data="op_users")]]

    text = (
        f"👤 <b>User Details</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
        f"📛 <b>Username:</b> @{esc(u.get('username')) or 'N/A'}\n"
        f"🎭 <b>Role:</b> {role}\n\n"
        f"<b>💎 Premium:</b> {prem_t}\n"
        f"<b>🚫 Banned:</b> {'Yes' if u.get('is_blocked') else 'No'}\n\n"
        f"<b>📊 Stats:</b>\n"
        f"  ├ Total: <b>{fmt(u.get('numbers_checked',0))}</b>\n"
        f"  ├ Today: <b>{used}</b>\n"
        f"  └ Bonus: <b>{u.get('bonus_checks',0) or 0}</b>\n\n"
        f"📅 <b>Joined:</b> <i>{str(u.get('joined_at',''))[:10]}</i>"
    )
    markup = InlineKeyboardMarkup(rows)
    await app.bot.send_message(chat_id, text, parse_mode=HTML, reply_markup=markup)

# ── User Actions ──────────────────────────────────────────────────────────────

async def handle_user_ban(chat_id: int, admin_id: int, target_id: int, ban: bool, app: Application):
    if not is_admin(admin_id): return
    db.block_user(target_id, ban)
    icon = "🚫" if ban else "✅"
    msg  = "banned" if ban else "unbanned"
    log  = f"{icon} <b>User {msg.title()}</b>\n🆔 <code>{target_id}</code>\nBy: <code>{admin_id}</code>"
    await send_log(app, log)
    try:
        await app.bot.send_message(target_id,
            f"🚫 <b>You have been banned.</b>" if ban else "✅ <b>Ban lifted!</b> Type /start",
            parse_mode=HTML)
    except: pass
    await show_user_panel(chat_id, admin_id, None, target_id, app, send_new=True)

async def handle_add_premium(chat_id: int, admin_id: int, target_id: int, days, plan: str, app: Application):
    if not is_admin(admin_id): return
    until = None if days == "lifetime" else datetime.now() + timedelta(days=int(days))
    db.create_user(target_id, "", "")
    db.set_premium(target_id, until, plan)
    is_vip_plan = plan == "vip"
    exp_txt     = until.strftime("%d %b %Y") if until else "Lifetime"
    label       = "👑 VIP" if is_vip_plan else "💎 Premium"
    log = f"{label} <b>Added</b>\n🆔 <code>{target_id}</code>\n⏳ {exp_txt}\nBy: <code>{admin_id}</code>"
    await send_log(app, log)
    await broadcast_owner(app, log)
    try:
        await app.bot.send_message(target_id,
            f"{'👑' if is_vip_plan else '💎'} <b>{label} Activated!</b>\n\n"
            f"{'Until ' + until.strftime('%d %b %Y') if until else '✨ Lifetime!'}\n\nEnjoy!",
            parse_mode=HTML)
    except: pass
    await app.bot.send_message(chat_id, f"✅ {label} added to <code>{target_id}</code> — {exp_txt}", parse_mode=HTML)
    await show_user_panel(chat_id, admin_id, None, target_id, app, send_new=True)

async def handle_remove_premium(chat_id: int, admin_id: int, target_id: int, app: Application):
    if not is_admin(admin_id): return
    db.remove_premium(target_id)
    await send_log(app, f"💔 <b>Premium Removed</b>\n🆔 <code>{target_id}</code>")
    try: await app.bot.send_message(target_id, "💔 <b>Your premium has been removed.</b>", parse_mode=HTML)
    except: pass
    await app.bot.send_message(chat_id, f"✅ Premium removed from <code>{target_id}</code>", parse_mode=HTML)
    await show_user_panel(chat_id, admin_id, None, target_id, app, send_new=True)

async def handle_add_bonus(chat_id: int, admin_id: int, target_id: int, checks: int, app: Application):
    if not is_admin(admin_id): return
    db.add_bonus(target_id, checks)
    u = db.get_user(target_id)
    new_bonus = (u.get("bonus_checks", 0) or 0) if u else checks
    log = f"🎟 <b>Bonus Added</b>\n🆔 <code>{target_id}</code>\n💫 +{checks}\nBy: <code>{admin_id}</code>"
    await send_log(app, log)
    try:
        await app.bot.send_message(target_id,
            f"🎟 <b>Bonus Checks Added!</b>\n\n✅ <b>+{checks} checks</b>!\n📦 Total bonus: <b>{new_bonus}</b>",
            parse_mode=HTML)
    except: pass
    await app.bot.send_message(chat_id, f"✅ +{checks} checks added to <code>{target_id}</code>", parse_mode=HTML)

async def handle_clear_bonus(chat_id: int, admin_id: int, target_id: int, app: Application):
    if not is_admin(admin_id): return
    db.clear_bonus(target_id)
    try: await app.bot.send_message(target_id, "ℹ️ Your bonus checks have been reset to 0.", parse_mode=HTML)
    except: pass
    await app.bot.send_message(chat_id, f"✅ Bonus cleared for <code>{target_id}</code>", parse_mode=HTML)

async def handle_user_role(chat_id: int, admin_id: int, target_id: int, role: str, app: Application):
    if not is_owner(admin_id) and role == "admin": return
    db.update_role(target_id, role)
    label = "Admin" if role == "admin" else "User"
    await send_log(app, f"🎭 <b>Role Changed</b>\n🆔 <code>{target_id}</code> → {label}")
    try:
        await app.bot.send_message(target_id,
            f"⭐ <b>You are now an Admin!</b>" if role == "admin" else "👤 <b>Admin role removed.</b>",
            parse_mode=HTML)
    except: pass
    await show_user_panel(chat_id, admin_id, None, target_id, app, send_new=True)

# ── FSub Settings ─────────────────────────────────────────────────────────────

async def show_fsub_settings(q, uid: int):
    if not is_admin(uid): return
    channels = db.get_all_fsub()
    img      = db.get_setting("fsub_image")
    body = "🔒 <b>Force Subscribe</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    body += f"<b>📋 Channels ({len(channels)}):</b>\n"
    if not channels: body += "<i>None set.</i>\n"
    for i, ch in enumerate(channels, 1):
        link = ch.get("link") or ch["channel_id"]
        body += f"{i}. <a href=\"{esc(link)}\">{esc(ch.get('title') or ch['channel_id'])}</a> <code>{esc(ch['channel_id'])}</code>\n"
    body += f"\n<b>🖼 Image:</b> {'✅ Set' if img else '❌ Not set'}"
    rows = [[InlineKeyboardButton(f"🗑 Remove: {(ch.get('title') or ch['channel_id'])[:25]}",
             callback_data=f"fsub_del_{ch['channel_id']}")] for ch in channels]
    rows.append([InlineKeyboardButton("➕ Add Channel", callback_data="set_fsub_input"),
                 InlineKeyboardButton("🖼 Set Image",   callback_data="set_fsub_image")])
    if img: rows.append([InlineKeyboardButton("🗑 Remove Image", callback_data="fsub_img_remove")])
    rows.append([InlineKeyboardButton("‹ Back", callback_data="owner_panel")])
    await edit_msg(q, body, InlineKeyboardMarkup(rows))

# ── Bot Settings ──────────────────────────────────────────────────────────────

async def show_bot_settings(q, uid: int):
    if not is_admin(uid): return
    g = lambda k, d: db.get_setting(k) or d
    mode  = g("bot_mode", "public")
    maint = g("maintenance", "off")
    paid  = g("paid_mode",   "false")
    fl    = g("free_limit",  "20")
    pl    = g("prem_limit",  "500")
    bl    = g("bulk_limit",  "100")
    rb    = g("refer_bonus", "10")
    vl    = g("vip_limit",   "999999")
    vb    = g("vip_bulk",    "1000")
    mi    = g("menu_image",  "")
    upi   = g("upi_id",      "Not set")
    api_k = g("api_key",     "")
    br_ch = g("brand_channel","")
    br_nm = g("brand_name",  "WA Checker API")

    text = (
        f"⚙️ <b>Bot Settings</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 Mode: <code>{mode}</code> | 🔧 Maint: <code>{maint}</code>\n"
        f"💰 Paid: <code>{paid}</code>\n"
        f"👤 Free: <code>{fl}/day</code> | 💎 Prem: <code>{pl}/day</code>\n"
        f"👑 VIP Daily: <code>{'Unlimited' if vl=='999999' else vl}</code> | VIP Bulk: <code>{vb}</code>\n"
        f"📁 Bulk: <code>{bl}</code> | 🔗 Bonus: <code>{rb}</code>\n"
        f"🖼 Menu img: {'✅' if mi else '❌'} | 💳 UPI: <code>{upi}</code>\n"
        f"🔑 API Key: {'✅' if api_k else '❌'} | 📢 Brand: <code>{br_ch or 'Not set'}</code>"
    )
    await edit_msg(q, text, InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Public" if mode=="public" else "⬜ Public",   callback_data="set_public"),
         InlineKeyboardButton("✅ Private" if mode=="private" else "⬜ Private", callback_data="set_private")],
        [InlineKeyboardButton("🔧 Maint ON" if maint=="on" else "⬜ Maint ON", callback_data="maint_on"),
         InlineKeyboardButton("🔧 Maint OFF" if maint=="off" else "⬜ Maint OFF", callback_data="maint_off")],
        [InlineKeyboardButton("💰 Paid ON" if paid=="true" else "⬜ Paid ON",   callback_data="paid_on"),
         InlineKeyboardButton("🆓 Paid OFF" if paid!="true" else "⬜ Paid OFF", callback_data="paid_off")],
        [InlineKeyboardButton("👤 Free Limit",    callback_data="set_free_limit"),
         InlineKeyboardButton("💎 Prem Limit",    callback_data="set_prem_limit")],
        [InlineKeyboardButton("📁 Bulk Limit",    callback_data="set_bulk_limit"),
         InlineKeyboardButton("🔗 Refer Bonus",   callback_data="set_refer_bonus")],
        [InlineKeyboardButton("👑 VIP Daily",      callback_data="set_vip_limit"),
         InlineKeyboardButton("👑 VIP Bulk",       callback_data="set_vip_bulk")],
        [InlineKeyboardButton("💳 Set UPI",        callback_data="set_upi_id"),
         InlineKeyboardButton("🔑 Set API Key",    callback_data="set_api_key")],
        [InlineKeyboardButton("📢 Brand Channel",  callback_data="set_brand_channel"),
         InlineKeyboardButton("🏷 Brand Name",     callback_data="set_brand_name")],
        [InlineKeyboardButton("🖼 Menu Image" if not mi else "🖼 Change Image", callback_data="set_menu_image")],
        [InlineKeyboardButton("‹ Back", callback_data="owner_panel")],
    ]))

# ── Stats ─────────────────────────────────────────────────────────────────────

async def show_stats(q, uid: int):
    if not is_admin(uid): return
    total  = db.get_total_stats()
    users  = db.get_all_users()
    prems  = sum(1 for u in users if db.is_premium_active(u["telegram_id"]))
    hist   = db.get_stats_history(7)
    wa_all = db.get_all_accounts()
    wa_txt = "\n".join(f"• {esc(a.get('label','?'))}: {a.get('total_checks',0)} checks, {a.get('ban_count',0)} bans" for a in wa_all) or "None"
    hist_t = "\n".join(f"• {h['date']}: {h.get('total_checks',0)}" for h in hist) or "No data"
    await edit_msg(q,
        f"📊 <b>Statistics</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{len(users)}</b> | 💎 Premium: <b>{prems}</b>\n\n"
        f"📱 Total checks: <b>{fmt(total.get('total_checks',0))}</b>\n"
        f"✅ Registered: <b>{fmt(total.get('registered_count',0))}</b>\n"
        f"❌ Not reg: <b>{fmt(total.get('not_registered_count',0))}</b>\n\n"
        f"📈 <b>Last 7 days:</b>\n{hist_t}\n\n"
        f"📱 <b>WA Accounts:</b>\n{wa_txt}",
        InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="owner_panel")]]))

# ── Redeem Panel ──────────────────────────────────────────────────────────────

async def show_redeem_panel(q, uid: int):
    if not is_admin(uid): return
    codes = await db.get_all_redeems()
    body  = "🎟 <b>Redeem Codes</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not codes:
        body += "<i>No codes yet.</i>"
    else:
        today = datetime.now().date().isoformat()
        for c in codes[:15]:
            used   = f"{c.get('used_count',0)}/{c.get('max_uses',1)}"
            active = "🟢" if c.get("is_active") else "🔴"
            body  += f"{active} <code>{esc(c['code'])}</code> — <b>+{c.get('checks',0)}</b> | {used}\n"
    rows = [[InlineKeyboardButton("➕ Create Code", callback_data="op_create_code")],
            [InlineKeyboardButton("‹ Back", callback_data="owner_panel")]]
    await edit_msg(q, body, InlineKeyboardMarkup(rows))

# ── API Keys Panel ────────────────────────────────────────────────────────────

async def show_api_keys(q, uid: int):
    if not is_admin(uid): return
    keys  = db.get_all_api_keys()
    today = datetime.now().date().isoformat()
    body  = "🔑 <b>API Keys</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not keys:
        body += "<i>No client keys yet.</i>"
    else:
        for k in keys:
            expired = k.get("expires_at") and datetime.fromisoformat(k["expires_at"]) < datetime.now()
            icon    = "🔴" if expired else "🟢"
            used    = k.get("used_today", 0) if k.get("reset_date") == today else 0
            limit   = "∞" if (k.get("daily_limit", 0) or 0) >= 999999 else k.get("daily_limit", 0)
            exp     = k["expires_at"][:10] if k.get("expires_at") else "Never"
            body   += f"{icon} <b>{esc(k.get('label','?'))}</b> [{k.get('plan','?')}]\n"
            body   += f"  📊 {used}/{limit} | 📅 {exp}\n"
            body   += f"  🔑 <code>{esc(k['key'])}</code>\n\n"
    rows = [[InlineKeyboardButton(f"🗑 {k.get('label','?')}", callback_data=f"revoke_api_{k['key']}") for k in keys[:1]]] if keys else []
    for k in keys[1:]:
        rows.append([InlineKeyboardButton(f"🗑 Revoke: {k.get('label','?')}", callback_data=f"revoke_api_{k['key']}")])
    rows.append([InlineKeyboardButton("➕ Create Key",   callback_data="op_create_api_key"),
                 InlineKeyboardButton("⚙️ Rate Settings", callback_data="op_api_settings")])
    rows.append([InlineKeyboardButton("‹ Back", callback_data="owner_panel")])
    await edit_msg(q, body, InlineKeyboardMarkup(rows))

async def show_api_settings(q, uid: int):
    if not is_admin(uid): return
    g = lambda k, d: db.get_setting(k) or d
    bfmt = lambda v: "∞ Unlimited" if v in ("0", 0) else str(v)
    text = (
        f"⚙️ <b>API Rate Settings</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>⚡ Req/Second:</b>\n"
        f"  💎 Basic:    <code>{g('api_rps_basic','3')}/sec</code>\n"
        f"  👑 Pro:      <code>{g('api_rps_pro','5')}/sec</code>\n"
        f"  🏢 Business: <code>{g('api_rps_business','10')}/sec</code>\n\n"
        f"<b>📦 Bulk Limit:</b>\n"
        f"  💎 Basic:    <code>{bfmt(g('api_bulk_basic','100'))}</code>\n"
        f"  👑 Pro:      <code>{bfmt(g('api_bulk_pro','500'))}</code>\n"
        f"  🏢 Business: <code>{bfmt(g('api_bulk_business','0'))}</code>"
    )
    await edit_msg(q, text, InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Basic RPS",    callback_data="set_api_rps_basic"),
         InlineKeyboardButton("⚡ Pro RPS",      callback_data="set_api_rps_pro")],
        [InlineKeyboardButton("⚡ Business RPS", callback_data="set_api_rps_business")],
        [InlineKeyboardButton("📦 Basic Bulk",    callback_data="set_api_bulk_basic"),
         InlineKeyboardButton("📦 Pro Bulk",      callback_data="set_api_bulk_pro")],
        [InlineKeyboardButton("📦 Business Bulk", callback_data="set_api_bulk_business")],
        [InlineKeyboardButton("‹ Back", callback_data="op_api_keys")],
    ]))
