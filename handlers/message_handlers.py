from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
import config
from services.ai_service import ai_service
from services.sheets_service import sheets_service
from services.chart_service import chart_service
from services.subscriber_service import save_subscriber
from handlers.command_handlers import (
    check_user_access,
    report_command,
    chart_command,
    recent_command,
    today_command,
    link_command,
    debt_command
)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn văn bản từ người dùng."""
    if not await check_user_access(update):
        return

    save_subscriber(update.effective_chat.id)
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    user_name = user.full_name or user.username or "Unknown"

    # Kiểm tra các nút bấm trên bàn phím nhanh
    if text == "📊 Báo cáo tháng":
        await report_command(update, context)
        return
    elif text == "📈 Biểu đồ chi tiêu":
        await chart_command(update, context)
        return
    elif text == "📒 Sổ Ghi Nợ":
        await debt_command(update, context)
        return
    elif text == "📝 Giao dịch gần đây":
        await recent_command(update, context)
        return
    elif text == "📅 Hôm nay":
        await today_command(update, context)
        return
    elif text == "🔗 Mở Google Sheet":
        await link_command(update, context)
        return

    # Gửi trạng thái đang gõ phím
    await update.message.reply_chat_action("typing")

    # Phân tích văn bản bằng Gemini AI
    ai_result = ai_service.analyze_text(text)
    intent = ai_result.get("intent", "CHAT")

    # 1. GHI NHẬN VAY MƯỢN / GHI NỢ (LƯU VÀO TAB RIÊNG "SỔ GHI NỢ")
    if intent == "ADD_DEBT":
        debt_items = ai_result.get("debt_items", [])
        if not debt_items:
            await update.message.reply_text("Không nhận diện được thông tin khoản nợ/vay. Bạn hãy thử nhắn lại rõ hơn nhé (vd: `Cho Nam vay 500k`).")
            return

        try:
            saved_debts = sheets_service.add_debt_transactions(debt_items, user_id=user_id, user_name=user_name)
            lines = [
                "**ĐÃ GHI VÀO SỔ GHI NỢ**",
                "────────────────────────"
            ]
            for d in saved_debts:
                lines.append(f"• Người liên quan: **{d['person']}**")
                lines.append(f"• Số tiền: `{d['amount']:,.0f} {d['unit']}`")
                if d.get("debt_date"):
                    lines.append(f"• Ngày nợ: {d['debt_date']}")
                if d.get("note"):
                    lines.append(f"• Ghi chú: {d['note']}")
                lines.append(f"• Trạng thái: {d.get('status', 'Nợ')}")

            sheet_url = sheets_service.get_sheet_url()
            if sheet_url:
                lines.append(f"\n[Mở Google Sheet]({sheet_url})")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Lỗi ghi vào Sổ Ghi Nợ: {str(e)}")

    # 2. HỎI ĐÁP VỀ SỔ NỢ
    elif intent == "QUERY_DEBT":
        await debt_command(update, context)

    # 3. GHI NHẬN CHI TIÊU / THU NHẬP (TAB SỔ CHI TIÊU)
    elif intent == "ADD_TRANSACTION":
        transactions = ai_result.get("transactions", [])
        if not transactions:
            await update.message.reply_text("Không nhận diện được khoản tiền nào trong tin nhắn. Bạn hãy thử nhắn lại (vd: `Ăn trưa 40k`).")
            return

        try:
            saved_txs = sheets_service.add_transactions(transactions, user_id=user_id, user_name=user_name)
            
            lines = [
                "**ĐÃ GHI VÀO SỔ CHI TIÊU**",
                "────────────────────────"
            ]
            total_exp = 0
            total_inc = 0

            for tx in saved_txs:
                is_income = "thu" in tx["type"].lower()
                amt = tx["amount"]
                
                if is_income:
                    total_inc += amt
                else:
                    total_exp += amt

                note_str = f" - {tx['note']}" if tx.get("note") else ""
                lines.append(f"• [{tx['type']}] `{amt:,.0f} VNĐ`{note_str}")

            lines.append("────────────────────────")
            if total_exp > 0 and total_inc > 0:
                lines.append(f"• Tổng chi: `{total_exp:,.0f} VNĐ` | Tổng thu: `{total_inc:,.0f} VNĐ`")
            elif total_exp > 0:
                lines.append(f"• Tổng chi: `{total_exp:,.0f} VNĐ`")
            elif total_inc > 0:
                lines.append(f"• Tổng thu: `{total_inc:,.0f} VNĐ`")

            sheet_url = sheets_service.get_sheet_url()
            if sheet_url:
                lines.append(f"[Mở Google Sheet]({sheet_url})")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"Không thể lưu vào Google Sheet: {str(e)}")

    # 4. HỎI ĐÁP THỐNG KÊ CHI TIÊU
    elif intent == "QUERY_STATS":
        query_info = ai_result.get("query_info", {})
        scope = query_info.get("scope", "this_month")
        month = query_info.get("month")
        year = query_info.get("year")

        now = datetime.now(config.TIMEZONE)
        if not month:
            month = now.month
        if not year:
            year = now.year

        if scope == "today":
            await today_command(update, context)
            return

        summary = sheets_service.get_monthly_summary(user_id=user_id, month=month, year=year)
        total_exp = summary["total_expense"]
        total_inc = summary["total_income"]
        balance = summary["balance"]

        resp = (
            f"**TỔNG KẾT CHI TIÊU - THÁNG {month:02d}/{year}**\n"
            f"────────────────────────\n"
            f"• Tổng chi: `{total_exp:,.0f} VNĐ`\n"
            f"• Tổng thu: `{total_inc:,.0f} VNĐ`\n"
            f"• Số dư: `{balance:,.0f} VNĐ`\n"
            f"────────────────────────\n"
            f"Gõ `/baocao` để xem chi tiết các giao dịch và khoản nợ."
        )
        await update.message.reply_text(resp, parse_mode="Markdown")

    else:
        # Chat thông thường
        reply_msg = ai_result.get("reply_message") or "Tôi có thể giúp bạn ghi chi tiêu và quản lý sổ nợ tự động vào Google Sheet. Hãy thử nhắn: `Ăn trưa 40k` hoặc `Cho Nam vay 500k` nhé!"
        await update.message.reply_text(reply_msg)

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý hình ảnh (hóa đơn, biên lai chuyển khoản)."""
    if not await check_user_access(update):
        return

    save_subscriber(update.effective_chat.id)
    user = update.effective_user
    user_id = user.id
    user_name = user.full_name or user.username or "Unknown"

    await update.message.reply_chat_action("typing")
    status_msg = await update.message.reply_text("Đang quét thông tin hóa đơn bằng AI...")

    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        caption = update.message.caption

        ai_result = ai_service.analyze_image(bytes(photo_bytes), caption=caption)
        transactions = ai_result.get("transactions", [])

        if not transactions:
            await status_msg.edit_text("Không thể nhận diện số tiền từ hình ảnh này. Bạn hãy thử chụp lại góc rõ hơn hoặc nhập bằng chữ nhé!")
            return

        saved_txs = sheets_service.add_transactions(transactions, user_id=user_id, user_name=user_name)

        lines = [
            "**ĐÃ QUÉT HÓA ĐƠN VÀO SỔ CHI TIÊU**",
            "────────────────────────"
        ]
        total_exp = 0
        for tx in saved_txs:
            amt = tx["amount"]
            total_exp += amt
            note_str = f" - {tx['note']}" if tx.get("note") else ""
            lines.append(f"• [{tx['type']}] `{amt:,.0f} VNĐ`{note_str}")

        lines.append("────────────────────────")
        lines.append(f"• Tổng cộng: `{total_exp:,.0f} VNĐ`")
        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")

        await status_msg.edit_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        await status_msg.edit_text(f"Lỗi xử lý hóa đơn: {str(e)}")
