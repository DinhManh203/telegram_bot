import os
import sys
from datetime import timezone, timedelta
from dotenv import load_dotenv

# Thiết lập UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Tải biến môi trường từ .env nếu có
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json").strip()
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
SPREADSHEET_ID_OR_NAME = os.getenv("SPREADSHEET_ID_OR_NAME", "Chi Tieu Ca Nhan").strip()
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip()

try:
    from zoneinfo import ZoneInfo
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception:
    # Mặc định UTC+7 cho Việt Nam
    TIMEZONE = timezone(timedelta(hours=7))

# Lọc danh sách user ID được phép (nếu có)
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
