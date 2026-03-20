import os
from dotenv import load_dotenv

load_dotenv()

# ── Required ──────────────────────────────────────────────────────────────────
BOT_TOKEN:   str       = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID:    int       = int(os.getenv("OWNER_ID", "0"))

# ── Optional ──────────────────────────────────────────────────────────────────
PORT:        int       = int(os.getenv("PORT", "3000"))
LOG_GROUP:   int       = int(os.getenv("LOG_GROUP_ID", "0"))
ADMIN_IDS:   list[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ── Supabase ──────────────────────────────────────────────────────────────────
SB_URL:      str = os.getenv("SUPABASE_URL", "")
SB_KEY:      str = os.getenv("SB_SERVICE_KEY", "")

# ── FSub / Images ─────────────────────────────────────────────────────────────
FSUB_CHANNELS: list[str] = [x.strip() for x in os.getenv("FSUB_CHANNELS", "").split(",") if x.strip()]
FSUB_IMAGE:    str = os.getenv("FSUB_IMAGE", "")
MENU_IMAGE:    str = os.getenv("MENU_IMAGE", "")

# ── API ───────────────────────────────────────────────────────────────────────
API_PUBLIC_URL: str = os.getenv("API_PUBLIC_URL", "")
