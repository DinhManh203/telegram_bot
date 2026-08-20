import re
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
    text_lower = text.lower()

    # 0. Kiểm tra yêu cầu XÓA giao dịch / xóa khoản nợ theo Mã GD
    delete_keywords = ["xóa", "xoa", "delete", "hủy", "huy", "remove"]
    is_delete_request = any(kw in text_lower for kw in delete_keywords) or intent == "DELETE"
    matched_ids = re.findall(r"\b((?:NO|TX)[0-9A-Za-z]{6,14})\b", text, re.IGNORECASE)
    ai_delete_ids = ai_result.get("delete_ids", [])
    if isinstance(ai_delete_ids, list):
        for did in ai_delete_ids:
            if did and did.upper() not in [m.upper() for m in matched_ids]:
                matched_ids.append(did)

    if is_delete_request and matched_ids:
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
        return

    # 1. Kiểm tra yêu cầu CHƯA TRẢ NỢ / ĐÁNH DẤU NỢ LẠI (Chuyển trạng thái sang "Nợ")
    has_unpay_action = bool(re.search(r"\b(chưa trả|chua tra|chưa nhận|chua nhan|chưa thanh toán|chua thanh toan|vẫn chưa trả|van chua tra|chưa trả nợ|chua tra no)\b", text_lower))
    
    # 2. Kiểm tra yêu cầu ĐÃ TRẢ NỢ (Chuyển trạng thái sang "Đã trả")
    has_pay_action = bool(re.search(r"\b(đã trả|da tra|trả nợ|tra no|trả tiền|thanh toán|thanh toan|hoàn thành trả|thu nợ|thu no|đòi nợ|doi no)\b", text_lower))
    if not has_pay_action and re.search(r"\btrả\b", text_lower) and not has_unpay_action:
        has_pay_action = True

    expense_triggers = ["ăn phở", "ăn sáng", "ăn trưa", "ăn tối", "uống cafe", "đổ xăng", "mua áo", "mua sắm", "tiền điện", "tiền nước", "tiền nhà"]
    is_daily_expense = any(exp in text_lower for exp in expense_triggers)

    if has_unpay_action and not is_daily_expense:
        intent = "UNPAY_DEBT"
    elif has_pay_action and not is_daily_expense:
        if intent in ("ADD_DEBT", "CHAT"):
            intent = "PAY_DEBT"
            debt_items = ai_result.get("debt_items", [])
            if debt_items:
                if not ai_result.get("person"):
                    ai_result["person"] = debt_items[0].get("person")
                if not ai_result.get("amount"):
                    ai_result["amount"] = debt_items[0].get("amount")

    # Kiểm tra nếu là câu hỏi/xác nhận tình trạng nợ hiện tại (vd: "vẫn đang nợ", "còn nợ bao nhiêu")
    if any(q in text_lower for q in ["vẫn đang nợ", "vẫn nợ", "còn nợ", "đang nợ bao nhiêu", "nợ bao nhiêu"]):
        intent = "QUERY_DEBT"

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

    # 2. XỬ LÝ CHUYỂN TRẠNG THÁI SỔ NỢ (ĐÃ TRẢ HOẶC CHƯA TRẢ NỢ)
    elif intent in ("PAY_DEBT", "UNPAY_DEBT"):
        target_status = "Nợ" if intent == "UNPAY_DEBT" else "Đã trả"
        person = ai_result.get("person") or ""
        debt_id = ai_result.get("debt_id") or ""
        amount = ai_result.get("amount")
        is_full = ai_result.get("is_full_payment", True)

        # Regex trích xuất Mã GD nếu có trong câu (ví dụ NO2608205754, NO260820ABB2)
        if not debt_id:
            match = re.search(r"\b(NO[0-9A-Za-z]{6,12})\b", text, re.IGNORECASE)
            if match:
                debt_id = match.group(1).upper()

        # Nếu chưa có person, lấy từ debt_items nếu có
        if not person and not debt_id:
            debt_items = ai_result.get("debt_items", [])
            if debt_items and debt_items[0].get("person"):
                person = debt_items[0].get("person")
                if not amount:
                    amount = debt_items[0].get("amount")

        # Nếu vẫn chưa có person, bóc tách từ text: "[Tên người] chưa trả / đã trả..."
        if not person and not debt_id:
            m_person = re.search(r"([A-Za-zÀ-ỹ\s]+?)\s+(?:đã\s+|vẫn\s+|vừa\s+)?(?:trả|chưa trả|thanh toán|thu nợ)", text, re.IGNORECASE)
            if m_person:
                person = m_person.group(1).strip()
            else:
                m_person2 = re.search(r"(?:trả|chưa trả|thu nợ|thanh toán)\s+(?:nợ\s+)?(?:cho\s+)?([A-Za-zÀ-ỹ\s]+)", text, re.IGNORECASE)
                if m_person2:
                    person = re.sub(r"\d+.*", "", m_person2.group(1)).strip()

        # Nếu chưa có amount, kiểm tra regex số tiền
        if amount is None and (not is_full or target_status == "Nợ"):
            m_amt = re.search(r"(\d+[\d\.,]*)\s*(k|cành|nghìn|ngàn|lốp|lít|củ|triệu|tr|m)?\b", text, re.IGNORECASE)
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
            await update.message.reply_text("Không nhận diện được tên người hoặc Mã GD. Bạn hãy thử nhắn lại (vd: `Tuấn Anh đã trả nợ` hoặc `Mã NO2608205754 chưa trả`).")
            return

        updated_items = sheets_service.update_debt_status(
            debt_id=debt_id,
            person=person,
            status=target_status,
            amount=amount,
            is_full=is_full
        )

        if updated_items:
            title_str = "✅ **ĐÃ CẬP NHẬT TRẠNG THÁI: ĐÃ TRẢ**" if target_status == "Đã trả" else "🔄 **ĐÃ CHUYỂN TRẠNG THÁI: NỢ (CHƯA TRẢ)**"
            lines = [
                title_str,
                "────────────────────────"
            ]
            for item in updated_items:
                lines.append(f"• Mã GD: `{item['id']}`")
                lines.append(f"• Người liên quan: **{item['person']}**")
                if item["status"] == "Đã trả":
                    lines.append(f"• Đã thanh toán: `{item['paid_amount']:,.0f} VNĐ` | Số dư nợ còn lại: `0 VNĐ`")
                    lines.append("• Trạng thái mới: **Đã trả**")
                else:
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
            target_str = f"mã `{debt_id}`" if debt_id else f"người **{person}**"
            await update.message.reply_text(
                f"Không tìm thấy khoản nợ nào phù hợp với {target_str} trong Sổ Ghi Nợ.",
                parse_mode="Markdown"
            )

    # 3. HỎI ĐÁP VỀ SỔ NỢ
    elif intent == "QUERY_DEBT":
        query_person = ai_result.get("person") or ""
        if not query_person:
            # Kiểm tra xem có tên người trong câu không
            m_q = re.search(r"(?:nợ\s+của\s+|kiểm\s+tra\s+nợ\s+|nợ\s+)([A-Za-zÀ-ỹ\s]+)", text, re.IGNORECASE)
            if m_q:
                query_person = re.sub(r"(?:vẫn|đang|bao nhiêu|không|nhé|ạ).*", "", m_q.group(1)).strip()

        debt_summary = sheets_service.get_debt_summary(user_id=user_id)
        items = debt_summary.get("items", [])

        if query_person:
            person_clean = query_person.lower()
            matched = [it for it in items if person_clean in it["person"].lower() or it["person"].lower() in person_clean]
            if matched:
                total_p = sum(it["amount"] for it in matched)
                lines = [
                    f"📒 **THÔNG TIN CÔNG NỢ CỦA {query_person.upper()}:**",
                    "────────────────────────",
                    f"• Tổng nợ hiện tại: `{total_p:,.0f} VNĐ`\n",
                    "**Chi tiết các khoản:**"
                ]
                for it in matched:
                    d_str = f" | Ngày: {it['debt_date']}" if it.get("debt_date") else ""
                    n_str = f" - {it['note']}" if it.get("note") else ""
                    lines.append(f"- Mã `{it['id']}`: `{it['amount']:,.0f} VNĐ` [{it['status']}]{d_str}{n_str}")
                
                sheet_url = sheets_service.get_sheet_url()
                if sheet_url:
                    lines.append(f"\n[Mở Google Sheet]({sheet_url})")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            else:
                await update.message.reply_text(f"Hiện tại **{query_person}** không có khoản nợ nào chưa trả trong sổ.", parse_mode="Markdown")
        else:
            await debt_command(update, context)

    # 4. GHI NHẬN CHI TIÊU / THU NHẬP (TAB SỔ CHI TIÊU)
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
