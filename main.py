import logging
import sys
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)
import config
from handlers.command_handlers import (
    start_command,
    report_command,
    chart_command,
    recent_command,
    today_command,
    delete_command,
    link_command,
    debt_command,
    expense_command
)
from handlers.message_handlers import (
    handle_text_message,
    handle_photo_message
)

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Khởi chạy Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("=" * 60)
        print("LOI: TELEGRAM_BOT_TOKEN chua duoc thiet lap!")
        print("Vui long mo file .env va dien TELEGRAM_BOT_TOKEN tu @BotFather.")
        print("=" * 60)
        sys.exit(1)

    print("Dang khoi dong Telegram AI Expense Bot...")
    
    # Khởi tạo Application
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Đăng ký các lệnh Command
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("chitieu", expense_command))
    app.add_handler(CommandHandler("expense", expense_command))
    app.add_handler(CommandHandler("ct", expense_command))
    app.add_handler(CommandHandler("no", debt_command))
    app.add_handler(CommandHandler("debt", debt_command))
    app.add_handler(CommandHandler("sono", debt_command))
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

    # Đăng ký xử lý tin nhắn hình ảnh (hóa đơn)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Đăng ký xử lý tin nhắn văn bản (chat tự nhiên, nút bấm)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("Bot da san sang nhan tin nhan tren Telegram.")
    # Bắt đầu chạy bot
    app.run_polling()

if __name__ == "__main__":
    main()
