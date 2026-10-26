import logging
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)
from telegram.error import InvalidToken
import config
from handlers.command_handlers import (
    start_command,
    help_command,
    report_command,
    chart_command,
    recent_command,
    today_command,
    delete_command,
    link_command,
    debt_command,
    expense_command,
    pay_debt_command,
    unpay_debt_command,
    daily_report_job,
    reminder_manual_command
)
from handlers.message_handlers import (
    handle_text_message,
    handle_photo_message
)
from datetime import time

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import json
import collections
from services.ai_service import ai_service

RECENT_LOGS = collections.deque(maxlen=250)

class MemoryLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            RECENT_LOGS.append(msg)
        except Exception:
            pass

_mem_handler = MemoryLogHandler()
_mem_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(_mem_handler)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def _json_res(self, data_dict: dict, status_code: int = 200):
        body = json.dumps(data_dict, ensure_ascii=False)
        self.send_response(status_code)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        clean_path = self.path.split("?")[0]
        if clean_path in ("/", "/models", "/models.html", "/index.html"):
            html_path = os.path.join(os.path.dirname(__file__), "models.html")
            if os.path.exists(html_path):
                try:
                    with open(html_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(content.encode("utf-8"))
                    return
                except Exception as e:
                    logger.warning(f"Lỗi đọc models.html: {e}")

        elif clean_path in ("/api/status", "/api/models"):
            try:
                data = ai_service.get_status_dict()
                self._json_res(data)
                return
            except Exception as e:
                logger.warning(f"Lỗi API status: {e}")
                self._json_res({"error": str(e)}, 500)
                return

        elif clean_path == "/api/logs":
            try:
                log_text = "\n".join(RECENT_LOGS) if RECENT_LOGS else "Hệ thống đang hoạt động bình thường. Chưa có log phát sinh."
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(log_text.encode("utf-8"))
                return
            except Exception as e:
                logger.warning(f"Lỗi API logs: {e}")

        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Telegram Bot is running healthy!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        clean_path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        payload = {}
        if body_bytes:
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                pass

        if clean_path == "/api/model/switch":
            target = payload.get("model")
            if target and target in ai_service.models:
                ai_service.current_model = target
                logger.info(f"[Web Console] Đã chuyển model chính sang: {target}")
                self._json_res({"success": True, "active_model": target})
            else:
                self._json_res({"success": False, "error": "Model không tồn tại trong danh sách"})
            return

        elif clean_path == "/api/model/reset":
            ai_service.model_cooldowns.clear()
            ai_service.model_reasons.clear()
            logger.info("[Web Console] Đã reset toàn bộ thời gian cooldown của các models.")
            self._json_res({"success": True})
            return

        elif clean_path == "/api/model/test":
            target = payload.get("model")
            if target:
                res = ai_service.test_model(target)
                self._json_res({"success": True, "results": [res]})
            else:
                results = []
                for m in ai_service.models:
                    results.append(ai_service.test_model(m))
                self._json_res({"success": True, "results": results})
            return

        elif clean_path == "/api/prompt":
            content = payload.get("content")
            if content:
                ai_service.system_prompt = content
                logger.info("[Web Console] Đã cập nhật System Instruction của Bot.")
                self._json_res({"success": True})
            else:
                self._json_res({"success": False, "error": "Nội dung rỗng"})
            return

        elif clean_path == "/api/settings":
            self._json_res({"success": True})
            return

        elif clean_path == "/api/bot/toggle":
            is_online = ai_service.toggle_online()
            status_str = "ONLINE (ĐANG HOẠT ĐỘNG)" if is_online else "STANDBY (TẮT)"
            logger.info(f"[Web Console] Trạng thái Bot đã chuyển sang: {status_str}")
            self._json_res({"success": True, "online": is_online})
            return

        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Telegram Bot is running healthy!")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_health_check_server():
    """Chạy web server mini trong thread riêng để phục vụ Health Check và trang models.html."""
    port = int(os.getenv("PORT", "8080"))
    server = None
    candidate_ports = [port] if os.getenv("PORT") else [8080, 8000, 8888, 5050]
    for p in candidate_ports:
        try:
            server = HTTPServer(("0.0.0.0", p), HealthCheckHandler)
            port = p
            break
        except Exception:
            continue
    if server:
        logger.info(f"Dashboard Model AI đang chạy tại: http://localhost:{port}/models")
        try:
            server.serve_forever()
        except Exception:
            pass
    else:
        logger.error("Không thể khởi động web server.")

def main():
    """Khởi chạy Telegram Bot."""
    threading.Thread(target=start_health_check_server, daemon=True).start()

    if not config.TELEGRAM_BOT_TOKEN:
        print("=" * 60)
        print("LỖI: TELEGRAM_BOT_TOKEN chưa được thiết lập!")
        print("Vui lòng mở file .env và điền TELEGRAM_BOT_TOKEN từ @BotFather.")
        print("=" * 60)
        sys.exit(1)

    print("Đang khởi động Telegram AI Expense Bot...")
    
    from telegram.request import HTTPXRequest
    request_client = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).request(request_client).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("huongdan", help_command))
    app.add_handler(CommandHandler("chitieu", expense_command))
    app.add_handler(CommandHandler("expense", expense_command))
    app.add_handler(CommandHandler("ct", expense_command))
    app.add_handler(CommandHandler("no", debt_command))
    app.add_handler(CommandHandler("debt", debt_command))
    app.add_handler(CommandHandler("sono", debt_command))
    app.add_handler(CommandHandler("trano", pay_debt_command))
    app.add_handler(CommandHandler("tra", pay_debt_command))
    app.add_handler(CommandHandler("paydebt", pay_debt_command))
    app.add_handler(CommandHandler("thanhtoan", pay_debt_command))
    app.add_handler(CommandHandler("chuatra", unpay_debt_command))
    app.add_handler(CommandHandler("unpaid", unpay_debt_command))
    app.add_handler(CommandHandler("chuatrano", unpay_debt_command))
    app.add_handler(CommandHandler("baocao", report_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("thongke", chart_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("xem", recent_command))
    app.add_handler(CommandHandler("history", recent_command))
    app.add_handler(CommandHandler("homnay", today_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("xoa", delete_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("nhacnho", reminder_manual_command))
    app.add_handler(CommandHandler("testnhacnho", reminder_manual_command))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    if app.job_queue:
        daily_time = time(hour=21, minute=0, second=0, tzinfo=config.TIMEZONE)
        app.job_queue.run_daily(daily_report_job, time=daily_time, name="daily_21h_expense_report")
        print("Đã thiết lập lịch gửi báo cáo tự động lúc 21:00 hàng ngày.")

    print("Bot đã sẵn sàng nhận tin nhắn trên Telegram.")
    try:
        app.run_polling(bootstrap_retries=10, timeout=30, drop_pending_updates=True)
    except InvalidToken:
        print("\n" + "=" * 65)
        print("❌ LỖI TELEGRAM TOKEN (401 Unauthorized):")
        print("👉 Token bot hiện tại trong file .env không hợp lệ hoặc đã bị hủy/thu hồi.")
        print("👉 Cách khắc phục:")
        print("   1. Mở Telegram, tìm và nhắn tin cho @BotFather")
        print("   2. Gõ lệnh /mybots -> chọn con bot của bạn")
        print("   3. Chọn 'API Token' (hoặc 'Revoke current token' nếu muốn cấp mới)")
        print("   4. Copy chuỗi token mới và dán vào dòng:")
        print("      TELEGRAM_BOT_TOKEN=... trong file .env")
        print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
