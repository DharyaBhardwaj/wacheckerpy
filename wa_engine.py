"""
WhatsApp Multi-Account Engine
Uses neonize (Python Baileys equivalent)
"""
from __future__ import annotations
import asyncio
import io
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
import qrcode

import config
import database as db

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

try:
    from neonize.client import NewClient
    from neonize.events import ConnectedEv, QRChangedEv, DisconnectedEv, LoggedOutEv
    NEONIZE_OK = True
except ImportError:
    NEONIZE_OK = False
    logger.warning("neonize not installed — WA disabled")

MAX_RETRY = 50

@dataclass
class WAAccount:
    account_id:   str
    account_type: str   = "checker"
    status:       str   = "disconnected"
    client:       object = None
    phone:        str   = ""
    qr_bytes:     Optional[bytes] = None
    retry_count:  int   = 0
    was_connected: bool = False
    _retry_task:  object = None

accounts: dict[str, WAAccount] = {}

# ── Callbacks ─────────────────────────────────────────────────────────────────
_cb_connect:    Optional[Callable] = None
_cb_disconnect: Optional[Callable] = None
_cb_ban:        Optional[Callable] = None
_cb_qr:         Optional[Callable] = None

def set_callbacks(on_connect=None, on_disconnect=None, on_ban=None, on_qr=None):
    global _cb_connect, _cb_disconnect, _cb_ban, _cb_qr
    _cb_connect    = on_connect
    _cb_disconnect = on_disconnect
    _cb_ban        = on_ban
    _cb_qr         = on_qr

# ── Helpers ───────────────────────────────────────────────────────────────────

def session_dir(account_id: str) -> Path:
    d = DATA_DIR / f"wa_{account_id}"
    d.mkdir(exist_ok=True)
    return d

def get_checkers() -> list[WAAccount]:
    return [a for a in accounts.values() if a.status == "connected" and a.account_type == "checker"]

def has_checker() -> bool:
    return bool(get_checkers())

def _make_qr(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ── Connect ───────────────────────────────────────────────────────────────────

async def connect_account(account_id: str, account_type: str = "checker"):
    if not NEONIZE_OK:
        logger.error("neonize not available")
        return

    existing = accounts.get(account_id)
    if existing and existing.status in ("connected", "connecting"):
        return

    db.add_account(account_id, account_id, account_type)
    db_acct = db.get_account(account_id)
    atype   = db_acct.get("account_type", account_type) if db_acct else account_type

    if not existing:
        acct = WAAccount(account_id=account_id, account_type=atype)
        accounts[account_id] = acct
    else:
        acct = existing
        acct.status    = "connecting"
        acct.qr_bytes  = None
        acct.account_type = atype

    sdir   = str(session_dir(account_id))
    client = NewClient(sdir)
    acct.client = client

    @client.event(ConnectedEv)
    async def on_connected(_, __):
        first = not acct.was_connected
        acct.status       = "connected"
        acct.was_connected = True
        acct.qr_bytes     = None
        acct.retry_count  = 0
        phone = getattr(client, "phone", "") or ""
        acct.phone        = phone
        db.set_account_connected(account_id, True, phone)
        if first and _cb_connect:
            await _cb_connect(account_id, atype, phone)

    @client.event(QRChangedEv)
    async def on_qr(_, ev):
        acct.status   = "waiting_qr"
        acct.qr_bytes = _make_qr(ev.QR)
        if _cb_qr:
            await _cb_qr(account_id, acct.qr_bytes)

    @client.event(DisconnectedEv)
    async def on_disconnect(_, __):
        acct.status   = "disconnected"
        acct.client   = None
        acct.qr_bytes = None
        db.set_account_connected(account_id, False)

        if acct.was_connected and _cb_disconnect:
            await _cb_disconnect(account_id, atype)
        acct.was_connected = False

        if atype == "checker" and not get_checkers():
            asyncio.create_task(promote_backup())

        if acct.retry_count < MAX_RETRY:
            acct.retry_count += 1
            backoff = min(300, 30 * acct.retry_count)
            await asyncio.sleep(backoff)
            asyncio.create_task(connect_account(account_id, atype))

    @client.event(LoggedOutEv)
    async def on_banned(_, __):
        acct.status = "banned"
        acct.client = None
        db.ban_account(account_id)
        wipe_session(account_id)
        if _cb_ban:
            await _cb_ban(account_id, atype)
        asyncio.create_task(promote_backup())

    asyncio.create_task(_run(client))

async def _run(client):
    try:
        await client.connect()
    except Exception as e:
        logger.error(f"WA client error: {e}")

# ── Pairing Code ──────────────────────────────────────────────────────────────

async def get_pairing_code(account_id: str, phone: str, account_type: str = "checker") -> str:
    if not NEONIZE_OK:
        raise RuntimeError("neonize not installed")
    wipe_session(account_id)
    db.add_account(account_id, account_id, account_type)

    acct = WAAccount(account_id=account_id, account_type=account_type, status="connecting")
    accounts[account_id] = acct

    sdir   = str(session_dir(account_id))
    client = NewClient(sdir)
    acct.client = client

    @client.event(ConnectedEv)
    async def on_connected(_, __):
        acct.status = "connected"
        acct.was_connected = True
        phone_n = getattr(client, "phone", "") or ""
        acct.phone = phone_n
        db.set_account_connected(account_id, True, phone_n)
        if _cb_connect:
            await _cb_connect(account_id, account_type, phone_n)

    @client.event(LoggedOutEv)
    async def on_banned(_, __):
        acct.status = "banned"
        db.ban_account(account_id)

    await asyncio.sleep(1)
    asyncio.create_task(_run(client))
    await asyncio.sleep(3)

    clean = phone.replace(" ", "").replace("+", "").replace("-", "")
    return await client.pair_phone(clean)

# ── Check ─────────────────────────────────────────────────────────────────────

async def check_number(account_id: str, phone: str) -> dict:
    acct = accounts.get(account_id)
    if not acct or acct.status != "connected" or not acct.client:
        return {"phone_number": phone, "is_registered": None, "error": "not_connected"}
    try:
        clean = phone.replace(" ", "").replace("+", "").replace("-", "")
        result = await acct.client.is_on_whatsapp(f"{clean}@s.whatsapp.net")
        db.inc_account_checks(account_id)
        return {"phone_number": phone, "is_registered": bool(result and result[0].exists if isinstance(result, list) else result)}
    except Exception as e:
        return {"phone_number": phone, "is_registered": None, "error": str(e)}

async def bulk_check(numbers: list[str], on_progress: Callable = None) -> list[dict]:
    results = [None] * len(numbers)
    pending = list(enumerate(numbers))
    done    = 0

    while pending:
        checkers = get_checkers()
        if not checkers:
            await asyncio.sleep(10)
            if not get_checkers():
                for idx, num in pending:
                    results[idx] = {"phone_number": num, "is_registered": None, "error": "no_accounts"}
                break
            continue

        chunks: dict[str, list] = {c.account_id: [] for c in checkers}
        for i, (idx, num) in enumerate(pending):
            cid = checkers[i % len(checkers)].account_id
            chunks[cid].append((idx, num))

        failed = []

        async def _chunk(cid, items):
            nonlocal done
            for idx, num in items:
                a = accounts.get(cid)
                if not a or a.status != "connected":
                    failed.append((idx, num))
                    continue
                results[idx] = await check_number(cid, num)
                done += 1
                if on_progress:
                    await on_progress(done, len(numbers))
                await asyncio.sleep(0.1)

        await asyncio.gather(*[_chunk(cid, items) for cid, items in chunks.items()])
        pending = failed
        if pending:
            await asyncio.sleep(2)

    return results

# ── Promote Backup ────────────────────────────────────────────────────────────

async def promote_backup() -> Optional[str]:
    backups = db.get_backups()
    for b in backups:
        a = accounts.get(b["account_id"])
        if a and a.status == "connected":
            db.set_account_type(b["account_id"], "checker")
            a.account_type = "checker"
            return b["account_id"]
    for b in backups:
        db.set_account_type(b["account_id"], "checker")
        asyncio.create_task(connect_account(b["account_id"], "checker"))
        return b["account_id"]
    return None

# ── Disconnect / Wipe ─────────────────────────────────────────────────────────

async def disconnect_account(account_id: str):
    a = accounts.get(account_id)
    if a:
        if a.client:
            try: await a.client.disconnect()
            except: pass
        a.status = "disconnected"
        a.client = None
    wipe_session(account_id)
    db.set_account_connected(account_id, False)

def wipe_session(account_id: str):
    d = DATA_DIR / f"wa_{account_id}"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

# ── Boot ──────────────────────────────────────────────────────────────────────

async def connect_all_saved():
    saved = db.get_all_accounts()
    logger.info(f"[Boot] Restoring {len(saved)} WA accounts...")
    for a in saved:
        if not a.get("is_enabled"):
            accounts[a["account_id"]] = WAAccount(
                account_id=a["account_id"],
                account_type=a.get("account_type", "checker"),
                status="banned",
                phone=a.get("phone_number", ""),
            )
            continue
        sdir       = DATA_DIR / f"wa_{a['account_id']}"
        has_session = sdir.exists() and any(sdir.iterdir())
        if has_session:
            logger.info(f"[Boot] Connecting: {a['account_id']}")
            await connect_account(a["account_id"], a.get("account_type", "checker"))
        else:
            accounts[a["account_id"]] = WAAccount(
                account_id=a["account_id"],
                account_type=a.get("account_type", "checker"),
                status="disconnected",
                phone=a.get("phone_number", ""),
            )