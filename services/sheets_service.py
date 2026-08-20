import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import gspread
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = [
    "Mã GD",
    "Thời Gian",
    "Loại",
    "Số tiền",
    "Đơn vị",
    "Mô Tả"
]

HEADERS_DEBT = [
    "Mã GD",
    "Thời gian ghi",
    "Thời gian nợ",
    "Người vay/ Chủ nợ",
    "Số tiền",
    "Đơn vị",
    "Ghi chú",
    "Trạng thái"
]

def parse_amount(val: Any) -> int:
    """Chuyển đổi an toàn giá trị tiền tệ sang số nguyên VNĐ."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().replace("đ", "").replace("VNĐ", "").replace("vnd", "").replace(" ", "")
    # Loại bỏ dấu phân cách hàng nghìn (cả dấu phẩy và dấu chấm)
    s = s.replace(",", "")
    if "." in s:
        parts = s.split(".")
        # Nếu dấu chấm là phân cách hàng nghìn (vd: 500.000)
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)
    try:
        return int(float(s))
    except Exception:
        return 0

class SheetsService:
    def __init__(self):
        self.client: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self.worksheet: Optional[gspread.Worksheet] = None
        self.debt_worksheet: Optional[gspread.Worksheet] = None
        self._init_connection()

    def _init_connection(self):
        """Khởi tạo kết nối với Google Sheets từ file hoặc biến môi trường JSON."""
        creds = None
        if config.GOOGLE_CREDENTIALS_JSON:
            try:
                import json
                info = json.loads(config.GOOGLE_CREDENTIALS_JSON)
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            except Exception as e:
                print(f"Loi doc GOOGLE_CREDENTIALS_JSON tu bien moi truong: {e}")

        if not creds and os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
            try:
                creds = Credentials.from_service_account_file(
                    config.GOOGLE_CREDENTIALS_FILE,
                    scopes=SCOPES
                )
            except Exception as e:
                print(f"Loi doc Google credentials file: {e}")

        if not creds:
            print("Canh bao: Chua cau hinh Google Service Account (file credentials hoac bien GOOGLE_CREDENTIALS_JSON).")
            return

        try:
            self.client = gspread.authorize(creds)
            self._get_or_create_sheet()
            self._get_or_create_debt_sheet()
        except Exception as e:
            print(f"Loi ket noi Google Sheets: {e}")

    def _get_or_create_sheet(self):
        """Tìm hoặc mở bảng tính, khởi tạo tiêu đề tab Sổ Chi Tiêu nếu chưa có."""
        if not self.client:
            return

        sheet_target = config.SPREADSHEET_ID_OR_NAME
        try:
            if len(sheet_target) > 30 and "/" not in sheet_target:
                self.spreadsheet = self.client.open_by_key(sheet_target)
            elif "docs.google.com/spreadsheets/d/" in sheet_target:
                self.spreadsheet = self.client.open_by_url(sheet_target)
            else:
                self.spreadsheet = self.client.open(sheet_target)
        except gspread.exceptions.SpreadsheetNotFound:
            try:
                self.spreadsheet = self.client.create(sheet_target)
            except Exception as e:
                print(f"Khong the tao moi bang tinh: {e}")
                return
        except Exception as e:
            print(f"Loi mo bang tinh: {e}")
            return

        # Lấy hoặc tạo sheet Chi Tiêu
        try:
            self.worksheet = self.spreadsheet.sheet1
            existing_values = self.worksheet.row_values(1)
            if not existing_values or existing_values != HEADERS:
                if not existing_values:
                    self.worksheet.insert_row(HEADERS, index=1)
                else:
                    self.worksheet.update(values=[HEADERS], range_name="A1:F1")
                try:
                    self.worksheet.update_title("Sổ Chi Tiêu")
                except Exception:
                    pass

            self._format_worksheet(self.worksheet, is_debt=False)
        except Exception as e:
            print(f"Loi khoi tao Worksheet Chi Tieu: {e}")

    def _get_or_create_debt_sheet(self):
        """Tìm hoặc tạo tab riêng 'Sổ Ghi Nợ' trong Google Sheet."""
        if not self.spreadsheet:
            return

        try:
            try:
                self.debt_worksheet = self.spreadsheet.worksheet("Sổ Ghi Nợ")
            except gspread.exceptions.WorksheetNotFound:
                print("Tao tab moi 'So Ghi No'...")
                self.debt_worksheet = self.spreadsheet.add_worksheet(title="Sổ Ghi Nợ", rows=100, cols=10)

            existing_values = self.debt_worksheet.row_values(1)
            if not existing_values or existing_values != HEADERS_DEBT:
                if not existing_values:
                    self.debt_worksheet.insert_row(HEADERS_DEBT, index=1)
                else:
                    self.debt_worksheet.update(values=[HEADERS_DEBT], range_name="A1:H1")

            self._format_worksheet(self.debt_worksheet, is_debt=True)
        except Exception as e:
            print(f"Loi khoi tao Worksheet Ghi No: {e}")

    def _setup_debt_conditional_formatting(self):
        """Thiết lập Dropdown List và Định dạng màu có điều kiện cho cột Trạng thái (Cột H)."""
        if not self.spreadsheet or not self.debt_worksheet:
            return

        try:
            sheet_id = self.debt_worksheet.id
            body = {
                "requests": [
                    # 1. Dropdown List chọn Nợ / Đã trả cho cột H (startColIndex=7, endColIndex=8)
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 1000,
                                "startColumnIndex": 7,
                                "endColumnIndex": 8
                            },
                            "rule": {
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": [
                                        {"userEnteredValue": "Nợ"},
                                        {"userEnteredValue": "Đã trả"}
                                    ]
                                },
                                "showCustomUi": True,
                                "strict": True
                            }
                        }
                    },
                    # 2. Quy tắc màu: "Nợ" -> Nền đỏ (#D93025), chữ vàng (#FFF066), in đậm
                    {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": 1000,
                                    "startColumnIndex": 7,
                                    "endColumnIndex": 8
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": "Nợ"}]
                                    },
                                    "format": {
                                        "backgroundColor": {"red": 0.85, "green": 0.19, "blue": 0.15},
                                        "textFormat": {
                                            "foregroundColor": {"red": 1.0, "green": 0.95, "blue": 0.20},
                                            "bold": True
                                        }
                                    }
                                }
                            },
                            "index": 0
                        }
                    },
                    # 3. Quy tắc màu: "Đã trả" -> Nền xanh lá đậm (#0F5132), chữ xanh lá nhạt (#D1E7DD), in đậm
                    {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": 1000,
                                    "startColumnIndex": 7,
                                    "endColumnIndex": 8
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": "Đã trả"}]
                                    },
                                    "format": {
                                        "backgroundColor": {"red": 0.08, "green": 0.45, "blue": 0.20},
                                        "textFormat": {
                                            "foregroundColor": {"red": 0.81, "green": 0.95, "blue": 0.84},
                                            "bold": True
                                        }
                                    }
                                }
                            },
                            "index": 1
                        }
                    }
                ]
            }
            self.spreadsheet.batch_update(body)
        except Exception as e:
            print(f"Loi cau hinh conditional formatting / validation: {e}")

    def _format_worksheet(self, ws: gspread.Worksheet, is_debt: bool = False):
        """Áp dụng quy tắc định dạng Times New Roman, nền đen chữ trắng và căn lề."""
        try:
            if not is_debt:
                # 1. Format Header Sổ Chi Tiêu (A1:F1 - 6 cột)
                ws.format("A1:F1", {
                    "backgroundColor": {"red": 0.12, "green": 0.12, "blue": 0.12},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "fontSize": 11,
                        "bold": True,
                        "fontFamily": "Times New Roman"
                    }
                })
                # 2. Format dữ liệu Sổ Chi Tiêu (A2:C Center, D Center + numberFormat, E Center - Đơn vị, F Left - Mô Tả)
                ws.format("A2:C", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("D2:D", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "numberFormat": {
                        "type": "NUMBER",
                        "pattern": "#,##0"
                    },
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("E2:E", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("F2:F", {
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
            else:
                # 1. Format Header Sổ Ghi Nợ (A1:H1 - 8 cột)
                ws.format("A1:H1", {
                    "backgroundColor": {"red": 0.12, "green": 0.12, "blue": 0.12},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "fontSize": 11,
                        "bold": True,
                        "fontFamily": "Times New Roman"
                    }
                })
                # 2. Format dữ liệu Sổ Ghi Nợ (A2:D Center, E Center + numberFormat, F Center - Đơn vị, G Left - Ghi chú, H Center - Trạng thái)
                ws.format("A2:D", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("E2:E", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "numberFormat": {
                        "type": "NUMBER",
                        "pattern": "#,##0"
                    },
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("F2:F", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("G2:G", {
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman"}
                })
                ws.format("H2:H", {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontFamily": "Times New Roman", "bold": True}
                })
                # Áp dụng Dropdown và màu sắc có điều kiện
                self._setup_debt_conditional_formatting()

            ws.freeze(rows=1)
        except Exception as err:
            print(f"Loi dinh dang bang: {err}")

    def get_sheet_url(self) -> Optional[str]:
        """Lấy URL của Google Sheet để gửi cho người dùng."""
        if self.spreadsheet:
            return self.spreadsheet.url
        return None

    def add_transactions(self, items: List[Dict[str, Any]], user_id: int, user_name: str) -> List[Dict[str, Any]]:
        """Thêm giao dịch vào tab 'Sổ Chi Tiêu' (6 cột)."""
        if not self.worksheet:
            self._init_connection()
            if not self.worksheet:
                raise Exception("Không thể kết nối đến Google Sheets.")

        now = datetime.now(config.TIMEZONE)
        results = []
        rows_to_append = []

        for item in items:
            tx_id = "TX" + now.strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()
            tx_time = item.get("date") or now.strftime("%Y-%m-%d %H:%M:%S")
            tx_type = item.get("type", "Chi tiêu")
            amount = int(item.get("amount", 0))
            unit = "VNĐ"
            note = item.get("note", "")

            row = [
                tx_id,
                tx_time,
                tx_type,
                amount,
                unit,
                note
            ]
            rows_to_append.append(row)
            results.append({
                "id": tx_id,
                "time": tx_time,
                "type": tx_type,
                "amount": amount,
                "unit": unit,
                "note": note
            })

        if rows_to_append:
            self.worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")

        return results

    def add_debt_transactions(self, items: List[Dict[str, Any]], user_id: int, user_name: str) -> List[Dict[str, Any]]:
        """Thêm giao dịch vào tab riêng 'Sổ Ghi Nợ' (8 cột)."""
        if not self.debt_worksheet:
            self._init_connection()
            if not self.debt_worksheet:
                raise Exception("Không thể mở tab 'Sổ Ghi Nợ' trên Google Sheets.")

        now = datetime.now(config.TIMEZONE)
        results = []
        rows_to_append = []

        for item in items:
            tx_id = "NO" + now.strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()
            tx_created_time = now.strftime("%Y-%m-%d %H:%M:%S")
            # Nếu không có ngày/tháng trong tin nhắn thì để trống ""
            debt_date = item.get("debt_date") or ""
            person = item.get("person", "Không rõ")
            amount = int(item.get("amount", 0))
            unit = "VNĐ"
            # Nếu không có lý do thì để trống ""
            note = item.get("note") or ""
            status = item.get("status") or "Nợ"

            row = [
                tx_id,
                tx_created_time,
                debt_date,
                person,
                amount,
                unit,
                note,
                status
            ]
            rows_to_append.append(row)
            results.append({
                "id": tx_id,
                "created_time": tx_created_time,
                "debt_date": debt_date,
                "person": person,
                "amount": amount,
                "unit": unit,
                "note": note,
                "status": status
            })

        if rows_to_append:
            self.debt_worksheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            self._format_worksheet(self.debt_worksheet, is_debt=True)

        return results

    def get_debt_summary(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Tổng hợp danh sách các khoản nợ từ Sổ Ghi Nợ."""
        if not self.debt_worksheet:
            self._init_connection()
            if not self.debt_worksheet:
                return {"total_amount": 0, "items": []}

        records = self.debt_worksheet.get_all_records(numericise_ignore=['all'])
        total_amount = 0
        active_debts = []

        for rec in records:
            amount = parse_amount(rec.get("Số tiền", rec.get("Số Tiền (VNĐ)", 0)))
            person = str(rec.get("Người vay/ Chủ nợ", rec.get("Người Vay / Chủ Nợ", ""))).strip()
            debt_date = str(rec.get("Thời gian nợ", rec.get("Thời Gian Nợ", ""))).strip()
            note = str(rec.get("Ghi chú", rec.get("Ghi Chú", ""))).strip()
            time_str = str(rec.get("Thời gian ghi", rec.get("Thời Gian Ghi", ""))).strip()
            status = str(rec.get("Trạng thái", "Nợ")).strip()

            if amount > 0 and status != "Đã trả":
                total_amount += amount
                active_debts.append({
                    "id": rec.get("Mã GD", ""),
                    "time": time_str,
                    "debt_date": debt_date,
                    "person": person,
                    "amount": amount,
                    "unit": "VNĐ",
                    "note": note,
                    "status": status
                })

        return {
            "total_amount": total_amount,
            "items": active_debts
        }

    def get_debts_by_month(self, user_id: Optional[int] = None, month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
        """Lấy danh sách các khoản nợ phát sinh trong tháng và năm."""
        if not self.debt_worksheet:
            self._init_connection()
            if not self.debt_worksheet:
                return {"total_debt": 0, "items": []}

        now = datetime.now(config.TIMEZONE)
        target_month = month if month is not None else now.month
        target_year = year if year is not None else now.year

        records = self.debt_worksheet.get_all_records(numericise_ignore=['all'])
        filtered_debts = []
        total_debt = 0

        for rec in records:
            time_str = str(rec.get("Thời gian ghi", rec.get("Thời Gian Ghi", ""))).strip()
            parsed_date = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    parsed_date = datetime.strptime(time_str[:19], fmt)
                    break
                except ValueError:
                    pass

            if parsed_date and parsed_date.month == target_month and parsed_date.year == target_year:
                amount = parse_amount(rec.get("Số tiền", rec.get("Số Tiền (VNĐ)", 0)))
                person = str(rec.get("Người vay/ Chủ nợ", rec.get("Người Vay / Chủ Nợ", ""))).strip()
                debt_date = str(rec.get("Thời gian nợ", rec.get("Thời Gian Nợ", ""))).strip()
                note = str(rec.get("Ghi chú", rec.get("Ghi Chú", ""))).strip()
                status = str(rec.get("Trạng thái", "Nợ")).strip()

                if amount > 0:
                    if status != "Đã trả":
                        total_debt += amount
                    filtered_debts.append({
                        "id": rec.get("Mã GD", ""),
                        "time": time_str,
                        "debt_date": debt_date,
                        "person": person,
                        "amount": amount,
                        "unit": "VNĐ",
                        "note": note,
                        "status": status
                    })

        return {
            "total_debt": total_debt,
            "items": filtered_debts
        }

    def get_transactions_by_month(self, user_id: Optional[int] = None, month: Optional[int] = None, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách giao dịch chi tiêu theo tháng và năm."""
        if not self.worksheet:
            self._init_connection()
            if not self.worksheet:
                return []

        now = datetime.now(config.TIMEZONE)
        target_month = month if month is not None else now.month
        target_year = year if year is not None else now.year

        records = self.worksheet.get_all_records(numericise_ignore=['all'])
        filtered = []

        for rec in records:
            rec_user_id = str(rec.get("User ID", "")).strip()
            if user_id and rec_user_id and rec_user_id != str(user_id):
                continue

            time_str = str(rec.get("Thời Gian", "")).strip()
            if not time_str:
                continue

            parsed_date = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    parsed_date = datetime.strptime(time_str[:19], fmt)
                    break
                except ValueError:
                    pass

            if parsed_date and parsed_date.month == target_month and parsed_date.year == target_year:
                amount = parse_amount(rec.get("Số tiền", rec.get("Số Tiền (VNĐ)", 0)))
                filtered.append({
                    "id": rec.get("Mã GD", ""),
                    "time": time_str,
                    "date_obj": parsed_date,
                    "type": rec.get("Loại", "Chi tiêu"),
                    "amount": amount,
                    "note": rec.get("Mô Tả", ""),
                    "user_id": rec_user_id,
                    "user_name": rec.get("Tên Người Dùng", "")
                })

        return filtered

    def get_monthly_summary(self, user_id: Optional[int] = None, month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
        """Tính toán tổng kết chi tiêu trong tháng."""
        transactions = self.get_transactions_by_month(user_id, month, year)
        
        total_expense = 0
        total_income = 0

        for tx in transactions:
            amount = tx["amount"]
            tx_type = tx["type"].strip()

            if "thu" in tx_type.lower():
                total_income += amount
            else:
                total_expense += amount

        now = datetime.now(config.TIMEZONE)
        return {
            "month": month if month is not None else now.month,
            "year": year if year is not None else now.year,
            "total_expense": total_expense,
            "total_income": total_income,
            "balance": total_income - total_expense,
            "transaction_count": len(transactions),
            "transactions": transactions
        }

    def get_recent_transactions(self, user_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy các giao dịch gần đây nhất trong Sổ Chi Tiêu."""
        if not self.worksheet:
            self._init_connection()
            if not self.worksheet:
                return []

        records = self.worksheet.get_all_records(numericise_ignore=['all'])
        if user_id:
            records = [r for r in records if str(r.get("User ID", "")).strip() == str(user_id)]

        records = records[-limit:]
        records.reverse()

        result = []
        for rec in records:
            amount = parse_amount(rec.get("Số tiền", rec.get("Số Tiền (VNĐ)", 0)))
            result.append({
                "id": rec.get("Mã GD", ""),
                "time": rec.get("Thời Gian", ""),
                "type": rec.get("Loại", "Chi tiêu"),
                "amount": amount,
                "note": rec.get("Mô Tả", "")
            })
        return result

    def delete_transaction_by_id(self, tx_id: str, user_id: Optional[int] = None) -> bool:
        """Xóa giao dịch theo mã GD trong cả tab Chi Tiêu hoặc tab Ghi Nợ."""
        if not self.spreadsheet:
            self._init_connection()
            if not self.spreadsheet:
                return False

        tx_id_clean = tx_id.strip().upper()
        
        # Tìm trong Sổ Chi Tiêu trước
        try:
            if self.worksheet:
                cell = self.worksheet.find(tx_id_clean, in_column=1)
                if cell:
                    self.worksheet.delete_rows(cell.row)
                    return True
        except Exception:
            pass

        # Tìm trong Sổ Ghi Nợ
        try:
            if self.debt_worksheet:
                cell = self.debt_worksheet.find(tx_id_clean, in_column=1)
                if cell:
                    self.debt_worksheet.delete_rows(cell.row)
                    return True
        except Exception:
            pass

        return False

# Khởi tạo singleton instance
sheets_service = SheetsService()
