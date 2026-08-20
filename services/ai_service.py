import json
import io
from datetime import datetime
from typing import Dict, Any, List, Optional
from PIL import Image
from google import genai
from google.genai import types
import config

SYSTEM_PROMPT = """
Bạn là trợ lý AI chuyên gia quản lý tài chính, chi tiêu và theo dõi công nợ cá nhân bằng tiếng Việt cho người dùng Telegram.
Nhiệm vụ của bạn là phân tích tin nhắn của người dùng (hoặc hình ảnh hóa đơn) và trả về kết quả dưới định dạng JSON có cấu trúc chuẩn xác.

Thời gian hệ thống hiện tại: {current_time}

QUY TẮC PHÂN LOẠI Ý ĐỊNH (INTENT):
1. "intent": "ADD_DEBT" -> KHI NGƯỜI DÙNG NHẮC ĐẾN VAY MƯỢN / CHO VAY / TRẢ NỢ / ĐÒI NỢ:
   - Cho người khác mượn / vay: "Cho Nam vay 500k", "Nam mượn 200k", "Cho anh Hùng mượn 1 củ"
   - Mình đi vay / mượn người khác: "Vay Tuấn 1 triệu", "Mượn mẹ 2 củ", "Vay bạn 500k"
   - Người khác trả nợ mình: "Nam trả nợ 500k", "Thu nợ anh Hùng 1tr"
   - Mình trả nợ cho người khác: "Trả nợ Tuấn 1 triệu", "Trả tiền mượn mẹ 2tr"
   => Khi là ADD_DEBT, trích xuất mảng "debt_items":
      - "person": Tên người vay / người cho vay (ví dụ: "Doãn Tuấn Anh", "Trịnh Dũng", "Nam", "Tuấn")
      - "debt_type": Một trong các loại: "Cho vay" | "Vay nợ" | "Thu nợ" | "Trả nợ"
      - "amount": Số tiền nguyên dương (VNĐ)
      - "debt_date": Ngày nợ (Ví dụ: nếu tin nhắn có ghi "ngày 15/8", "hôm qua", "20/07/2026" thì chuyển đổi chuẩn thành dạng "DD/MM/YYYY" hoặc "YYYY-MM-DD"). QUY TẮC BẮT BUỘC: Nếu trong tin nhắn KHÔNG có thời gian ngày/tháng thì BẮT BUỘC ĐỂ TRỐNG "" (chuỗi rỗng), KHÔNG ĐƯỢC tự ý điền ngày hôm nay!
      - "status": "Nợ" (đối với Cho vay / Vay nợ / còn nợ) hoặc "Đã trả" (đối với Thu nợ / Trả nợ / đã hoàn tất)
      - "note": Ghi chú lý do nếu người dùng có nói rõ (vd: "tiền mua sách", "tiền liên hoan"). QUY TẮC BẮT BUỘC: Nếu người dùng không nói rõ lý do (ví dụ chỉ nói: "Trịnh Dũng nợ 122k", "Cho Nam vay 500k") thì BẮT BUỘC ĐỂ TRỐNG "" (chuỗi rỗng), TUYỆT ĐỐI KHÔNG TỰ BỊA GHI CHÚ!
      - "date": "{current_time}"

2. "intent": "QUERY_DEBT" -> KHI NGƯỜI DÙNG HỎI VỀ DANH SÁCH NỢ:
   - "Ai đang nợ tôi?", "Tôi đang nợ những ai?", "Xem sổ nợ", "Kiểm tra nợ"

3. "intent": "ADD_TRANSACTION" -> KHI NGƯỜI DÙNG GHI NHẬN CHI TIÊU / THU NHẬP THÔNG THƯỜNG:
   - "Ăn phở 45k", "Đổ xăng 50k", "Mua áo 250k", "Lương về 15tr"
   => Trích xuất mảng "transactions" với các trường:
      - "amount": Số tiền nguyên dương (VNĐ)
      - "type": "Chi tiêu" hoặc "Thu nhập"
      - "category": "Ăn uống" | "Đi lại" | "Mua sắm" | "Hóa đơn" | "Giải trí" | "Sức khỏe" | "Giáo dục" | "Gia đình" | "Thu nhập" | "Khác"
      - "note": Mô tả ngắn gọn
      - "date": "{current_time}"

4. "intent": "QUERY_STATS" -> KHI HỎI VỀ THỐNG KÊ CHI TIÊU:
   - "Tháng này tiêu bao nhiêu rồi?", "Hôm nay ăn uống hết bao nhiêu?", "Báo cáo tháng này"

5. "intent": "CHAT" -> Lời chào hỏi hoặc trò chuyện thông thường.

QUY ĐỔI TIỀN TỆ TIẾNG VIỆT:
- "k", "cành", "nghìn", "ngàn" -> * 1.000 (vd: 50k = 50000, 30 cành = 30000)
- "lốp", "lít" -> * 100.000 (vd: 2 lốp = 200000)
- "củ", "triệu", "tr", "m" -> * 1.000.000 (vd: 1.5tr = 1500000, 2 củ = 2000000)

ĐỊNH DẠNG JSON TRẢ VỀ:
{{
  "intent": "ADD_DEBT" | "QUERY_DEBT" | "ADD_TRANSACTION" | "QUERY_STATS" | "CHAT",
  "debt_items": [
    {{
      "person": "Nam",
      "debt_type": "Cho vay",
      "amount": 500000,
      "status": "Chưa trả",
      "note": "Cho vay tiền",
      "date": "{current_time}"
    }}
  ],
  "transactions": [
    {{
      "amount": 45000,
      "type": "Chi tiêu",
      "category": "Ăn uống",
      "note": "Ăn phở bò",
      "date": "{current_time}"
    }}
  ],
  "query_info": {{
    "scope": "this_month",
    "category": null,
    "month": 8,
    "year": 2026
  }},
  "reply_message": "..."
}}
"""

class AIService:
    def __init__(self):
        self.client: Optional[genai.Client] = None
        self._init_client()

    def _init_client(self):
        """Khởi tạo Gemini Client."""
        if not config.GEMINI_API_KEY:
            print("⚠️ Cảnh báo: GEMINI_API_KEY chưa được thiết lập.")
            return

        try:
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        except Exception as e:
            print(f"❌ Lỗi khởi tạo Gemini Client: {e}")

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Phân tích tin nhắn văn bản của người dùng."""
        if not self.client:
            self._init_client()
            if not self.client:
                return {
                    "intent": "CHAT",
                    "transactions": [],
                    "debt_items": [],
                    "reply_message": "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng thêm API Key vào file .env."
                }

        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=f"Phân tích tin nhắn sau:\n{text}")
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )

            result_text = response.text.strip()
            data = json.loads(result_text)
            return data
        except Exception as e:
            print(f"❌ Lỗi phân tích văn bản AI: {e}")
            return {
                "intent": "CHAT",
                "transactions": [],
                "debt_items": [],
                "reply_message": f"Xin lỗi, đã xảy ra lỗi khi xử lý bằng AI: {str(e)}"
            }

    def analyze_image(self, image_bytes: bytes, caption: Optional[str] = None) -> Dict[str, Any]:
        """Phân tích ảnh chụp hóa đơn / biên lai."""
        if not self.client:
            self._init_client()
            if not self.client:
                return {
                    "intent": "CHAT",
                    "transactions": [],
                    "debt_items": [],
                    "reply_message": "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng thêm API Key vào file .env."
                }

        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)
        prompt_instruction = "Đây là ảnh hóa đơn/biên lai. Hãy đọc hóa đơn và trích xuất các khoản chi tiêu."
        if caption:
            prompt_instruction += f"\nGhi chú kèm theo của người dùng: {caption}"

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt_instruction),
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )

            result_text = response.text.strip()
            data = json.loads(result_text)
            return data
        except Exception as e:
            print(f"❌ Lỗi phân tích ảnh AI: {e}")
            return {
                "intent": "CHAT",
                "transactions": [],
                "debt_items": [],
                "reply_message": f"Không thể đọc thông tin từ ảnh: {str(e)}"
            }

ai_service = AIService()
