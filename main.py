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

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Telegram Bot is running healthy!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Ẩn log kiểm tra cổng tự động của Render để tránh rác log
        pass

def start_health_check_server():
    """Chạy web server mini trong thread riêng để Render Web Service kiểm tra cổng (Health Check)."""
    port = int(os.getenv("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check web server đang lắng nghe trên cổng {port}...")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Lỗi khởi động health check web server: {e}")

def main():
    """Khởi chạy Telegram Bot."""
    # Khởi chạy health check web server ngầm cho Render Web Service
    threading.Thread(target=start_health_check_server, daemon=True).start()

    if not config.TELEGRAM_BOT_TOKEN:
        print("=" * 60)
        print("LỖI: TELEGRAM_BOT_TOKEN chưa được thiết lập!")
        print("Vui lòng mở file .env và điền TELEGRAM_BOT_TOKEN từ @BotFather.")
        print("=" * 60)
        sys.exit(1)

    print("Đang khởi động Telegram AI Expense Bot...")
    
    # Cấu hình HTTPXRequest với timeout lớn hơn và cơ chế retry khi chạy trên server
    from telegram.request import HTTPXRequest
    request_client = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    # Khởi tạo Application
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).request(request_client).build()

    # Đăng ký các lệnh Command
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

    # Đăng ký xử lý tin nhắn hình ảnh (hóa đơn)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Đăng ký xử lý tin nhắn văn bản (chat tự nhiên, nút bấm)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Cấu hình Cron Job tự động gửi báo cáo chi tiêu ngày lúc 21:00 hàng ngày (theo múi giờ Việt Nam)
    if app.job_queue:
        daily_time = time(hour=21, minute=0, second=0, tzinfo=config.TIMEZONE)
        app.job_queue.run_daily(daily_report_job, time=daily_time, name="daily_21h_expense_report")
        print("Đã thiết lập lịch gửi báo cáo tự động lúc 21:00 hàng ngày.")

    print("Bot đã sẵn sàng nhận tin nhắn trên Telegram.")
    # Bắt đầu chạy bot với cơ chế tự động thử lại (bootstrap_retries=10)
    app.run_polling(bootstrap_retries=10, timeout=30, drop_pending_updates=True)

if __name__ == "__main__":
    main()
