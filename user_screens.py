"""User-facing screens — check, profile, premium, referral, etc."""
from __future__ import annotations
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import core.database as db
import core.wa_engine as wa
from core.helpers import is_admin, is_premium, is_vip, esc, fmt, BACK_BTN, edit_msg

HTML = ParseMode.HTML

async def show_check_number(q, uid: int, ctx):
    ctx.user_data["state"] = "check_single"
    await edit_msg(q,
        "🔍 <b>Check Single Number</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send number with country code:\n\n"
        "• <code>919876543210</code>  <i>(India)</i>\n"
        "• <code>14155552671</code>   <i>(USA)</i>",
        BACK_BTN)

async def show_bulk_check(q, uid: int, ctx):
    fl   = int(db.get_setting("free_limit", "20"))
    pl   = int(db.get_setting("prem_limit", "500"))
    bl   = int(db.get_setting("vip_bulk", "1000") if is_vip(uid) else db.get_setting("bulk_limit", "100"))
    prem = is_premium(uid)
    vip  = is_vip(uid)
    lims = db.get_remaining_checks(uid, fl, pl)
    tier = "👑 VIP" if vip else ("💎 Premium" if prem else "👤 Free")
    ctx.user_data["state"] = "bulk_check"
    await edit_msg(q,
        f"📋 <b>Bulk Number Check</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send numbers one per line or upload .txt file.\n\n"
        f"<b>📊 Quota:</b>\n"
        f"  • Daily limit:  <code>{'Unlimited' if vip else (pl if prem else fl)}</code>\n"
        f"  • Remaining:    <code>{'Unlimited' if vip else lims['remaining']}</code>\n"
        f"  • Per request:  <code>{bl}</code>\n"
        f"  • Tier:         <b>{tier}</b>",
        BACK_BTN)

async def show_tools(q, uid: int, ctx):
    count = await db.get_number_count(uid)
    await edit_msg(q,
        f"🧰 <b>Number Pool — Tools</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Upload numbers and dispense them one-by-one.\n\n"
        f"<b>📦 Pool:</b> <code>{count}</code> available",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Numbers",        callback_data="tools_upload")],
            [InlineKeyboardButton("🎲 Get Next",   callback_data="tools_get"),
             InlineKeyboardButton("⏭ Skip",        callback_data="tools_change")],
            [InlineKeyboardButton("🔍 Filter by Ending Digits", callback_data="tools_filter")],
            [InlineKeyboardButton("‹ Back to Menu",            callback_data="main_menu")],
        ]))

async def show_profile(q, uid: int, ctx):
    u = db.get_user(uid)
    if not u: return
    prem   = db.is_premium_active(uid)
    vip    = db.is_vip(uid)
    today  = datetime.now().date().isoformat()
    used   = u.get("daily_checks", 0) if u.get("daily_reset") == today else 0
    fl, pl = int(db.get_setting("free_limit","20")), int(db.get_setting("prem_limit","500"))
    lim    = 999999 if vip else (pl if prem else fl)
    role   = "👑 Owner" if u.get("role")=="owner" else "⭐ Admin" if u.get("role")=="admin" else "👑 VIP" if vip else "💎 Premium" if prem else "👤 Free"
    prem_t = ""
    if prem:
        if not u.get("premium_until"): prem_t = "\n💎 Plan: <b>Lifetime</b>"
        else:
            d    = datetime.fromisoformat(u["premium_until"])
            diff = (d - datetime.now()).days
            prem_t = f"\n💎 Plan: <b>{'VIP' if vip else 'Premium'}</b> — {diff}d left"
    await edit_msg(q,
        f"👤 <b>My Profile</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📛 <b>Username:</b> @{esc(u.get('username')) or 'N/A'}\n"
        f"🎭 <b>Role:</b> {role}{prem_t}\n\n"
        f"<b>📊 Stats</b>\n"
        f"  ├ Total:  <b>{fmt(u.get('numbers_checked',0))}</b>\n"
        f"  ├ Today:  <b>{used} / {'∞' if vip else lim}</b>\n"
        f"  └ Bonus:  <b>{u.get('bonus_checks',0) or 0}</b>\n\n"
        f"<b>🎁 Referral</b>\n"
        f"  ├ Code:   <code>{u.get('refer_code','N/A')}</code>\n"
        f"  └ Total:  <b>{u.get('refer_count',0)}</b> friends\n\n"
        f"📅 <b>Joined:</b> <i>{str(u.get('joined_at',''))[:10]}</i>",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Export Data", callback_data="export_profile")],
            [InlineKeyboardButton("‹ Back to Menu", callback_data="main_menu")],
        ]))

async def show_premium_info(q, uid: int):
    prem = is_premium(uid)
    vip  = is_vip(uid)
    u    = db.get_user(uid)
    if prem and u:
        plan   = "👑 VIP" if vip else "💎 Premium"
        if not u.get("premium_until"): exp = f"✨ <b>Lifetime {plan}</b>"
        else:
            d    = datetime.fromisoformat(u["premium_until"])
            diff = (d - datetime.now()).days
            exp  = f"⏳ <b>{diff} day(s) remaining</b>\n📅 {d.strftime('%d %b %Y')}"
        vl = db.get_setting("vip_limit","999999")
        vb = db.get_setting("vip_bulk","1000")
        pl = db.get_setting("prem_limit","500")
        bl = db.get_setting("bulk_limit","100")
        benefits = (f"  ✅ <b>Unlimited</b> checks/day\n  ✅ Bulk up to <b>{vb}</b>\n  ✅ Top priority"
                    if vip else
                    f"  ✅ <b>{pl}</b> checks/day\n  ✅ Bulk up to <b>{bl}</b>\n  ✅ Priority")
        await edit_msg(q,
            f"{plan} <b>Active</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{exp}\n\n<b>✨ Benefits:</b>\n{benefits}\n\n<i>Thank you! 🙏</i>",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Upgrade/Renew", callback_data="premium_plans")],
                [InlineKeyboardButton("‹ Back", callback_data="main_menu")],
            ]))
        return

    upi = db.get_setting("upi_id") or "Contact owner"
    await edit_msg(q,
        f"💎 <b>Premium Plans</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📅 Monthly Subscriptions</b>\n\n"
        f"🆓 <b>Free</b>       — ₹0/month\n  └ {db.get_setting('free_limit','20')}/day\n\n"
        f"💎 <b>Basic</b>      — ₹99/month\n  └ 300/day\n\n"
        f"👑 <b>Pro</b>        — ₹249/month\n  └ 1,000/day\n\n"
        f"🏢 <b>Business</b>   — ₹599/month\n  └ Unlimited/day\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🎟 Check Bundles</b>  <i>(₹10 = 100 checks)</i>\n\n"
        f"  📦 100 checks  — <b>₹10</b>\n"
        f"  📦 500 checks  — <b>₹50</b>\n"
        f"  📦 1,000 checks — <b>₹100</b>\n"
        f"  📦 5,000 checks — <b>₹500</b>\n\n"
        f"💳 Pay via UPI: <code>{esc(upi)}</code>",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Basic — ₹99",    callback_data="buy_basic"),
             InlineKeyboardButton("👑 Pro — ₹249",     callback_data="buy_pro")],
            [InlineKeyboardButton("🏢 Business — ₹599",callback_data="buy_business")],
            [InlineKeyboardButton("🎟 Check Bundles",   callback_data="buy_bundles")],
            [InlineKeyboardButton("💬 Contact Owner",   url="https://t.me/bhardwa_j")],
            [InlineKeyboardButton("‹ Back",             callback_data="main_menu")],
        ]))

async def show_plan_detail(q, uid: int, plan: str):
    plans = {
        "basic":    {"name":"Basic",    "price":"₹99/month",  "daily":"300",   "icon":"💎"},
        "pro":      {"name":"Pro",      "price":"₹249/month", "daily":"1,000", "icon":"👑"},
        "business": {"name":"Business", "price":"₹599/month", "daily":"Unlimited","icon":"🏢"},
    }
    p   = plans.get(plan); upi = db.get_setting("upi_id") or "Contact owner"
    if not p: return
    await edit_msg(q,
        f"{p['icon']} <b>{p['name']} — {p['price']}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>✨ Benefits:</b>\n"
        f"  ✅ <b>{p['daily']}</b> checks/day\n"
        f"  ✅ Bulk checking\n"
        f"  ✅ Priority processing\n\n"
        f"<b>💳 How to pay:</b>\n"
        f"1. Send to UPI: <code>{esc(upi)}</code>\n"
        f"2. Screenshot bhejo owner ko\n"
        f"3. Plan minutes mein activate!",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Send Screenshot", url="https://t.me/bhardwa_j")],
            [InlineKeyboardButton("‹ Back to Plans", callback_data="premium_info")],
        ]))

async def show_bundle_detail(q, uid: int):
    upi = db.get_setting("upi_id") or "Contact owner"
    await edit_msg(q,
        f"🎟 <b>Check Bundles</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Rate: ₹10 = 100 checks</i>\n\n"
        f"  📦 100 checks   — <b>₹10</b>\n"
        f"  📦 500 checks   — <b>₹50</b>\n"
        f"  📦 1,000 checks — <b>₹100</b>\n"
        f"  📦 5,000 checks — <b>₹500</b>\n\n"
        f"✅ Never expire!\n\n"
        f"<b>💳 Pay to UPI:</b>\n<code>{esc(upi)}</code>\n\n"
        f"Screenshot owner ko bhejo → checks add honge!",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact Owner", url="https://t.me/bhardwa_j")],
            [InlineKeyboardButton("‹ Back", callback_data="premium_info")],
        ]))

async def show_referral(q, uid: int, ctx):
    u     = db.get_user(uid)
    if not u: return
    bonus = int(db.get_setting("refer_bonus","10"))
    me    = await ctx.bot.get_me()
    link  = f"https://t.me/{me.username}?start={u.get('refer_code','')}"
    await edit_msg(q,
        f"🎁 <b>Referral Program</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Invite friends → earn <b>+{bonus} checks</b> each!\n\n"
        f"<b>🔗 Your Link:</b>\n<code>{link}</code>\n\n"
        f"<b>📈 Stats:</b>\n"
        f"  ├ Friends: <b>{u.get('refer_count',0)}</b>\n"
        f"  └ Earned:  <b>{u.get('bonus_checks',0)} checks</b>",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("‹ Back to Menu", callback_data="main_menu")],
        ]))

async def show_status(q, uid: int):
    checkers = wa.get_checkers()
    ok = bool(checkers)
    await edit_msg(q,
        f"📡 <b>Bot Status</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{'🟢' if ok else '🔴'} <b>{'Online & Working' if ok else 'Currently Offline'}</b>\n\n"
        f"<i>{'✅ You can check numbers now!' if ok else '⚠️ Try again in a few minutes.'}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n<b>🤖 WA Checker</b> — <i>by @Bhardwa_j</i>",
        BACK_BTN)

async def show_help(q, uid: int):
    await edit_msg(q,
        "📖 <b>Help & Guide</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🔍 Check Number</b> — single number\n"
        "<b>📋 Bulk Check</b> — multiple / .txt file\n"
        "<b>🧰 Tools</b> — number pool, filter\n"
        "<b>💎 Premium</b> — higher limits\n"
        "<b>🎁 Referral</b> — earn free checks\n"
        "<b>🎟 Redeem</b> — use gift codes\n\n"
        "━━━━━━━━━━━━━━━━━━━━",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Support", url="https://t.me/bhardwa_j")],
            [InlineKeyboardButton("‹ Back",     callback_data="main_menu")],
        ]))

async def show_redeem_screen(q, uid: int, ctx):
    ctx.user_data["state"] = "redeem_code"
    await edit_msg(q,
        "🎟 <b>Redeem Code</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Enter your code to get bonus checks:\n\n<i>Codes are case-insensitive.</i>",
        BACK_BTN)
