import json
import os
import threading
from typing import Set, List
import config
from services.sheets_service import sheets_service

SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "subscribers.json")

def load_subscribers() -> Set[int]:
    """Tải danh sách chat ID đã đăng ký nhận tin báo cáo và nhắc nhở."""
    subs = set()
    loaded_from_local = False

    # 1. Đọc từ local cache nếu tồn tại
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    for x in data:
                        try:
                            subs.add(int(x))
                        except (ValueError, TypeError):
                            pass
                    if subs:
                        loaded_from_local = True
        except Exception as e:
            print(f"Lỗi đọc file subscribers.json: {e}")

    # 2. Nếu local cache rỗng (ví dụ sau khi server restart/redeploy), đọc từ Google Sheet
    if not loaded_from_local:
        try:
            sheet_subs = sheets_service.get_subscribers_from_sheet()
            if sheet_subs:
                for cid in sheet_subs:
                    subs.add(cid)
                # Ghi lại vào local cache để các lần sau đọc nhanh
                try:
                    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                        json.dump(list(subs), f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Lỗi ghi cache subscribers.json từ Sheet: {e}")
        except Exception as e:
            print(f"Lỗi tải subscribers từ Google Sheet: {e}")

    # 3. Kết hợp với ALLOWED_USER_IDS nếu được cấu hình
    if config.ALLOWED_USER_IDS:
        for uid in config.ALLOWED_USER_IDS:
            subs.add(uid)

    return subs

def _save_to_sheet_async(chat_id: int, user_name: str = ""):
    """Lưu subscriber lên Google Sheet trong thread riêng để không làm nghẽn phản hồi bot."""
    try:
        sheets_service.save_subscriber_to_sheet(chat_id, user_name)
    except Exception as e:
        print(f"Lỗi lưu subscriber lên Google Sheet (async): {e}")

def save_subscriber(chat_id: int, user_name: str = ""):
    """Lưu chat ID của người dùng khi họ tương tác với bot (vào cả local cache và Google Sheet)."""
    if not chat_id:
        return
    try:
        subs = load_subscribers()
        is_new = chat_id not in subs
        if is_new:
            subs.add(chat_id)
            with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(subs), f, ensure_ascii=False, indent=2)

        # Lưu/cập nhật vào Google Sheet (chạy ngầm để tối ưu độ trễ phản hồi)
        threading.Thread(target=_save_to_sheet_async, args=(chat_id, user_name), daemon=True).start()
    except Exception as e:
        print(f"Lỗi lưu subscriber: {e}")

def get_all_subscribers() -> List[int]:
    """Lấy danh sách tất cả chat ID cần gửi báo cáo và nhắc nhở."""
    return list(load_subscribers())
