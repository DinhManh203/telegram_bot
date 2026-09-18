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

HEADERS_SUBSCRIBERS = [
    "Chat ID",
    "Tên Người Dùng",
    "Ngày Đăng Ký",
    "Lần Tương Tác Cuối"
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
        self.subscribers_worksheet: Optional[gspread.Worksheet] = None
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
                print(f"Lỗi đọc GOOGLE_CREDENTIALS_JSON từ biến môi trường: {e}")

        if not creds and os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
            try:
                creds = Credentials.from_service_account_file(
                    config.GOOGLE_CREDENTIALS_FILE,
                    scopes=SCOPES
                )
            except Exception as e:
                print(f"Lỗi đọc Google credentials file: {e}")

        if not creds:
            print("Cảnh báo: Chưa cấu hình Google Service Account (file credentials hoặc biến GOOGLE_CREDENTIALS_JSON).")
            return

        try:
            self.client = gspread.authorize(creds)
            self._get_or_create_sheet()
            self._get_or_create_debt_sheet()
            self._get_or_create_subscribers_sheet()
        except Exception as e:
            print(f"Lỗi kết nối Google Sheets: {e}")

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
                print(f"Không thể tạo mới bảng tính: {e}")
                return
        except Exception as e:
            print(f"Lỗi mở bảng tính: {e}")
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
            print(f"Lỗi khởi tạo Worksheet Chi Tiêu: {e}")

    def _get_or_create_debt_sheet(self):
        """Tìm hoặc tạo tab riêng 'Sổ Ghi Nợ' trong Google Sheet."""
        if not self.spreadsheet:
            return

        try:
            try:
                self.debt_worksheet = self.spreadsheet.worksheet("Sổ Ghi Nợ")
            except gspread.exceptions.WorksheetNotFound:
                print("Tạo tab mới 'Sổ Ghi Nợ'...")
                self.debt_worksheet = self.spreadsheet.add_worksheet(title="Sổ Ghi Nợ", rows=100, cols=10)

            existing_values = self.debt_worksheet.row_values(1)
            if not existing_values or existing_values != HEADERS_DEBT:
                if not existing_values:
                    self.debt_worksheet.insert_row(HEADERS_DEBT, index=1)
                else:
                    self.debt_worksheet.update(values=[HEADERS_DEBT], range_name="A1:H1")
                self._format_worksheet(self.debt_worksheet, is_debt=True)
        except Exception as e:
            print(f"Lỗi khởi tạo Worksheet Ghi Nợ: {e}")

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
            print(f"Lỗi cấu hình định dạng có điều kiện / danh sách lựa chọn: {e}")

    def _format_worksheet(self, ws: gspread.Worksheet, is_debt: bool = False):
        """Áp dụng toàn bộ quy tắc định dạng (nền đen header, nền xám chữ đậm cho tiêu đề Tháng/Ngày, nền trắng cho dữ liệu) trong 1 request batch_update duy nhất."""
        try:
            if not self.spreadsheet or not ws:
                return

            sheet_id = ws.id
            num_cols = 8 if is_debt else 6

            requests = [
                # 1. Format Header cột hàng 1 (Nền đen #1F1F1F, chữ trắng in đậm, Times New Roman, căn giữa)
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.12, "green": 0.12, "blue": 0.12},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                    "fontSize": 11,
                                    "bold": True,
                                    "fontFamily": "Times New Roman"
                                }
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                    }
                },
                # 2. Reset toàn bộ vùng dữ liệu từ hàng 2 sang nền trắng, chữ thường
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                                    "bold": False,
                                    "fontFamily": "Times New Roman"
                                }
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                    }
                }
            ]

            # Căn lề và numberFormat riêng cho các cột
            if not is_debt:
                # Cột D: Số tiền (căn giữa, numberFormat)
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 3,
                            "endColumnIndex": 4
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
                    }
                })
                # Cột F: Mô Tả (căn trái)
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 5,
                            "endColumnIndex": 6
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "LEFT"
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment)"
                    }
                })
            else:
                # Cột E: Số tiền (căn giữa, numberFormat)
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 4,
                            "endColumnIndex": 5
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
                    }
                })
                # Cột G: Ghi chú (căn trái)
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 6,
                            "endColumnIndex": 7
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "LEFT"
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment)"
                    }
                })
                # Cột H: Trạng thái (in đậm)
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 7,
                            "endColumnIndex": 8
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True, "fontFamily": "Times New Roman"}
                            }
                        },
                        "fields": "userEnteredFormat(textFormat)"
                    }
                })

            # 3. Quét tất cả các hàng để tìm và áp dụng định dạng Nền Xám + Chữ Đậm cho các tiêu đề Tháng / Ngày
            all_vals = ws.get_all_values()
            for row_idx, r in enumerate(all_vals[1:], start=2):
                if not r or not r[0]:
                    continue
                first_cell = r[0].strip().lower()
                if first_cell.startswith("tháng ") or first_cell.startswith("ngày "):
                    requests.append({
                        "mergeCells": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_idx - 1,
                                "endRowIndex": row_idx,
                                "startColumnIndex": 0,
                                "endColumnIndex": num_cols
                            },
                            "mergeType": "MERGE_ALL"
                        }
                    })
                    requests.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_idx - 1,
                                "endRowIndex": row_idx,
                                "startColumnIndex": 0,
                                "endColumnIndex": num_cols
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                                    "horizontalAlignment": "CENTER",
                                    "verticalAlignment": "MIDDLE",
                                    "textFormat": {
                                        "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                                        "fontSize": 11,
                                        "bold": True,
                                        "fontFamily": "Times New Roman"
                                    }
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                        }
                    })

            self.spreadsheet.batch_update({"requests": requests})
            if is_debt:
                self._setup_debt_conditional_formatting()
            ws.freeze(rows=1)
        except Exception as err:
            print(f"Lỗi định dạng bảng tính: {err}")

    def get_sheet_url(self) -> Optional[str]:
        """Lấy URL của Google Sheet để gửi cho người dùng."""
        if self.spreadsheet:
            return self.spreadsheet.url
        return None

    def _format_header_row(self, ws: gspread.Worksheet, row_idx: int, end_col: str):
        """Format một hàng tiêu đề hợp nhất nền xám chữ đen đậm trong 1 request batch_update duy nhất."""
        try:
            num_cols = 8 if end_col == "H" else 6
            requests = [
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": row_idx - 1,
                            "endRowIndex": row_idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "mergeType": "MERGE_ALL"
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": row_idx - 1,
                            "endRowIndex": row_idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                                    "fontSize": 11,
                                    "bold": True,
                                    "fontFamily": "Times New Roman"
                                }
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
                    }
                }
            ]
            if self.spreadsheet:
                self.spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            print(f"Lỗi format header row {row_idx}: {e}")

    def _ensure_month_header(self, ws: gspread.Worksheet, month: int, is_debt: bool = False):
        """Nếu chưa có hàng tiêu đề tháng (ví dụ 'Tháng 8'), chèn hàng hợp nhất nền xám chữ đen đậm."""
        month_label = f"Tháng {month}"
        try:
            all_vals = ws.get_all_values()
            # Kiểm tra xem tiêu đề tháng này đã xuất hiện trong bảng chưa
            for r in all_vals:
                if r and r[0].strip().lower() == month_label.lower():
                    return

            end_col = "H" if is_debt else "F"
            res = ws.append_row([month_label], value_input_option="USER_ENTERED")
            
            row_idx = None
            if isinstance(res, dict):
                updated_range = res.get('updates', {}).get('updatedRange', '')
                import re
                m = re.search(r"[A-Za-z]+(\d+)", updated_range.split("!")[-1])
                if m:
                    row_idx = int(m.group(1))
            if not row_idx:
                row_idx = len(ws.get_all_values())

            self._format_header_row(ws, row_idx, end_col)
        except Exception as e:
            print(f"Lỗi chèn tiêu đề tháng '{month_label}': {e}")

    def _ensure_day_header(self, ws: gspread.Worksheet, day: int, month: int, is_debt: bool = False):
        """Đảm bảo có hàng tiêu đề tháng trước, sau đó chèn hàng tiêu đề ngày (ví dụ 'Ngày 25 tháng 8')."""
        self._ensure_month_header(ws, month=month, is_debt=is_debt)

        day_label = f"Ngày {day} tháng {month}"
        try:
            all_vals = ws.get_all_values()
            # Kiểm tra xem tiêu đề ngày này đã xuất hiện trong bảng chưa
            for r in all_vals:
                if r and (
                    r[0].strip().lower() == day_label.lower() or
                    r[0].strip().lower() == f"ngày {day}/{month}" or
                    r[0].strip().lower() == f"ngày {day:02d}/{month:02d}"
                ):
                    return

            end_col = "H" if is_debt else "F"
            res = ws.append_row([day_label], value_input_option="USER_ENTERED")
            
            row_idx = None
            if isinstance(res, dict):
                updated_range = res.get('updates', {}).get('updatedRange', '')
                import re
                m = re.search(r"[A-Za-z]+(\d+)", updated_range.split("!")[-1])
                if m:
                    row_idx = int(m.group(1))
            if not row_idx:
                row_idx = len(ws.get_all_values())

            self._format_header_row(ws, row_idx, end_col)
        except Exception as e:
            print(f"Lỗi chèn tiêu đề ngày '{day_label}': {e}")

    def add_transactions(self, items: List[Dict[str, Any]], user_id: int, user_name: str) -> List[Dict[str, Any]]:
        """Thêm giao dịch vào tab 'Sổ Chi Tiêu' (6 cột)."""
        if not self.worksheet:
            self._init_connection()
            if not self.worksheet:
                raise Exception("Không thể kết nối đến Google Sheets.")

        now = datetime.now(config.TIMEZONE)
        results = []
        grouped_by_date: Dict[tuple, list] = {}

        for item in items:
            tx_id = "TX" + now.strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()
            tx_time = item.get("date") or now.strftime("%Y-%m-%d %H:%M:%S")
            tx_type = item.get("type", "Chi tiêu")
            amount = int(item.get("amount", 0))
            unit = "VNĐ"
            note = item.get("note", "")

            # Trích xuất ngày & tháng của giao dịch
            parsed_dt = now
            if item.get("date"):
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                    try:
                        parsed_dt = datetime.strptime(str(item["date"]).strip()[:19], fmt)
                        break
                    except ValueError:
                        pass

            date_key = (parsed_dt.day, parsed_dt.month)
            if date_key not in grouped_by_date:
                grouped_by_date[date_key] = []

            row = [
                tx_id,
                tx_time,
                tx_type,
                amount,
                unit,
                note
            ]
            grouped_by_date[date_key].append(row)
            results.append({
                "id": tx_id,
                "time": tx_time,
                "type": tx_type,
                "amount": amount,
                "unit": unit,
                "note": note
            })

        for (day, month), rows in grouped_by_date.items():
            self._ensure_day_header(self.worksheet, day=day, month=month, is_debt=False)
            if rows:
                self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        return results

    def add_debt_transactions(self, items: List[Dict[str, Any]], user_id: int, user_name: str) -> List[Dict[str, Any]]:
        """Thêm giao dịch vào tab riêng 'Sổ Ghi Nợ' (8 cột)."""
        if not self.debt_worksheet:
            self._init_connection()
            if not self.debt_worksheet:
                raise Exception("Không thể mở tab 'Sổ Ghi Nợ' trên Google Sheets.")

        now = datetime.now(config.TIMEZONE)
        # Đảm bảo có dòng tiêu đề ngày trước khi chèn giao dịch nợ
        self._ensure_day_header(self.debt_worksheet, day=now.day, month=now.month, is_debt=True)

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

        return results

    def update_debt_status(
        self,
        debt_id: Optional[str] = None,
        person: Optional[str] = None,
        status: str = "Đã trả",
        amount: Optional[int] = None,
        is_full: bool = True
    ) -> List[Dict[str, Any]]:
        """Cập nhật trạng thái ('Đã trả' hoặc 'Nợ') và số tiền cho khoản nợ theo Mã GD hoặc tên người."""
        if not self.debt_worksheet:
            self._init_connection()
            if not self.debt_worksheet:
                return []

        try:
            all_vals = self.debt_worksheet.get_all_values()
            if len(all_vals) <= 1:
                return []

            updated_items = []
            person_clean = person.strip().lower() if person else ""
            debt_id_clean = debt_id.strip().upper() if debt_id else ""
            target_status = "Đã trả" if ("trả" in status.lower() and "chưa" not in status.lower()) else "Nợ"

            for row_idx, row in enumerate(all_vals[1:], start=2):
                if len(row) < 8:
                    continue
                r_id = row[0].strip().upper()
                r_person = row[3].strip()
                r_person_lower = r_person.lower()
                r_status = row[7].strip()
                r_amount = parse_amount(row[4])

                # Bỏ qua hàng không có thông tin nợ
                if not r_person or not r_id.startswith("NO"):
                    continue

                is_matched = False

                # 1. Khớp theo Mã GD nếu có (kể cả đang ở trạng thái nào)
                if debt_id_clean and (debt_id_clean == r_id or debt_id_clean in r_id):
                    is_matched = True
                # 2. Khớp theo tên người nợ
                elif person_clean and r_person_lower and (person_clean in r_person_lower or r_person_lower in person_clean):
                    if target_status == "Đã trả" and r_status != "Đã trả":
                        is_matched = True
                    elif target_status == "Nợ" and r_status == "Đã trả":
                        is_matched = True
                    elif target_status == "Nợ":
                        is_matched = True

                if not is_matched:
                    continue

                # Xác định số tiền và trạng thái mới
                if target_status == "Đã trả":
                    if is_full or amount is None or amount <= 0 or amount >= r_amount:
                        paid_amount = r_amount if r_amount > 0 else (amount or 0)
                        new_amount = 0
                        new_status = "Đã trả"
                    else:
                        paid_amount = amount
                        new_amount = r_amount - amount
                        new_status = "Nợ" if new_amount > 0 else "Đã trả"
                else:
                    # Chuyển ngược lại sang "Nợ" (Chưa trả nợ / Chưa nhận được tiền)
                    paid_amount = 0
                    if amount is not None and amount > 0:
                        new_amount = amount
                    elif r_amount > 0:
                        new_amount = r_amount
                    else:
                        new_amount = amount or 0
                    new_status = "Nợ"

                # Cập nhật trực tiếp lên Google Sheet: Cột E (Số tiền - col 5) và Cột H (Trạng thái - col 8)
                self.debt_worksheet.update_cell(row_idx, 5, new_amount)
                self.debt_worksheet.update_cell(row_idx, 8, new_status)

                updated_items.append({
                    "id": row[0],
                    "person": r_person,
                    "old_amount": r_amount,
                    "paid_amount": paid_amount,
                    "new_amount": new_amount,
                    "status": new_status,
                    "note": row[6] if len(row) > 6 else ""
                })

                # Nếu khớp chính xác Mã GD thì dừng lại
                if debt_id_clean and (debt_id_clean == r_id or debt_id_clean in r_id):
                    break

                # Khấu trừ số tiền trả nếu có
                if target_status == "Đã trả" and amount is not None and amount > 0:
                    amount -= paid_amount
                    if amount <= 0:
                        break

            return updated_items
        except Exception as e:
            print(f"Lỗi update_debt_status (debt_id={debt_id}, person={person}, status={status}): {e}")
            return []

    def mark_debt_as_paid(
        self,
        person: Optional[str] = None,
        debt_id: Optional[str] = None,
        amount: Optional[int] = None,
        is_full: bool = True
    ) -> List[Dict[str, Any]]:
        """Tìm khoản nợ theo Mã GD hoặc tên người và cập nhật trạng thái 'Đã trả'."""
        return self.update_debt_status(
            debt_id=debt_id,
            person=person,
            status="Đã trả",
            amount=amount,
            is_full=is_full
        )

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

                if (amount > 0 or status == "Đã trả") and person:
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
        valid_records = [r for r in records if str(r.get("Mã GD", "")).startswith("TX")]
        if user_id:
            valid_records = [r for r in valid_records if str(r.get("User ID", "")).strip() == str(user_id)]

        valid_records = valid_records[-limit:]
        valid_records.reverse()

        result = []
        for rec in valid_records:
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

    def reorganize_sheets_with_day_headers(self) -> bool:
        """Tổ chức lại toàn bộ dữ liệu hiện có trong Sổ Chi Tiêu và Sổ Ghi Nợ theo dải phân cách từng Ngày và Tháng."""
        if not self.spreadsheet:
            self._init_connection()
            if not self.spreadsheet:
                return False

        # 1. Tổ chức lại Sổ Chi Tiêu
        if self.worksheet:
            try:
                all_vals = self.worksheet.get_all_values()
                valid_rows = []
                for r in all_vals[1:]:
                    if r and len(r) >= 6 and r[0].startswith("TX"):
                        valid_rows.append(r[:6])

                # Gom nhóm theo ngày
                groups: Dict[tuple, list] = {}
                for r in valid_rows:
                    time_str = r[1]
                    parsed_dt = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                        try:
                            parsed_dt = datetime.strptime(time_str[:19], fmt)
                            break
                        except ValueError:
                            pass
                    if not parsed_dt:
                        parsed_dt = datetime.now(config.TIMEZONE)

                    key = (parsed_dt.year, parsed_dt.month, parsed_dt.day)
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(r)

                # Xóa toàn bộ nội dung cũ và ghi lại có dải phân cách ngày
                self.worksheet.clear()
                self.worksheet.update(values=[HEADERS], range_name="A1:F1")
                self._format_worksheet(self.worksheet, is_debt=False)

                for (yr, m, d), rows in groups.items():
                    self._ensure_day_header(self.worksheet, day=d, month=m, is_debt=False)
                    self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")

                self._format_worksheet(self.worksheet, is_debt=False)
                print("Đã tổ chức lại Sổ Chi Tiêu thành công!")
            except Exception as e:
                print(f"Lỗi tổ chức lại Sổ Chi Tiêu: {e}")

        # 2. Tổ chức lại Sổ Ghi Nợ
        if self.debt_worksheet:
            try:
                all_debt_vals = self.debt_worksheet.get_all_values()
                valid_debt_rows = []
                for r in all_debt_vals[1:]:
                    if r and len(r) >= 8 and r[0].startswith("NO"):
                        valid_debt_rows.append(r[:8])

                groups_debt: Dict[tuple, list] = {}
                for r in valid_debt_rows:
                    time_str = r[1]
                    parsed_dt = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                        try:
                            parsed_dt = datetime.strptime(time_str[:19], fmt)
                            break
                        except ValueError:
                            pass
                    if not parsed_dt:
                        parsed_dt = datetime.now(config.TIMEZONE)

                    key = (parsed_dt.year, parsed_dt.month, parsed_dt.day)
                    if key not in groups_debt:
                        groups_debt[key] = []
                    groups_debt[key].append(r)

                self.debt_worksheet.clear()
                self.debt_worksheet.update(values=[HEADERS_DEBT], range_name="A1:H1")
                self._format_worksheet(self.debt_worksheet, is_debt=True)

                for (yr, m, d), rows in groups_debt.items():
                    self._ensure_day_header(self.debt_worksheet, day=d, month=m, is_debt=True)
                    self.debt_worksheet.append_rows(rows, value_input_option="USER_ENTERED")

                self._format_worksheet(self.debt_worksheet, is_debt=True)
                print("Đã tổ chức lại Sổ Ghi Nợ thành công!")
            except Exception as e:
                print(f"Lỗi tổ chức lại Sổ Ghi Nợ: {e}")

        return True

    def _get_or_create_subscribers_sheet(self):
        """Tìm hoặc tạo tab riêng 'Subscribers' trong Google Sheet để lưu Chat ID lâu dài."""
        if not self.spreadsheet:
            return

        try:
            try:
                self.subscribers_worksheet = self.spreadsheet.worksheet("Subscribers")
            except gspread.exceptions.WorksheetNotFound:
                print("Tạo tab mới 'Subscribers'...")
                self.subscribers_worksheet = self.spreadsheet.add_worksheet(title="Subscribers", rows=100, cols=10)

            existing_values = self.subscribers_worksheet.row_values(1)
            if not existing_values or existing_values != HEADERS_SUBSCRIBERS:
                if not existing_values:
                    self.subscribers_worksheet.insert_row(HEADERS_SUBSCRIBERS, index=1)
                else:
                    self.subscribers_worksheet.update(values=[HEADERS_SUBSCRIBERS], range_name="A1:D1")
        except Exception as e:
            print(f"Lỗi khởi tạo Worksheet Subscribers: {e}")

    def get_subscribers_from_sheet(self) -> List[int]:
        """Lấy danh sách các Chat ID đã đăng ký từ tab Subscribers trên Google Sheet."""
        if not self.subscribers_worksheet:
            self._get_or_create_subscribers_sheet()
        if not self.subscribers_worksheet:
            return []

        try:
            records = self.subscribers_worksheet.get_all_values()
            if len(records) <= 1:
                return []

            chat_ids = []
            for row in records[1:]:
                if row and row[0]:
                    try:
                        cid = int(str(row[0]).strip())
                        if cid not in chat_ids:
                            chat_ids.append(cid)
                    except (ValueError, TypeError):
                        pass
            return chat_ids
        except Exception as e:
            print(f"Lỗi đọc danh sách subscribers từ Google Sheet: {e}")
            return []

    def save_subscriber_to_sheet(self, chat_id: int, user_name: str = ""):
        """Lưu hoặc cập nhật Chat ID người dùng vào tab Subscribers trên Google Sheet."""
        if not chat_id:
            return
        if not self.subscribers_worksheet:
            self._get_or_create_subscribers_sheet()
        if not self.subscribers_worksheet:
            return

        try:
            now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            records = self.subscribers_worksheet.get_all_values()

            found_row = None
            if len(records) > 1:
                for idx, row in enumerate(records[1:], start=2):
                    if row and str(row[0]).strip() == str(chat_id):
                        found_row = idx
                        break

            if found_row:
                prev_row = records[found_row - 1]
                saved_username = user_name or (prev_row[1] if len(prev_row) > 1 else "")
                reg_date = prev_row[2] if len(prev_row) > 2 and prev_row[2] else now_str
                update_vals = [str(chat_id), saved_username, reg_date, now_str]
                self.subscribers_worksheet.update(values=[update_vals], range_name=f"A{found_row}:D{found_row}")
            else:
                new_row = [str(chat_id), user_name, now_str, now_str]
                self.subscribers_worksheet.append_row(new_row)
        except Exception as e:
            print(f"Lỗi lưu subscriber vào Google Sheet: {e}")

# Khởi tạo singleton instance
sheets_service = SheetsService()
