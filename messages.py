"""Message handlers — text, photo, document"""
from __future__ import annotations
import io
import re
import secrets
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

<<<<<<< HEAD
import database as db
import wa_engine as wa
from helpers import (is_admin, is_authorized, is_premium, is_vip,
                           is_maintenance, esc, fmt, progress_bar, BACK_BTN,
                           send_log, broadcast_owner)
from menus import send_welcome, send_fsub_prompt, check_fsub, refresh_fsub
=======
import core.database as db
import core.wa_engine as wa
from core.helpers import (is_admin, is_authorized, is_premium, is_vip,
                           is_maintenance, esc, fmt, progress_bar, BACK_BTN,
                           send_log, broadcast_owner)
from core.menus import send_welcome, send_fsub_prompt, check_fsub, refresh_fsub
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e

HTML = ParseMode.HTML

# ── Main message handler ──────────────────────────────────────────────────────

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg      = update.message
    uid      = msg.from_user.id
    username = msg.from_user.username or ""
    fname    = msg.from_user.first_name or ""
    text     = msg.text or ""

    if is_maintenance() and not is_admin(uid): return

    db.create_user(uid, username, fname)

    if not await check_fsub(ctx.application, uid):
        return await send_fsub_prompt(msg.chat_id, uid, ctx.application)

    if not is_authorized(uid):
        return await msg.reply_text(
            "🔒 <b>Access Denied</b>\n\nContact <a href='https://t.me/bhardwa_j'>@Bhardwa_j</a>",
            parse_mode=HTML, disable_web_page_preview=True)

    state = ctx.user_data.get("state", "")

    # ── Admin states ──────────────────────────────────────────────────────────

    if state == "broadcast":
        ctx.user_data.clear()
        users = db.get_all_users()
        sent = failed = 0
        sm = await msg.reply_text(f"📢 Broadcasting to {len(users)} users...")
        for u in users:
            try: await ctx.bot.send_message(u["telegram_id"], text, parse_mode=HTML); sent += 1
            except: failed += 1
        await sm.edit_text(f"📢 <b>Done!</b>\n✅ {sent} | ❌ {failed}", parse_mode=HTML)
        return

    if state == "add_account":
        ctx.user_data.clear()
        aid = re.sub(r'\s+', '_', text.strip().lower())
        if not re.match(r'^[a-z0-9_]+$', aid):
            return await msg.reply_text("❌ Invalid. Use lowercase, numbers, underscores.")
        if db.get_account(aid):
            return await msg.reply_text(f"❌ Account <code>{esc(aid)}</code> exists.", parse_mode=HTML)
        db.add_account(aid, aid, "checker")
        wa.accounts[aid] = wa.WAAccount(account_id=aid, account_type="checker")
        log = f"➕ <b>Account Added</b>\n🆔 <code>{esc(aid)}</code>"
        await send_log(ctx.application, log)
        await broadcast_owner(ctx.application, log)
        return await msg.reply_text(f"✅ <b>{esc(aid)}</b> created!", parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📷 QR",   callback_data=f"wa_qr_{aid}"),
                 InlineKeyboardButton("🔗 Pair", callback_data=f"wa_pair_{aid}")],
                [InlineKeyboardButton("‹ Back",  callback_data="op_accounts")]]))

    if state == "pair_wa":
        account_id = ctx.user_data.get("pair_account", "")
        ctx.user_data.clear()
        sm = await msg.reply_text(f"⏳ Getting pairing code for <b>{esc(account_id)}</b>...", parse_mode=HTML)
        try:
            code = await wa.get_pairing_code(account_id, text.strip())
            await sm.edit_text(
                f"🔗 <b>Pairing Code</b>\n\n<code>{code}</code>\n\n"
                f"WhatsApp → Settings → Linked Devices → Link a Device → Phone number",
                parse_mode=HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="op_accounts")]]))
        except Exception as e:
            await sm.edit_text(f"❌ Failed: {esc(str(e))}", parse_mode=HTML)
        return

    if state == "user_wa_pair":
        ctx.user_data.clear()
        account_id = f"user_{uid}"
        db.add_account(account_id, f"@{username or uid}", "checker")
        sm = await msg.reply_text("⏳ Getting pairing code...", parse_mode=HTML)
        try:
            code = await wa.get_pairing_code(account_id, text.strip(), "checker")
            log  = f"🔗 <b>User WA Pairing</b>\n👤 @{esc(username)} (<code>{uid}</code>)"
            await send_log(ctx.application, log)
            await sm.edit_text(
                f"🔗 <b>Pairing Code</b>\n\n<code>{code}</code>\n\n"
                f"WhatsApp → Settings → Linked Devices → Phone number", parse_mode=HTML)
        except Exception as e:
            await sm.edit_text(f"❌ Failed: {esc(str(e))}", parse_mode=HTML)
        return

    if state == "add_premium_uid":
        try: tid = int(text.strip())
        except: return await msg.reply_text("❌ Invalid ID.")
        ctx.user_data["state"]     = "add_premium_days"
        ctx.user_data["target_id"] = tid
        return await msg.reply_text(f"💎 Adding premium to <code>{tid}</code>\n\nSend days or <code>lifetime</code>:", parse_mode=HTML)

    if state == "add_premium_days":
        target = ctx.user_data.get("target_id")
        ctx.user_data.clear()
        val = text.strip().lower()
        if val == "lifetime": until = None
        else:
            try: until = datetime.now() + timedelta(days=int(val))
            except: return await msg.reply_text('❌ Send number or "lifetime"')
        db.create_user(target, "", "")
        db.set_premium(target, until)
        exp = until.strftime("%d %b %Y") if until else "Lifetime"
        try: await ctx.bot.send_message(target, f"💎 <b>Premium Activated!</b>\n\n{exp}", parse_mode=HTML)
        except: pass
        return await msg.reply_text(f"✅ Premium → <code>{target}</code> — {exp}", parse_mode=HTML)

    if state == "add_checks":
        ctx.user_data.clear()
        parts = text.strip().split()
        if len(parts) < 2:
            return await msg.reply_text("❌ Format: <code>USER_ID CHECKS</code>", parse_mode=HTML)
        tid, checks = int(parts[0]), int(parts[1])
        db.create_user(tid, "", "")
        db.add_bonus(tid, checks)
        try: await ctx.bot.send_message(tid, f"🎟 <b>+{checks} bonus checks!</b>", parse_mode=HTML)
        except: pass
        return await msg.reply_text(f"✅ +{checks} checks → <code>{tid}</code>", parse_mode=HTML)

    if state == "set_fsub":
        ctx.user_data.clear()
        chid = text.strip()
        info = await refresh_fsub(ctx.application, chid)
        db.add_fsub(chid, info["title"], info.get("link",""))
        return await msg.reply_text(
            f"✅ <b>Channel Added!</b>\n\n📢 <b>{esc(info['title'])}</b>\n🆔 <code>{esc(chid)}</code>\n\n⚠️ Make bot admin in this channel!",
            parse_mode=HTML, disable_web_page_preview=True)

    if state == "set_fsub_image":
        ctx.user_data.clear()
        db.set_setting("fsub_image", text.strip())
        return await msg.reply_text("✅ FSub image URL saved!")

    if state == "set_menu_image":
        ctx.user_data.clear()
        db.set_setting("menu_image", text.strip())
        return await msg.reply_text("✅ Menu image URL saved!")

    if state == "set_log_group":
        ctx.user_data.clear()
        db.set_setting("log_group_id", text.strip())
        return await msg.reply_text(f"✅ Log group set: <code>{esc(text.strip())}</code>", parse_mode=HTML)

    # Settings states
    settings_map = {
        "set_free_limit":       "free_limit",
        "set_prem_limit":       "prem_limit",
        "set_bulk_limit":       "bulk_limit",
        "set_refer_bonus":      "refer_bonus",
        "set_vip_limit":        "vip_limit",
        "set_vip_bulk":         "vip_bulk",
        "set_upi_id":           "upi_id",
        "set_api_key":          "api_key",
        "set_brand_channel":    "brand_channel",
        "set_brand_name":       "brand_name",
        "set_api_rps_basic":    "api_rps_basic",
        "set_api_rps_pro":      "api_rps_pro",
        "set_api_rps_business": "api_rps_business",
        "set_api_bulk_basic":   "api_bulk_basic",
        "set_api_bulk_pro":     "api_bulk_pro",
        "set_api_bulk_business":"api_bulk_business",
    }
    if state in settings_map:
        ctx.user_data.clear()
        val = text.strip()
        if state == "set_brand_channel" and not val.startswith("@"):
            val = "@" + val
        db.set_setting(settings_map[state], val)
        return await msg.reply_text(f"✅ <b>{settings_map[state].replace('_',' ').title()}</b> set to <code>{esc(val)}</code>", parse_mode=HTML)

    if state == "create_code":
        ctx.user_data.clear()
        parts = text.strip().split()
        if len(parts) < 2:
            return await msg.reply_text("❌ Format: <code>CODE CHECKS MAXUSERS</code>\nExample: <code>SUMMER25 50 10</code>", parse_mode=HTML)
        code_name = parts[0].upper() if parts[0].lower() != "auto" else "CODE" + secrets.token_hex(3).upper()
        code_name = re.sub(r'[^A-Z0-9]', '', code_name)
        checks    = int(parts[1])
        max_uses  = int(parts[2]) if len(parts) > 2 else 1
        actual    = max_uses if max_uses > 0 else 999999
        try:
            await db.create_redeem(code_name, checks, actual, uid)
            limit_txt = "Unlimited" if actual >= 999999 else str(actual)
            return await msg.reply_text(
                f"✅ <b>Code Created!</b>\n\n🎟 <code>{code_name}</code>\n💫 +{checks} checks | 👥 {limit_txt} uses",
                parse_mode=HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎟 View Codes", callback_data="op_redeem")]]))
        except Exception as e:
            return await msg.reply_text(f"❌ Error: {esc(str(e))}", parse_mode=HTML)

    if state == "create_api_key":
        ctx.user_data.clear()
        parts = text.strip().split()
        if len(parts) < 3:
            return await msg.reply_text("❌ Format: <code>LABEL PLAN DAYS</code>", parse_mode=HTML)
        label, plan, days_str = parts[0], parts[1].lower(), parts[2]
        limits = {"basic": 1000, "pro": 10000, "business": 999999}
        if plan not in limits:
            return await msg.reply_text("❌ Plan must be: basic / pro / business")
        days    = int(days_str)
        expires = (datetime.now() + timedelta(days=days)).isoformat() if days > 0 else None
        key     = secrets.token_hex(20)
        obj = {
            "key": key, "label": label, "plan": plan,
            "daily_limit": limits[plan], "used_today": 0,
            "reset_date": datetime.now().date().isoformat(),
            "expires_at": expires, "owner_id": uid,
            "created_at": datetime.now().isoformat(),
        }
        db.save_api_key(obj)
        public_url = db.get_setting("brand_channel") and f"https://api.dhairyabh21.workers.dev" or "https://your-api.workers.dev"
        exp_txt = datetime.fromisoformat(expires).strftime("%d %b %Y") if expires else "Never"
        lim_txt = "Unlimited" if limits[plan] >= 999999 else f"{limits[plan]:,}"
        return await msg.reply_text(
            f"✅ <b>API Key Created!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>{esc(label)}</b>\n📦 {plan} ({lim_txt}/day)\n📅 Expires: {exp_txt}\n\n"
            f"🔑 <b>Key:</b>\n<code>{key}</code>\n\n"
            f"<b>1️⃣ Single:</b>\n<code>{public_url}/WSCK?phone=919876543210&key={key}</code>\n\n"
            f"<b>2️⃣ Bulk (POST):</b>\n<code>{public_url}/WSCK/bulk?key={key}</code>\n"
            f"Body: <code>{{\"phones\":[\"919876543210\"]}}</code>",
            parse_mode=HTML, disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔑 View Keys", callback_data="op_api_keys")]]))

    # ── Redeem code ───────────────────────────────────────────────────────────
    if state == "redeem_code":
        ctx.user_data.clear()
        code   = text.strip().upper()
        result = await db.use_redeem(code, uid)
        if result["success"]:
            u   = db.get_user(uid)
            log = (f"🎟 <b>Code Redeemed</b>\n👤 @{esc(username)} (<code>{uid}</code>)\n"
                   f"🎟 Code: <code>{esc(code)}</code>\n💫 +{result['checks']}")
            await send_log(ctx.application, log)
            await broadcast_owner(ctx.application, log)
            return await msg.reply_text(
                f"🎉 <b>Redeemed!</b>\n\n✅ <b>+{result['checks']} bonus checks!</b>",
                parse_mode=HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="main_menu")]]))
        reasons = {
            "already_redeemed": "❌ Already redeemed.",
            "invalid_code":     "❌ Invalid or expired code.",
            "expired":          "❌ Code limit reached.",
        }
        return await msg.reply_text(
            f"🎟 <b>Failed</b>\n\n{reasons.get(result.get('reason',''), '❌ Error')}",
            parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data="redeem"),
                                                InlineKeyboardButton("‹ Back", callback_data="main_menu")]]))

    # ── Filter digits ─────────────────────────────────────────────────────────
    if state == "filter_digits":
        ctx.user_data_copy = dict(ctx.user_data)
        numbers = ctx.user_data.get("numbers", [])
        ctx.user_data.clear()
        digits = re.sub(r'\D', '', text.strip())
        if not digits:
            return await msg.reply_text("❌ Send digits only. Example: <code>0247</code>", parse_mode=HTML)
        found = [n for n in numbers if n.endswith(digits)]
        if not found:
            return await msg.reply_text(
                f"🔍 No numbers ending with <code>{esc(digits)}</code>\nTotal checked: {len(numbers)}",
                parse_mode=HTML)
        if len(found) <= 20:
            result_text = "\n".join(f"<code>{esc(n)}</code>" for n in found)
            return await msg.reply_text(
                f"✅ <b>{len(found)} number(s) ending with <code>{esc(digits)}</code>:</b>\n\n{result_text}",
                parse_mode=HTML)
        buf = io.BytesIO("\n".join(found).encode()); buf.name = f"filtered_{digits}.txt"
        return await ctx.bot.send_document(msg.chat_id, buf,
            caption=f"✅ <b>{len(found)} numbers</b> ending with <code>{esc(digits)}</code>",
            parse_mode=HTML)

    # ── Number checking ───────────────────────────────────────────────────────
    if state not in ("check_single", "bulk_check"):
        return await send_welcome(msg.chat_id, uid, ctx.application)

    if not wa.has_checker():
        return await msg.reply_text("❌ <b>No accounts connected.</b>", parse_mode=HTML)

    if db.get_setting("paid_mode") == "true" and not is_premium(uid) and not is_admin(uid):
        return await msg.reply_text("🔒 <b>Premium Required</b>", parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Plans", callback_data="premium_info")]]))

    nums = [n.replace(" ","").replace("+","") for n in re.split(r'[\n,\s]+', text)
            if re.match(r'^\+?\d{7,15}$', n.strip())]
    if not nums:
        return await msg.reply_text("❌ No valid numbers.\nFormat: <code>919876543210</code>", parse_mode=HTML)

    fl   = int(db.get_setting("free_limit","20"))
    pl   = int(db.get_setting("prem_limit","500"))
    bl   = int(db.get_setting("vip_bulk","1000") if is_vip(uid) else db.get_setting("bulk_limit","100"))
    lims = db.get_remaining_checks(uid, fl, pl)

    if lims["remaining"] <= 0:
        return await msg.reply_text(
            f"⏳ <b>Daily Limit Reached</b>\n\nAll <b>{lims['limit']}</b> checks used.",
            parse_mode=HTML,
            reply_markup=None if lims["is_premium"] else InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade", callback_data="premium_info")]]))

    if len(nums) > bl:
        return await msg.reply_text(f"❌ Max <b>{bl}</b> numbers per request.", parse_mode=HTML)

    ctx.user_data.clear()
    await _process_numbers(msg, uid, nums[:lims["remaining"]], ctx, always_txt=(state=="bulk_check"))


async def _process_numbers(msg, uid: int, numbers: list, ctx, always_txt: bool = False):
    import asyncio
    started = asyncio.get_event_loop().time()
    n_ckrs  = len(wa.get_checkers())
    done    = 0

    def prog_text(d, total):
        pct = 0 if total == 0 else int(d / total * 100)
        bar = progress_bar(d, total)
        return f"⏳ <b>Checking...</b> {d}/{total}\n<code>{bar}</code> {pct}%"

    sm = await msg.reply_text(prog_text(0, len(numbers)), parse_mode=HTML)

    async def on_prog(d, total):
        nonlocal done; done = d
        if d % 5 == 0 or d == total:
            try: await sm.edit_text(prog_text(d, total), parse_mode=HTML)
            except: pass

    results = await wa.bulk_check(numbers, on_prog)
    reg   = [r for r in results if r and r.get("is_registered") is True]
    noreg = [r for r in results if r and r.get("is_registered") is False]
    unk   = [r for r in results if r and r.get("is_registered") is None]

    db.increment_stats(len(reg), len(noreg))
    db.increment_checks(uid, len(numbers))

    # Supabase log
    if db._sb:
        try:
            r = db._sb.table("verification_jobs").insert({
                "telegram_user_id": uid,
                "telegram_username": db.get_user(uid)["username"] if db.get_user(uid) else None,
                "total_numbers": len(numbers),
                "registered_count": len(reg),
                "not_registered_count": len(noreg),
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
            }).execute()
        except: pass

    lines = [
        "✅ <b>Results</b>", "",
        f"📊 Total:       <code>{len(numbers)}</code>",
        f"✅ Registered:  <code>{len(reg)}</code>",
        f"❌ Not reg:     <code>{len(noreg)}</code>",
        f"❓ Unknown:     <code>{len(unk)}</code>",
    ]
    if n_ckrs > 1: lines.append(f"\n🔀 {n_ckrs} accounts in parallel")

    if always_txt or len(numbers) > 50:
        async def send_file(arr, name, cap):
            if not arr: return
            buf = io.BytesIO("\n".join(r["phone_number"] for r in arr).encode())
            buf.name = name
            await ctx.bot.send_document(msg.chat_id, buf, caption=cap, parse_mode=HTML)
        await send_file(reg,   "registered.txt",    f"✅ {len(reg)} registered")
        await send_file(noreg, "not_registered.txt", f"❌ {len(noreg)} not registered")
        await send_file(unk,   "unknown.txt",         f"❓ {len(unk)} unknown")
        lines += ["", "📎 Results as files."]
    else:
        for label, arr, icon in [("Registered",reg,"✅"),("Not Registered",noreg,"❌"),("Unknown",unk,"❓")]:
            if not arr: continue
            lines += ["", f"<b>{label}:</b>"]
            lines += [f"{icon} <code>{esc(r['phone_number'])}</code>" for r in arr[:30]]
            if len(arr) > 30: lines.append(f"  … +{len(arr)-30} more")

    try:
        await sm.edit_text("\n".join(lines), parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="main_menu")]]))
    except:
        await msg.reply_text("\n".join(lines), parse_mode=HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ Back", callback_data="main_menu")]]))


# ── Photo handler ─────────────────────────────────────────────────────────────

async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.message.from_user.id
    if not is_admin(uid): return
    state = ctx.user_data.get("state", "")
    if state not in ("set_fsub_image", "set_menu_image"): return
    ctx.user_data.clear()
    file_id = update.message.photo[-1].file_id
    key     = "fsub_image" if state == "set_fsub_image" else "menu_image"
    db.set_setting(key, file_id)
    label = "FSub" if state == "set_fsub_image" else "Menu"
    await update.message.reply_text(f"✅ <b>{label} image saved!</b>", parse_mode=HTML)


# ── Document handler ──────────────────────────────────────────────────────────

async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg   = update.message
    uid   = msg.from_user.id
    state = ctx.user_data.get("state", "")

    if not msg.document.file_name.endswith(".txt"):
        return await msg.reply_text("❌ Send a <code>.txt</code> file.", parse_mode=HTML)

    try:
        file    = await ctx.bot.get_file(msg.document.file_id)
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
        nums    = [n.replace(" ","").replace("+","") for n in re.split(r'[\n,\s]+', content)
                   if re.match(r'^\+?\d{7,15}$', n.strip())]
        if not nums: return await msg.reply_text("❌ No valid numbers found.")

        if state == "filter_pending_file":
            ctx.user_data["state"]   = "filter_digits"
            ctx.user_data["numbers"] = nums
            return await msg.reply_text(
                f"✅ <b>File received!</b> {len(nums)} numbers loaded.\n\n"
                f"Now send ending digits:\nExample: <code>0247</code>",
                parse_mode=HTML)

        if state == "upload":
            ctx.user_data.clear()
            for n in nums: await db.add_number(uid, n)
            return await msg.reply_text(f"✅ <b>{len(nums)} numbers</b> added!", parse_mode=HTML)

        if state != "bulk_check":
            return await msg.reply_text("📁 Tap <b>Bulk Check</b> first, then send file.", parse_mode=HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Bulk Check", callback_data="bulk_check")]]))

        if not wa.has_checker():
            return await msg.reply_text("❌ No accounts connected.")

        fl   = int(db.get_setting("free_limit","20"))
        pl   = int(db.get_setting("prem_limit","500"))
        bl   = int(db.get_setting("vip_bulk","1000") if is_vip(uid) else db.get_setting("bulk_limit","100"))
        lims = db.get_remaining_checks(uid, fl, pl)
        if lims["remaining"] <= 0: return await msg.reply_text("⏳ Daily limit reached.")
        if len(nums) > bl: return await msg.reply_text(f"❌ Max {bl} numbers.")

        ctx.user_data.clear()
        await _process_numbers(msg, uid, nums[:lims["remaining"]], ctx, always_txt=True)
    except Exception as e:
<<<<<<< HEAD
        await msg.reply_text(f"❌ Error: {esc(str(e))}")
=======
        await msg.reply_text(f"❌ Error: {esc(str(e))}")
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
