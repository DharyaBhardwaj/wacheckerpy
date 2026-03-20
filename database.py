"""
Database — Supabase as primary store
In-memory cache for fast reads
"""
from __future__ import annotations
import json
import random
import string
from datetime import datetime, date, timedelta
from typing import Optional
from supabase import create_client, Client
import config

# ── Init ──────────────────────────────────────────────────────────────────────
_sb: Client = create_client(config.SB_URL, config.SB_KEY) if config.SB_URL and config.SB_KEY else None

# ── Caches ────────────────────────────────────────────────────────────────────
_users:    dict[int, dict] = {}
_settings: dict[str, str]  = {}
_accounts: dict[str, dict] = {}
_stats:    dict[str, dict] = {}
_fsub:     list[dict]      = []
_refer:    set[int]        = set()
_api_keys: dict[str, dict] = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_refer(uid: int) -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"REF{base36(uid)}{suffix}"

def base36(n: int) -> str:
    chars = string.digits + string.ascii_uppercase
    result = ""
    while n:
        result = chars[n % 36] + result
        n //= 36
    return result or "0"

def _prem_active(u: dict) -> bool:
    if not u or not u.get("is_premium"): return False
    if not u.get("premium_until"): return True
    return datetime.fromisoformat(u["premium_until"]) > datetime.now()

def _sb_set(table: str, data: dict, conflict: str = None):
    if not _sb: return
    try:
        if conflict:
            _sb.table(table).upsert(data, on_conflict=conflict).execute()
        else:
            _sb.table(table).insert(data).execute()
    except Exception as e:
        print(f"[DB] {table} write error: {e}")

def _sb_update(table: str, data: dict, **filters):
    if not _sb: return
    try:
        q = _sb.table(table).update(data)
        for k, v in filters.items():
            q = q.eq(k, v)
        q.execute()
    except Exception as e:
        print(f"[DB] {table} update error: {e}")

# ── Boot load ─────────────────────────────────────────────────────────────────

async def init():
    if not _sb:
        print("[DB] No Supabase — running without persistence")
        return
    try:
        tables = {
            "users":       (_users,    "telegram_id"),
            "bot_settings":(_settings, "key"),
            "wa_accounts": (_accounts, "account_id"),
            "bot_stats":   (_stats,    "date"),
            "fsub_channels": None,
            "refer_log":   None,
            "api_keys":    (_api_keys,  "key"),
        }

        r = _sb.table("users").select("*").execute()
        for u in (r.data or []):
            _users[u["telegram_id"]] = u

        r = _sb.table("bot_settings").select("*").execute()
        for s in (r.data or []):
            _settings[s["key"]] = s["value"]

        r = _sb.table("wa_accounts").select("*").order("id").execute()
        for a in (r.data or []):
            _accounts[a["account_id"]] = a

        r = _sb.table("bot_stats").select("*").execute()
        for s in (r.data or []):
            _stats[s["date"]] = s

        r = _sb.table("fsub_channels").select("*").order("id").execute()
        _fsub.clear()
        _fsub.extend(r.data or [])

        r = _sb.table("refer_log").select("referred_id").execute()
        for row in (r.data or []):
            _refer.add(row["referred_id"])

        # API keys stored in settings as JSON
        raw = _settings.get("api_keys_store")
        if raw:
            keys = json.loads(raw)
            for k in keys:
                _api_keys[k["key"]] = k

        # Apply env overrides
        if config.FSUB_IMAGE:   set_setting("fsub_image", config.FSUB_IMAGE)
        if config.MENU_IMAGE:   set_setting("menu_image", config.MENU_IMAGE)
        if config.FSUB_CHANNELS:
            for ch in config.FSUB_CHANNELS:
                add_fsub(ch, ch, "")

        print(f"[DB] Loaded: {len(_users)} users, {len(_accounts)} accounts, {len(_settings)} settings, {len(_api_keys)} API keys")
    except Exception as e:
        print(f"[DB] Init error: {e}")

# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    return _settings.get(key) or default

def set_setting(key: str, value: str):
    _settings[key] = value
    _sb_set("bot_settings", {"key": key, "value": value}, conflict="key")

# ── Users ─────────────────────────────────────────────────────────────────────

def get_user(uid: int) -> Optional[dict]:
    return _users.get(uid)

def create_user(uid: int, username: str, first_name: str, role: str = "user") -> bool:
    if uid in _users:
        u = _users[uid]
        u["username"] = username
        u["first_name"] = first_name
        u["last_active"] = datetime.now().isoformat()
        _sb_update("users", {"username": username, "first_name": first_name, "last_active": u["last_active"]}, telegram_id=uid)
        return False
    code = _gen_refer(uid)
    u = {
        "telegram_id": uid, "username": username, "first_name": first_name,
        "role": role, "is_blocked": 0, "is_allowed": 0, "is_premium": 0,
        "premium_until": None, "premium_plan": None,
        "numbers_checked": 0, "daily_checks": 0,
        "daily_reset": date.today().isoformat(),
        "refer_code": code, "referred_by": None,
        "refer_count": 0, "bonus_checks": 0,
        "joined_at": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
    }
    _users[uid] = u
    _sb_set("users", u)
    return True

def get_all_users() -> list[dict]:
    return sorted(_users.values(), key=lambda u: u.get("joined_at", ""), reverse=True)

def update_role(uid: int, role: str):
    if uid in _users: _users[uid]["role"] = role
    _sb_update("users", {"role": role}, telegram_id=uid)

def block_user(uid: int, blocked: bool):
    if uid in _users: _users[uid]["is_blocked"] = 1 if blocked else 0
    _sb_update("users", {"is_blocked": 1 if blocked else 0}, telegram_id=uid)

def set_premium(uid: int, until: Optional[datetime], plan: str = "premium"):
    val = until.isoformat() if until else None
    if uid in _users:
        _users[uid].update({"is_premium": 1, "is_allowed": 1, "premium_until": val, "premium_plan": plan})
    _sb_update("users", {"is_premium": 1, "is_allowed": 1, "premium_until": val, "premium_plan": plan}, telegram_id=uid)

def remove_premium(uid: int):
    if uid in _users:
        _users[uid].update({"is_premium": 0, "premium_until": None, "premium_plan": None})
    _sb_update("users", {"is_premium": 0, "premium_until": None, "premium_plan": None}, telegram_id=uid)

def is_premium_active(uid: int) -> bool:
    return _prem_active(_users.get(uid))

def is_vip(uid: int) -> bool:
    u = _users.get(uid)
    return bool(u and _prem_active(u) and u.get("premium_plan") == "vip")

def get_remaining_checks(uid: int, free_lim: int, prem_lim: int) -> dict:
    u = _users.get(uid)
    if not u: return {"limit": free_lim, "used": 0, "remaining": free_lim, "is_premium": False, "is_vip": False}
    today = date.today().isoformat()
    used  = u["daily_checks"] if u.get("daily_reset") == today else 0
    prem  = _prem_active(u)
    vip   = prem and u.get("premium_plan") == "vip"
    limit = 999999 if vip else (prem_lim if prem else free_lim)
    bonus = u.get("bonus_checks", 0) or 0
    remaining = 999999 if vip else max(0, limit + bonus - used)
    return {"limit": limit, "used": used, "remaining": remaining, "is_premium": prem, "is_vip": vip, "bonus": bonus}

def increment_checks(uid: int, count: int):
    today = date.today().isoformat()
    u = _users.get(uid)
    if not u: return
    used = (u.get("daily_checks", 0) if u.get("daily_reset") == today else 0) + count
    u["daily_checks"]    = used
    u["daily_reset"]     = today
    u["numbers_checked"] = (u.get("numbers_checked", 0) or 0) + count
    u["last_active"]     = datetime.now().isoformat()
    _sb_update("users", {
        "daily_checks": used, "daily_reset": today,
        "numbers_checked": u["numbers_checked"], "last_active": u["last_active"]
    }, telegram_id=uid)

def add_bonus(uid: int, amount: int):
    u = _users.get(uid)
    if not u: return
    new_bonus = (u.get("bonus_checks", 0) or 0) + amount
    u["bonus_checks"] = new_bonus
    _sb_update("users", {"bonus_checks": new_bonus}, telegram_id=uid)

def clear_bonus(uid: int):
    if uid in _users: _users[uid]["bonus_checks"] = 0
    _sb_update("users", {"bonus_checks": 0}, telegram_id=uid)

# ── Referral ──────────────────────────────────────────────────────────────────

def get_user_by_refer(code: str) -> Optional[dict]:
    return next((u for u in _users.values() if u.get("refer_code") == code), None)

def apply_referral(referrer_id: int, referred_id: int, bonus: int = 10) -> bool:
    if referred_id in _refer: return False
    _refer.add(referred_id)
    r = _users.get(referrer_id)
    if r:
        r["refer_count"]  = (r.get("refer_count", 0) or 0) + 1
        r["bonus_checks"] = (r.get("bonus_checks", 0) or 0) + bonus
        _sb_update("users", {"refer_count": r["refer_count"], "bonus_checks": r["bonus_checks"]}, telegram_id=referrer_id)
    ref = _users.get(referred_id)
    if ref:
        ref["referred_by"] = referrer_id
        _sb_update("users", {"referred_by": referrer_id}, telegram_id=referred_id)
    if _sb:
        try: _sb.table("refer_log").insert({"referrer_id": referrer_id, "referred_id": referred_id, "bonus_given": bonus}).execute()
        except: pass
    return True

# ── Stats ─────────────────────────────────────────────────────────────────────

def increment_stats(registered: int, not_registered: int):
    today = date.today().isoformat()
    total = registered + not_registered
    s = _stats.get(today) or {"date": today, "total_checks": 0, "registered_count": 0, "not_registered_count": 0}
    s["total_checks"]         += total
    s["registered_count"]     += registered
    s["not_registered_count"] += not_registered
    _stats[today] = s
    _sb_set("bot_stats", s, conflict="date")

def get_total_stats() -> dict:
    all_s = list(_stats.values())
    return {
        "total_checks":         sum(s.get("total_checks", 0) for s in all_s),
        "registered_count":     sum(s.get("registered_count", 0) for s in all_s),
        "not_registered_count": sum(s.get("not_registered_count", 0) for s in all_s),
    }

def get_stats_history(days: int = 7) -> list:
    return sorted(_stats.values(), key=lambda s: s["date"], reverse=True)[:days]

# ── WA Accounts ───────────────────────────────────────────────────────────────

def get_all_accounts() -> list[dict]:
    return sorted(_accounts.values(), key=lambda a: (a.get("account_type", ""), a.get("id", 0)))

def get_account(account_id: str) -> Optional[dict]:
    return _accounts.get(account_id)

def add_account(account_id: str, label: str, atype: str = "checker"):
    if account_id in _accounts: return
    a = {"account_id": account_id, "label": label or account_id, "account_type": atype,
         "is_enabled": 1, "is_connected": 0, "total_checks": 0, "ban_count": 0}
    _accounts[account_id] = a
    if _sb:
        try: _sb.table("wa_accounts").upsert(a, on_conflict="account_id").execute()
        except: pass

def remove_account(account_id: str):
    _accounts.pop(account_id, None)
    if _sb:
        try: _sb.table("wa_accounts").delete().eq("account_id", account_id).execute()
        except: pass

def set_account_connected(account_id: str, connected: bool, phone: str = None):
    a = _accounts.get(account_id)
    if a:
        a["is_connected"] = 1 if connected else 0
        if phone: a["phone_number"] = phone
        if connected: a["last_connected"] = datetime.now().isoformat()
    upd = {"is_connected": 1 if connected else 0}
    if phone: upd["phone_number"] = phone
    if connected: upd["last_connected"] = datetime.now().isoformat()
    _sb_update("wa_accounts", upd, account_id=account_id)

def set_account_type(account_id: str, atype: str):
    if account_id in _accounts: _accounts[account_id]["account_type"] = atype
    _sb_update("wa_accounts", {"account_type": atype}, account_id=account_id)

def ban_account(account_id: str):
    a = _accounts.get(account_id)
    if a:
        a["ban_count"] = (a.get("ban_count", 0) or 0) + 1
        a["is_enabled"] = 0
        a["is_connected"] = 0
    _sb_update("wa_accounts", {"ban_count": (a or {}).get("ban_count", 1), "is_enabled": 0, "is_connected": 0}, account_id=account_id)

def inc_account_checks(account_id: str, count: int = 1):
    a = _accounts.get(account_id)
    if a: a["total_checks"] = (a.get("total_checks", 0) or 0) + count
    _sb_update("wa_accounts", {"total_checks": (a or {}).get("total_checks", count)}, account_id=account_id)

def get_backups() -> list[dict]:
    return [a for a in _accounts.values() if a.get("is_enabled") and a.get("account_type") == "backup"]

# ── FSub ──────────────────────────────────────────────────────────────────────

def get_all_fsub() -> list[dict]:
    return list(_fsub)

def add_fsub(channel_id: str, title: str, link: str):
    existing = next((c for c in _fsub if c["channel_id"] == channel_id), None)
    obj = {"channel_id": channel_id, "title": title or channel_id, "link": link or ""}
    if existing:
        existing.update(obj)
    else:
        _fsub.append(obj)
    _sb_set("fsub_channels", obj, conflict="channel_id")

def remove_fsub(channel_id: str):
    global _fsub
    _fsub = [c for c in _fsub if c["channel_id"] != channel_id]
    if _sb:
        try: _sb.table("fsub_channels").delete().eq("channel_id", channel_id).execute()
        except: pass

def update_fsub(channel_id: str, title: str, link: str):
    for c in _fsub:
        if c["channel_id"] == channel_id:
            c["title"] = title
            c["link"]  = link
    _sb_update("fsub_channels", {"title": title, "link": link}, channel_id=channel_id)

# ── Redeem Codes ──────────────────────────────────────────────────────────────

async def create_redeem(code: str, checks: int, max_uses: int, creator_id: int) -> dict:
    if not _sb: raise RuntimeError("Supabase not configured")
    r = _sb.table("redeem_codes").insert({
        "code": code.upper(), "checks": checks,
        "max_uses": max_uses, "used_count": 0,
        "is_active": True, "created_by": creator_id
    }).execute()
    return r.data[0] if r.data else {}

async def get_redeem(code: str) -> Optional[dict]:
    if not _sb: return None
    r = _sb.table("redeem_codes").select("*").eq("code", code.upper()).eq("is_active", True).execute()
    return r.data[0] if r.data else None

async def get_all_redeems() -> list:
    if not _sb: return []
    r = _sb.table("redeem_codes").select("*").order("created_at", desc=True).execute()
    return r.data or []

async def use_redeem(code: str, uid: int) -> dict:
    if not _sb: return {"success": False, "reason": "no_db"}
    # Check already used
    r = _sb.table("redeem_log").select("id").eq("code", code.upper()).eq("user_id", uid).execute()
    if r.data: return {"success": False, "reason": "already_redeemed"}
    # Get code
    code_row = await get_redeem(code)
    if not code_row: return {"success": False, "reason": "invalid_code"}
    if code_row["used_count"] >= code_row["max_uses"]: return {"success": False, "reason": "expired"}
    # Apply bonus
    add_bonus(uid, code_row["checks"])
    # Log
    _sb.table("redeem_log").insert({"code": code.upper(), "user_id": uid, "checks": code_row["checks"]}).execute()
    # Update count
    new_count = code_row["used_count"] + 1
    _sb.table("redeem_codes").update({
        "used_count": new_count,
        "is_active": new_count < code_row["max_uses"]
    }).eq("code", code.upper()).execute()
    return {"success": True, "checks": code_row["checks"]}

async def delete_redeem(code: str):
    if _sb:
        try: _sb.table("redeem_codes").delete().eq("code", code.upper()).execute()
        except: pass

# ── API Keys ──────────────────────────────────────────────────────────────────

def _save_api_keys():
    data = json.dumps(list(_api_keys.values()))
    _settings["api_keys_store"] = data
    _sb_set("bot_settings", {"key": "api_keys_store", "value": data}, conflict="key")

def get_api_key(key: str) -> Optional[dict]:
    return _api_keys.get(key)

def get_all_api_keys() -> list[dict]:
    return list(_api_keys.values())

def save_api_key(obj: dict):
    _api_keys[obj["key"]] = obj
    _save_api_keys()

def delete_api_key(key: str):
    _api_keys.pop(key, None)
    _save_api_keys()

# ── Number Pool ───────────────────────────────────────────────────────────────

async def add_number(uid: int, phone: str):
    if _sb:
        try: _sb.table("number_pool").insert({"user_id": uid, "phone_number": phone}).execute()
        except: pass

async def get_next_number(uid: int) -> Optional[dict]:
    if not _sb: return None
    r = _sb.table("number_pool").select("*").eq("user_id", uid).eq("is_used", 0).order("id").limit(1).execute()
    if not r.data: return None
    row = r.data[0]
    _sb.table("number_pool").update({"is_used": 1}).eq("id", row["id"]).execute()
    return row

async def get_number_count(uid: int) -> int:
    if not _sb: return 0
    r = _sb.table("number_pool").select("id", count="exact").eq("user_id", uid).eq("is_used", 0).execute()
<<<<<<< HEAD
    return r.count or 0
=======
    return r.count or 0
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
