import json
import os
from typing import Set, List
import config

SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "subscribers.json")

def load_subscribers() -> Set[int]:
    """Tải danh sách chat ID đã đăng ký nhận tin báo cáo."""
    subs = set()
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for x in data:
                        try:
                            subs.add(int(x))
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            print(f"Lỗi đọc file subscribers.json: {e}")

    # Kết hợp với ALLOWED_USER_IDS nếu được cấu hình
    if config.ALLOWED_USER_IDS:
        for uid in config.ALLOWED_USER_IDS:
            subs.add(uid)

    return subs

def save_subscriber(chat_id: int):
    """Lưu chat ID của người dùng khi họ tương tác với bot."""
    if not chat_id:
        return
    try:
        subs = load_subscribers()
        if chat_id not in subs:
            subs.add(chat_id)
            with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(subs), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu subscriber: {e}")

def get_all_subscribers() -> List[int]:
    """Lấy danh sách tất cả chat ID cần gửi báo cáo hàng ngày."""
    return list(load_subscribers())
