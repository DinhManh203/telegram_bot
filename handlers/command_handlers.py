from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
import config
from services.sheets_service import sheets_service
from services.chart_service import chart_service
from services.ai_service import ai_service
from services.subscriber_service import save_subscriber, get_all_subscribers

# Bàn phím thao tác nhanh tối giản
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Báo cáo tháng"), KeyboardButton("Biểu đồ chi tiêu")],
        [KeyboardButton("Sổ Ghi Nợ"), KeyboardButton("Giao dịch gần đây")],
        [KeyboardButton("Hôm nay"), KeyboardButton("Mở Google Sheet")]
    ],
    resize_keyboard=True
)

async def check_user_access(update: Update) -> bool:
    """Kiểm tra quyền truy cập của user."""
    user = update.effective_user
    if not user or not config.is_user_allowed(user.id):
        if update.message:
            await update.message.reply_text("Bạn không có quyền sử dụng bot này.")
        return False
    return True

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start."""
    if not await check_user_access(update):
        return

    save_subscriber(update.effective_chat.id)
    user = update.effective_user
    welcome_text = (
        f"Xin chào **{user.first_name}**!\n"
        f"Bot Quản Lý Tài Chính & Sổ Nợ đã sẵn sàng.\n\n"
        f"────────────────────────\n"
        f"**CÁCH SỬ DỤNG NHANH:**\n"
        f"• **Ghi chi tiêu:** Nhắn `Ăn sáng 45k` hoặc gõ `/chitieu Ăn sáng 45k`\n"
        f"• **Ghi nợ:** Nhắn `Cho Nam vay 500k` hoặc gõ `/no Cho Nam vay 500k`\n"
        f"• **Xem báo cáo:** Gõ `/baocao` hoặc chọn menu bên dưới"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /baocao [tháng] [năm]: Báo cáo chi tiêu và các khoản nợ trong tháng."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    now = datetime.now(config.TIMEZONE)
    target_month = now.month
    target_year = now.year

    if context.args and len(context.args) >= 1:
        try:
            target_month = int(context.args[0])
            if len(context.args) >= 2:
                target_year = int(context.args[1])
        except ValueError:
            pass

    summary = sheets_service.get_monthly_summary(user_id=user_id, month=target_month, year=target_year)
    transactions = sheets_service.get_transactions_by_month(user_id=user_id, month=target_month, year=target_year)
    total_expense = summary["total_expense"]
    total_income = summary["total_income"]
    balance = summary["balance"]

    debt_data = sheets_service.get_debts_by_month(user_id=user_id, month=target_month, year=target_year)
    total_debt = debt_data["total_debt"]
    debt_items = debt_data["items"]

    lines = [
        f"**BÁO CÁO TÀI CHÍNH - THÁNG {target_month:02d}/{target_year}**",
        "────────────────────────",
        "**1. SỔ CHI TIÊU**",
        f"• Tổng chi tiêu: `{total_expense:,.0f} VNĐ`",
        f"• Tổng thu nhập: `{total_income:,.0f} VNĐ`",
        f"• Số dư: `{balance:,.0f} VNĐ`\n",
        "**Chi tiết giao dịch:**"
    ]

    if transactions:
        for tx in transactions:
            date_short = tx["time"][:10] if len(tx["time"]) >= 10 else ""
            note_str = f" - {tx['note']}" if tx.get("note") else ""
            type_str = f"[{tx['type']}] " if "thu" in tx["type"].lower() else ""
            lines.append(f"- {date_short}: {type_str}`{tx['amount']:,.0f} VNĐ`{note_str}")
    else:
        lines.append("- (Chưa có giao dịch chi tiêu trong tháng)")

    lines.append("\n────────────────────────")
    lines.append("**2. SỔ GHI NỢ**")
    lines.append(f"• Tổng nợ chưa trả: `{total_debt:,.0f} VNĐ`\n")
    lines.append("**Chi tiết khoản nợ:**")

    if debt_items:
        for d in debt_items:
            note_str = f" - {d['note']}" if d.get("note") else ""
            debt_time = f" | Ngày nợ: {d['debt_date']}" if d.get("debt_date") else ""
            lines.append(f"- **{d['person']}**: `{d['amount']:,.0f} VNĐ` [{d['status']}]{debt_time}{note_str}")
    else:
        lines.append("- (Không có khoản nợ nào trong tháng)")

    sheet_url = sheets_service.get_sheet_url()
    if sheet_url:
        lines.append("────────────────────────")
        lines.append(f"[Mở bảng tính Google Sheet]({sheet_url})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /thongke hoặc nút Biểu đồ chi tiêu."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    now = datetime.now(config.TIMEZONE)
    target_month = now.month
    target_year = now.year

    if context.args and len(context.args) >= 1:
        try:
            target_month = int(context.args[0])
            if len(context.args) >= 2:
                target_year = int(context.args[1])
        except ValueError:
            pass

    summary = sheets_service.get_monthly_summary(user_id=user_id, month=target_month, year=target_year)
    total_expense = summary["total_expense"]

    await update.message.reply_text(
        f"**THỐNG KÊ CHI TIÊU - THÁNG {target_month:02d}/{target_year}**\n"
        f"────────────────────────\n"
        f"• Tổng chi tiêu: `{total_expense:,.0f} VNĐ`\n"
        f"• Tổng thu nhập: `{summary['total_income']:,.0f} VNĐ`\n"
        f"• Số dư: `{summary['balance']:,.0f} VNĐ`\n"
        f"• Số giao dịch: `{summary['transaction_count']}`",
        parse_mode="Markdown"
    )

async def expense_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /chitieu: Ghi trực tiếp vào tab Sổ Chi Tiêu hoặc xem tổng quan."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Người dùng"

    if context.args:
        raw_text = " ".join(context.args)
        await update.message.reply_chat_action("typing")

        ai_res = ai_service.analyze_text(raw_text)
        transactions = ai_res.get("transactions", [])

        if not transactions:
            amount = 0
            if ai_res.get("debt_items"):
                amount = ai_res["debt_items"][0].get("amount", 0)
            transactions = [{
                "amount": amount,
                "type": "Chi tiêu",
                "note": raw_text,
                "date": datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            }]

        if transactions and transactions[0].get("amount", 0) > 0:
            try:
                saved = sheets_service.add_transactions(transactions, user_id=user_id, user_name=user_name)
                lines = [
                    "**ĐÃ GHI VÀO SỔ CHI TIÊU**",
                    "────────────────────────"
                ]
                for tx in saved:
                    lines.append(f"• Loại: {tx['type']}")
                    lines.append(f"• Số tiền: `{tx['amount']:,.0f} {tx['unit']}`")
                    if tx.get("note"):
                        lines.append(f"• Mô tả: {tx['note']}")

                sheet_url = sheets_service.get_sheet_url()
                if sheet_url:
                    lines.append(f"\n[Mở Google Sheet]({sheet_url})")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"Lỗi ghi vào Sổ Chi Tiêu: {str(e)}")
        else:
            await update.message.reply_text(
                "Không nhận diện được số tiền hợp lệ.\n"
                "Ví dụ: `/chitieu Ăn phở bò 45k` hoặc `/chitieu Đổ xăng 50k`"
            )
    else:
        now = datetime.now(config.TIMEZONE)
        summary = sheets_service.get_monthly_summary(user_id=user_id, month=now.month, year=now.year)
        lines = [
            f"**TỔNG HỢP CHI TIÊU - THÁNG {now.month:02d}/{now.year}**",
            "────────────────────────",
            f"• Tổng chi tiêu: `{summary['total_expense']:,.0f} VNĐ`",
            f"• Tổng thu nhập: `{summary['total_income']:,.0f} VNĐ`",
            f"• Số dư: `{summary['balance']:,.0f} VNĐ`\n",
            "Ghi chi tiêu nhanh: `/chitieu <nội dung>` (vd: `/chitieu Ăn phở 45k`)"
        ]
        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def debt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /no: Ghi trực tiếp vào tab Sổ Ghi Nợ hoặc xem tổng hợp nợ."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Người dùng"

    if context.args:
        raw_text = " ".join(context.args)
        await update.message.reply_chat_action("typing")

        ai_res = ai_service.analyze_text(raw_text)
        debt_items = ai_res.get("debt_items", [])

        if not debt_items and ai_res.get("transactions"):
            for tx in ai_res["transactions"]:
                debt_items.append({
                    "person": tx.get("note") or "Không rõ",
                    "debt_type": "Cho vay",
                    "amount": tx.get("amount", 0),
                    "debt_date": "",
                    "status": "Nợ",
                    "note": tx.get("note", ""),
                    "date": datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
                })

        if debt_items and debt_items[0].get("amount", 0) > 0:
            try:
                saved = sheets_service.add_debt_transactions(debt_items, user_id=user_id, user_name=user_name)
                lines = [
                    "**ĐÃ GHI VÀO SỔ GHI NỢ**",
                    "────────────────────────"
                ]
                for d in saved:
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
        else:
            await update.message.reply_text(
                "Không nhận diện được thông tin ghi nợ hợp lệ.\n"
                "Ví dụ: `/no Cho Nam vay 500k` hoặc `/no Trịnh Dũng nợ 122k`"
            )
    else:
        debt_summary = sheets_service.get_debt_summary(user_id=user_id)
        total_amount = debt_summary.get("total_amount", 0)
        items = debt_summary.get("items", [])

        lines = [
            "**TỔNG HỢP SỔ GHI NỢ**",
            "────────────────────────",
            f"• Tổng nợ chưa trả: `{total_amount:,.0f} VNĐ`\n",
            "**Danh sách khoản nợ:**"
        ]

        if items:
            for item in items:
                date_str = f" | Ngày: {item['debt_date']}" if item.get("debt_date") else ""
                note_str = f" - {item['note']}" if item.get("note") else ""
                lines.append(f"- **{item['person']}**: `{item['amount']:,.0f} VNĐ` [{item.get('status', 'Nợ')}]{date_str}{note_str}")
        else:
            lines.append("- (Chưa có khoản nợ nào trong sổ)")

        lines.append("────────────────────────")
        lines.append("Ghi nợ nhanh: `/no <nội dung>` (vd: `/no Cho Nam vay 500k`)")

        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /xem: Hiển thị các giao dịch gần đây."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    recent = sheets_service.get_recent_transactions(user_id=user_id, limit=8)

    if not recent:
        await update.message.reply_text("Chưa có giao dịch nào được lưu trong bảng tính.")
        return

    lines = [
        "**GIAO DỊCH GẦN ĐÂY**",
        "────────────────────────"
    ]
    for tx in recent:
        note_str = f" - {tx['note']}" if tx.get("note") else ""
        lines.append(f"- {tx['time'][:16]} | {tx['type']}: `{tx['amount']:,.0f} VNĐ`{note_str}")

    lines.append("────────────────────────")
    lines.append("Xóa giao dịch nhầm: `/xoa <Mã GD>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem chi tiêu trong ngày hôm nay."""
    if not await check_user_access(update):
        return

    user_id = update.effective_user.id
    now = datetime.now(config.TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")
    month_txs = sheets_service.get_transactions_by_month(user_id=user_id, month=now.month, year=now.year)

    today_txs = [tx for tx in month_txs if tx.get("time", "").startswith(today_str)]

    if not today_txs:
        await update.message.reply_text(f"Hôm nay ({now.strftime('%d/%m/%Y')}): Bạn chưa ghi nhận khoản thu chi nào.")
        return

    total_exp = sum(tx["amount"] for tx in today_txs if "thu" not in tx["type"].lower())
    total_inc = sum(tx["amount"] for tx in today_txs if "thu" in tx["type"].lower())

    lines = [
        f"**TỔNG KẾT HÔM NAY ({now.strftime('%d/%m/%Y')})**",
        "────────────────────────"
    ]
    for tx in today_txs:
        note_str = f" - {tx['note']}" if tx.get("note") else ""
        lines.append(f"- [{tx['type']}] `{tx['amount']:,.0f} VNĐ`{note_str}")

    lines.append("────────────────────────")
    lines.append(f"• Tổng chi: `{total_exp:,.0f} VNĐ`")
    if total_inc > 0:
        lines.append(f"• Tổng thu: `{total_inc:,.0f} VNĐ`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /xoa <Mã GD>."""
    if not await check_user_access(update):
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Vui lòng cung cấp Mã GD cần xóa.\n"
            "Ví dụ: `/xoa TX260820ABCD` hoặc `/xoa NO260820ABCD`"
        )
        return

    tx_id = context.args[0].strip()
    user_id = update.effective_user.id
    success = sheets_service.delete_transaction_by_id(tx_id, user_id=user_id)

    if success:
        await update.message.reply_text(f"Đã xóa thành công giao dịch `{tx_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Không tìm thấy giao dịch `{tx_id}` trên bảng tính.", parse_mode="Markdown")

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /link lấy URL Google Sheet."""
    if not await check_user_access(update):
        return

    save_subscriber(update.effective_chat.id)
    url = sheets_service.get_sheet_url()
    if url:
        await update.message.reply_text(
            f"**Google Sheet của bạn:**\n"
            f"[Bấm vào đây để mở bảng tính]({url})\n\n"
            f"_(Gồm 2 tab: **Sổ Chi Tiêu** và **Sổ Ghi Nợ**)_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Chưa kết nối được Google Sheet hoặc chưa tìm thấy URL.")

async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    """Job gửi báo cáo chi tiêu tự động lúc 21:00 hàng ngày."""
    chat_ids = get_all_subscribers()
    if not chat_ids:
        return

    now = datetime.now(config.TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")

    month_txs = sheets_service.get_transactions_by_month(month=now.month, year=now.year)
    today_txs = [tx for tx in month_txs if tx.get("time", "").startswith(today_str)]

    lines = [
        f"**BÁO CÁO CHI TIÊU HÔM NAY ({now.strftime('%d/%m/%Y')} - 21:00)**",
        "────────────────────────"
    ]

    if not today_txs:
        lines.append("Hôm nay bạn chưa có giao dịch chi tiêu nào.")
    else:
        total_exp = sum(tx["amount"] for tx in today_txs if "thu" not in tx["type"].lower())
        total_inc = sum(tx["amount"] for tx in today_txs if "thu" in tx["type"].lower())

        lines.append(f"• Tổng chi hôm nay: `{total_exp:,.0f} VNĐ`")
        if total_inc > 0:
            lines.append(f"• Tổng thu nhập: `{total_inc:,.0f} VNĐ`")
        lines.append("\nChi tiết các khoản chi:")
        for tx in today_txs:
            note_str = f" - {tx['note']}" if tx.get("note") else ""
            lines.append(f"- [{tx['type']}] `{tx['amount']:,.0f} VNĐ`{note_str}")

    lines.append("────────────────────────")
    sheet_url = sheets_service.get_sheet_url()
    if sheet_url:
        lines.append(f"[Mở Google Sheet]({sheet_url})")

    message_text = "\n".join(lines)

    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=message_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Lỗi gửi báo cáo 21h tới chat_id {cid}: {e}")

