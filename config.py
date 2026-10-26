import os
import sys
from datetime import timezone, timedelta
from dotenv import load_dotenv

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json").strip()
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
SPREADSHEET_ID_OR_NAME = os.getenv("SPREADSHEET_ID_OR_NAME", "Chi Tieu Ca Nhan").strip()
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip()

DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]
GEMINI_MODELS_RAW = os.getenv("GEMINI_MODELS", "").strip()
if GEMINI_MODELS_RAW:
    GEMINI_MODELS = [m.strip() for m in GEMINI_MODELS_RAW.split(",") if m.strip()]
else:
    GEMINI_MODELS = DEFAULT_GEMINI_MODELS

try:
    from zoneinfo import ZoneInfo
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception:
    TIMEZONE = timezone(timedelta(hours=7))

ALLOWED_USER_IDS_RAW = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = []
if ALLOWED_USER_IDS_RAW:
    for uid in ALLOWED_USER_IDS_RAW.split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.append(int(uid))

def is_user_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS
