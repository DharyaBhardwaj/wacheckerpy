"""
REST API Server — FastAPI
Endpoints: /WSCK (single), /WSCK/bulk (batch)
"""
from __future__ import annotations
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

<<<<<<< HEAD
import database as db
import wa_engine as wa
=======
import core.database as db
import core.wa_engine as wa
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e

app = FastAPI(title="WA Checker API", docs_url=None, redoc_url=None)

# ── Rate limiter ──────────────────────────────────────────────────────────────
_rate_windows: dict[str, dict] = {}

def _check_rps(key: str, max_rps: int) -> bool:
    now = time.time()
    w   = _rate_windows.get(key) or {"count": 0, "start": now}
    if now - w["start"] >= 1.0:
        w = {"count": 1, "start": now}
    else:
        w["count"] += 1
    _rate_windows[key] = w
    return w["count"] <= max_rps

_active_bulk = 0
MAX_CONCURRENT_BULK = 2

# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_api_key(request: Request):
    key = request.headers.get("X-Api-Key") or request.query_params.get("key")
    if not key:
        raise HTTPException(401, detail="API key required")

    # Master key
    master = db.get_setting("api_key")
    if master and key == master:
        return {"plan": "master", "daily_limit": 999999, "key": key}

    # Client key
    data = db.get_api_key(key)
    if not data:
        raise HTTPException(401, detail="Invalid API key")

    # Expiry
    if data.get("expires_at"):
        if datetime.fromisoformat(data["expires_at"]) < datetime.now():
            raise HTTPException(403, detail="API key expired")

    # Daily limit
    today = datetime.now().date().isoformat()
    if data.get("reset_date") != today:
        data["used_today"] = 0
        data["reset_date"] = today

    limit = data.get("daily_limit", 1000) or 0
    if limit > 0 and (data.get("used_today", 0) or 0) >= limit:
        raise HTTPException(429, detail={
            "error": "Daily limit reached",
            "limit": limit,
            "used":  data.get("used_today", 0),
        })

    # RPS check
    rps_map = {
        "basic":    int(db.get_setting("api_rps_basic", "3")),
        "pro":      int(db.get_setting("api_rps_pro", "5")),
        "business": int(db.get_setting("api_rps_business", "10")),
        "master":   999,
    }
    max_rps = rps_map.get(data.get("plan", "basic"), 3)
    if not _check_rps(key, max_rps):
        raise HTTPException(429, detail={
            "error": "Too many requests",
            "limit": f"{max_rps}/sec",
            "retry_after": "1 second",
        })

    # Increment usage
    data["used_today"] = (data.get("used_today", 0) or 0) + 1
    db.save_api_key(data)
    return data

def _branding():
    name = db.get_setting("brand_name") or "WA Checker API"
    chan = db.get_setting("brand_channel") or "@wachecke_r_bot"
    return f"{name} | Telegram: {chan}"

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "running", "name": "WA Checker API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/WSCK")
async def check_single(phone: str, key_data: dict = Depends(get_api_key)):
    clean = phone.replace(" ","").replace("+","").replace("-","")
    if not clean.isdigit() or len(clean) < 7 or len(clean) > 15:
        raise HTTPException(400, detail="Invalid phone number")

    checkers = wa.get_checkers()
    if not checkers:
        raise HTTPException(503, detail="No WhatsApp accounts connected")

    import random
    checker = random.choice(checkers)
    result  = await wa.check_number(checker.account_id, clean)

    return {
        "success":       True,
        "phone":         clean,
        "is_registered": result.get("is_registered"),
        "checked_at":    datetime.now().isoformat(),
        "powered_by":    _branding(),
    }

class BulkRequest(BaseModel):
    phones: list[str]

@app.post("/WSCK/bulk")
async def check_bulk(body: BulkRequest, key_data: dict = Depends(get_api_key)):
    global _active_bulk

    phones = [p.replace(" ","").replace("+","").replace("-","")
              for p in body.phones
              if p.replace(" ","").replace("+","").replace("-","").isdigit()]
    phones = [p for p in phones if 7 <= len(p) <= 15]

    if not phones:
        raise HTTPException(400, detail="Send valid phone numbers in 'phones' array")

    # Bulk limit per plan
    plan = key_data.get("plan", "basic")
    bulk_limits = {
        "basic":    int(db.get_setting("api_bulk_basic", "100")),
        "pro":      int(db.get_setting("api_bulk_pro", "500")),
        "business": int(db.get_setting("api_bulk_business", "0")),
        "master":   0,
    }
    bl = bulk_limits.get(plan, 100)
    if bl > 0 and len(phones) > bl:
        raise HTTPException(400, detail=f"Max {bl} numbers per request for {plan} plan")

    if not wa.get_checkers():
        raise HTTPException(503, detail="No WhatsApp accounts connected")

    if _active_bulk >= MAX_CONCURRENT_BULK:
        raise HTTPException(429, detail={"error": "Server busy", "retry_after": "5 seconds"})

    _active_bulk += 1
    try:
        results = await wa.bulk_check(phones)
    finally:
        _active_bulk = max(0, _active_bulk - 1)

    return {
        "success":       True,
        "total":         len(results),
        "registered":    [r["phone_number"] for r in results if r and r.get("is_registered") is True],
        "not_registered":[r["phone_number"] for r in results if r and r.get("is_registered") is False],
        "unknown":       [r["phone_number"] for r in results if r and r.get("is_registered") is None],
        "checked_at":    datetime.now().isoformat(),
        "powered_by":    _branding(),
<<<<<<< HEAD
    }
=======
    }
>>>>>>> 937f2086d73be9b44218523290134a49f8c47d3e
