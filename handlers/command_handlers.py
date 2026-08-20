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

    await update.message.reply_chat_action("typing")
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

    await update.message.reply_chat_action("typing")
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
            lines.append(f"• Mã GD: `{d['id']}` | **{d['person']}**: `{d['amount']:,.0f} VNĐ` [{d['status']}]{debt_time}{note_str}")
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

    await update.message.reply_chat_action("upload_photo")
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

    chart_buf = chart_service.generate_expense_pie_chart(
        summary.get("expense_by_category", {}),
        target_month,
        target_year
    )

    if chart_buf:
        await update.message.reply_photo(
            photo=chart_buf,
            caption=(
                f"📊 **BIỂU ĐỒ CHI TIÊU - THÁNG {target_month:02d}/{target_year}**\n"
                f"────────────────────────\n"
                f"• Tổng chi tiêu: `{total_expense:,.0f} VNĐ`\n"
                f"• Tổng thu nhập: `{summary['total_income']:,.0f} VNĐ`\n"
                f"• Số dư: `{summary['balance']:,.0f} VNĐ`"
            ),
            parse_mode="Markdown"
        )
    else:
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
        raw_lower = raw_text.lower()
        if any(kw in raw_lower for kw in ["chưa trả", "chua tra", "chưa nhận", "chua nhan"]):
            await unpay_debt_command(update, context)
            return
        if any(kw in raw_lower for kw in ["trả", "tra", "thanh toán", "thanh toan", "thu nợ", "hoàn thành"]):
            await pay_debt_command(update, context)
            return

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
                    lines.append(f"• Mã GD: `{d['id']}`")
                    lines.append(f"• Người liên quan: **{d['person']}**")
                    lines.append(f"• Số tiền: `{d['amount']:,.0f} {d['unit']}`")
                    if d.get("debt_date"):
                        lines.append(f"• Ngày nợ: {d['debt_date']}")
                    if d.get("note"):
                        lines.append(f"• Ghi chú: {d['note']}")
                    lines.append(f"• Trạng thái: **{d.get('status', 'Nợ')}**")
                    lines.append("────────────────────────")

                sheet_url = sheets_service.get_sheet_url()
                if sheet_url:
                    lines.append(f"[Mở Google Sheet]({sheet_url})")
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
                lines.append(f"• Mã GD: `{item['id']}` | **{item['person']}**: `{item['amount']:,.0f} VNĐ` [{item.get('status', 'Nợ')}]{date_str}{note_str}")
        else:
            lines.append("- (Chưa có khoản nợ nào trong sổ)")

        lines.append("────────────────────────")
        lines.append("• Ghi nợ: `/no <nội dung>` (vd: `/no Cho Nam vay 500k`)")
        lines.append("• Báo đã trả: `/trano <Mã GD/Tên>`")
        lines.append("• Báo chưa trả: `/chuatra <Mã GD/Tên>`")

        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def pay_debt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /trano, /tra, /paydebt: Cập nhật hoàn thành trả nợ theo Mã GD hoặc tên người."""
    if not await check_user_access(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp Mã GD hoặc Tên người đã trả nợ.\n"
            "Ví dụ:\n"
            "• `/trano NO2608205754` (Đánh dấu đã trả theo Mã GD)\n"
            "• `/trano Tuấn Anh` (Đánh dấu đã trả hết nợ của Tuấn Anh)\n"
            "• `/trano Tuấn Anh 200k` (Trả 1 phần 200k)",
            parse_mode="Markdown"
        )
        return

    raw_text = " ".join(context.args).strip()
    await update.message.reply_chat_action("typing")

    import re
    # 1. Trích xuất Mã GD nếu có
    debt_id = ""
    match = re.search(r"\b(NO[0-9A-Za-z]{6,12})\b", raw_text, re.IGNORECASE)
    if match:
        debt_id = match.group(1).upper()
        remaining_text = raw_text.replace(match.group(1), "").strip()
    else:
        remaining_text = raw_text

    # 2. Phân tích AI để bóc tách người và số tiền
    person = ""
    amount = None
    if remaining_text:
        ai_res = ai_service.analyze_text(f"{remaining_text} trả nợ")
        person = ai_res.get("person") or ""
        amount = ai_res.get("amount")

    # Regex trích xuất số tiền nếu có
    if amount is None:
        m_amt = re.search(r"(\d+[\d\.,]*)\s*(k|cành|nghìn|ngàn|lốp|lít|củ|triệu|tr|m)?\b", raw_text, re.IGNORECASE)
        if m_amt:
            num_part = m_amt.group(1).replace(".", "").replace(",", "")
            unit_part = (m_amt.group(2) or "").lower()
            try:
                num = float(num_part)
                if unit_part in ("k", "cành", "nghìn", "ngàn"):
                    num *= 1000
                elif unit_part in ("lốp", "lít"):
                    num *= 100000
                elif unit_part in ("củ", "triệu", "tr", "m"):
                    num *= 1000000
                if num > 0:
                    amount = int(num)
            except Exception:
                pass

    if not person and not debt_id:
        m_p = re.search(r"([A-Za-zÀ-ỹ\s]+?)(?:\s+(?:đã|trả|vẫn|còn|nợ|\d).*|$)", remaining_text)
        if m_p:
            person = m_p.group(1).strip()
        else:
            person = remaining_text

    is_full = (amount is None or amount <= 0)

    updated_items = sheets_service.update_debt_status(
        debt_id=debt_id,
        person=person,
        status="Đã trả",
        amount=amount,
        is_full=is_full
    )

    if updated_items:
        lines = [
            "✅ **ĐÃ CẬP NHẬT TRẠNG THÁI: ĐÃ TRẢ**",
            "────────────────────────"
        ]
        for item in updated_items:
            lines.append(f"• Mã GD: `{item['id']}`")
            lines.append(f"• Người liên quan: **{item['person']}**")
            if item["status"] == "Đã trả":
                lines.append(f"• Đã thanh toán: `{item['paid_amount']:,.0f} VNĐ` | Số dư nợ còn lại: `0 VNĐ`")
                lines.append("• Trạng thái mới: **Đã trả**")
            else:
                lines.append(f"• Đã trả: `{item['paid_amount']:,.0f} VNĐ` | Số dư nợ còn lại: `{item['new_amount']:,.0f} VNĐ`")
                lines.append("• Trạng thái: **Nợ**")
            if item.get("note"):
                lines.append(f"• Ghi chú: {item['note']}")
            lines.append("────────────────────────")

        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        target_str = f"mã `{debt_id}`" if debt_id else f"người **{person or raw_text}**"
        await update.message.reply_text(
            f"Không tìm thấy khoản nợ chưa trả nào của {target_str} trong Sổ Ghi Nợ.",
            parse_mode="Markdown"
        )

async def unpay_debt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /chuatra, /unpaid: Chuyển trạng thái khoản nợ về 'Nợ' (chưa trả)."""
    if not await check_user_access(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp Mã GD hoặc Tên người chưa trả nợ.\n"
            "Ví dụ:\n"
            "• `/chuatra NO2608205754` (Đổi lại trạng thái sang Nợ theo Mã GD)\n"
            "• `/chuatra Tuấn Anh` (Đổi trạng thái của Tuấn Anh sang Nợ)\n"
            "• `/chuatra Tuấn Anh 500k` (Khôi phục nợ 500k)",
            parse_mode="Markdown"
        )
        return

    raw_text = " ".join(context.args).strip()
    await update.message.reply_chat_action("typing")

    import re
    debt_id = ""
    match = re.search(r"\b(NO[0-9A-Za-z]{6,12})\b", raw_text, re.IGNORECASE)
    if match:
        debt_id = match.group(1).upper()
        remaining_text = raw_text.replace(match.group(1), "").strip()
    else:
        remaining_text = raw_text

    person = ""
    amount = None
    if remaining_text:
        ai_res = ai_service.analyze_text(f"{remaining_text} nợ")
        person = ai_res.get("person") or ""
        amount = ai_res.get("amount")

    # Regex trích xuất số tiền nếu có
    if amount is None:
        m_amt = re.search(r"(\d+[\d\.,]*)\s*(k|cành|nghìn|ngàn|lốp|lít|củ|triệu|tr|m)?\b", raw_text, re.IGNORECASE)
        if m_amt:
            num_part = m_amt.group(1).replace(".", "").replace(",", "")
            unit_part = (m_amt.group(2) or "").lower()
            try:
                num = float(num_part)
                if unit_part in ("k", "cành", "nghìn", "ngàn"):
                    num *= 1000
                elif unit_part in ("lốp", "lít"):
                    num *= 100000
                elif unit_part in ("củ", "triệu", "tr", "m"):
                    num *= 1000000
                if num > 0:
                    amount = int(num)
            except Exception:
                pass

    if not person and not debt_id:
        m_p = re.search(r"([A-Za-zÀ-ỹ\s]+?)(?:\s+(?:vẫn|còn|đang|chưa|nợ|\d).*|$)", remaining_text)
        if m_p:
            person = m_p.group(1).strip()
        else:
            person = remaining_text

    updated_items = sheets_service.update_debt_status(
        debt_id=debt_id,
        person=person,
        status="Nợ",
        amount=amount,
        is_full=False
    )

    if updated_items:
        lines = [
            "🔄 **ĐÃ CHUYỂN TRẠNG THÁI: NỢ (CHƯA TRẢ)**",
            "────────────────────────"
        ]
        for item in updated_items:
            lines.append(f"• Mã GD: `{item['id']}`")
            lines.append(f"• Người liên quan: **{item['person']}**")
            lines.append(f"• Số tiền nợ: `{item['new_amount']:,.0f} VNĐ`")
            lines.append("• Trạng thái mới: **Nợ**")
            if item.get("note"):
                lines.append(f"• Ghi chú: {item['note']}")
            lines.append("────────────────────────")

        sheet_url = sheets_service.get_sheet_url()
        if sheet_url:
            lines.append(f"[Mở Google Sheet]({sheet_url})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        target_str = f"mã `{debt_id}`" if debt_id else f"người **{person or raw_text}**"
        await update.message.reply_text(
            f"Không tìm thấy khoản nợ nào phù hợp với {target_str} trong Sổ Ghi Nợ.",
            parse_mode="Markdown"
        )

async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /xem: Hiển thị các giao dịch gần đây."""
    if not await check_user_access(update):
        return

    await update.message.reply_chat_action("typing")
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

    await update.message.reply_chat_action("typing")
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
    """Xử lý lệnh /xoa <Mã GD 1> [Mã GD 2] ..."""
    if not await check_user_access(update):
        return

    await update.message.reply_chat_action("typing")
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Vui lòng cung cấp Mã GD cần xóa.\n"
            "Ví dụ:\n"
            "• `/xoa TX260820ABCD`\n"
            "• `/xoa NO260820F66D NO260820ABB2` (Xóa nhiều mã)",
            parse_mode="Markdown"
        )
        return

    import re
    user_id = update.effective_user.id
    raw_args = " ".join(context.args)
    matched_ids = re.findall(r"\b((?:NO|TX)[0-9A-Za-z]{6,14})\b", raw_args, re.IGNORECASE)
    if not matched_ids:
        # Nếu người dùng chỉ gõ mã không có tiền tố NO/TX
        matched_ids = [arg.strip().upper() for arg in context.args if arg.strip()]

    deleted_success = []
    deleted_failed = []

    for tid in matched_ids:
        clean_tid = tid.strip().upper()
        ok = sheets_service.delete_transaction_by_id(clean_tid, user_id=user_id)
        if ok:
            deleted_success.append(clean_tid)
        else:
            deleted_failed.append(clean_tid)

    lines = []
    if deleted_success:
        lines.append("🗑️ **ĐÃ XÓA THÀNH CÔNG:**")
        lines.append("────────────────────────")
        for tid in deleted_success:
            lines.append(f"• Mã GD: `{tid}`")
    if deleted_failed:
        if lines:
            lines.append("────────────────────────")
        lines.append("⚠️ **KHÔNG TÌM THẤY ĐỂ XÓA:**")
        for tid in deleted_failed:
            lines.append(f"• Mã GD: `{tid}`")

    sheet_url = sheets_service.get_sheet_url()
    if sheet_url:
        lines.append(f"\n[Mở Google Sheet]({sheet_url})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /link lấy URL Google Sheet."""
    if not await check_user_access(update):
        return

    await update.message.reply_chat_action("typing")
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

