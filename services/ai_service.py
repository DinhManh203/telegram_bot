import json
import io
import base64
import httpx
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
            print("Cảnh báo: GEMINI_API_KEY chưa được thiết lập.")
            return

        try:
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        except Exception as e:
            print(f"Lỗi khởi tạo Gemini Client: {e}")

    def _analyze_text_gemini(self, text: str, prompt: str) -> Dict[str, Any]:
        """Phân tích văn bản bằng Model chính (Google Gemini)."""
        if not self.client:
            self._init_client()
            if not self.client:
                raise Exception("Chưa cấu hình GEMINI_API_KEY.")

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
        return json.loads(result_text)

    def _analyze_text_fallback(self, text: str, prompt: str) -> Dict[str, Any]:
        """Phân tích văn bản bằng Model dự phòng (OpenRouter / OpenAI-compatible)."""
        if not config.FALLBACK_AI_API_KEY:
            raise Exception("Chưa cấu hình FALLBACK_AI_API_KEY.")

        url = f"{config.FALLBACK_AI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.FALLBACK_AI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/SutieXuXi203/telegram_bot_wallet",
            "X-Title": "Telegram Wallet Bot"
        }
        payload = {
            "model": config.FALLBACK_AI_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Phân tích tin nhắn sau:\n{text}"}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        res = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        if res.status_code != 200:
            raise Exception(f"Fallback Model trả về mã lỗi {res.status_code}: {res.text[:200]}")

        content = res.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Phân tích tin nhắn văn bản với cơ chế tự động chuyển sang Model dự phòng khi lỗi."""
        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)

        # 1. Thử gọi Model chính (Google Gemini)
        if config.GEMINI_API_KEY:
            try:
                return self._analyze_text_gemini(text, prompt)
            except Exception as e:
                print(f"Model chính Gemini gặp sự cố ({e}). Đang chuyển sang Model dự phòng ({config.FALLBACK_AI_MODEL})...")

        # 2. Chuyển sang Model dự phòng nếu Model chính lỗi hoặc chưa có key
        if config.FALLBACK_AI_API_KEY:
            try:
                return self._analyze_text_fallback(text, prompt)
            except Exception as e2:
                print(f"Model dự phòng ({config.FALLBACK_AI_MODEL}) cũng gặp lỗi: {e2}")

        return {
            "intent": "CHAT",
            "transactions": [],
            "debt_items": [],
            "reply_message": "Xin lỗi, hiện tại không thể kết nối tới các dịch vụ AI để xử lý tin nhắn."
        }

    def _analyze_image_gemini(self, image_bytes: bytes, prompt_instruction: str, prompt: str) -> Dict[str, Any]:
        """Quét ảnh bằng Model chính (Google Gemini)."""
        if not self.client:
            self._init_client()
            if not self.client:
                raise Exception("Chưa cấu hình GEMINI_API_KEY.")

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
        return json.loads(result_text)

    def _analyze_image_fallback(self, image_bytes: bytes, prompt_instruction: str, prompt: str) -> Dict[str, Any]:
        """Quét ảnh bằng Model dự phòng (OpenRouter GPT-4o Vision)."""
        if not config.FALLBACK_AI_API_KEY:
            raise Exception("Chưa cấu hình FALLBACK_AI_API_KEY.")

        base64_img = base64.b64encode(image_bytes).decode('utf-8')
        image_url = f"data:image/jpeg;base64,{base64_img}"

        url = f"{config.FALLBACK_AI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.FALLBACK_AI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/SutieXuXi203/telegram_bot_wallet",
            "X-Title": "Telegram Wallet Bot"
        }
        payload = {
            "model": config.FALLBACK_AI_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_instruction},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        res = httpx.post(url, headers=headers, json=payload, timeout=40.0)
        if res.status_code != 200:
            raise Exception(f"Fallback Model trả về mã lỗi {res.status_code}: {res.text[:200]}")

        content = res.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def analyze_image(self, image_bytes: bytes, caption: Optional[str] = None) -> Dict[str, Any]:
        """Phân tích ảnh chụp hóa đơn / biên lai với cơ chế tự động chuyển đổi sang Model dự phòng."""
        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)
        prompt_instruction = "Đây là ảnh hóa đơn/biên lai. Hãy đọc hóa đơn và trích xuất các khoản chi tiêu."
        if caption:
            prompt_instruction += f"\nGhi chú kèm theo của người dùng: {caption}"

        # 1. Thử gọi Model chính (Google Gemini)
        if config.GEMINI_API_KEY:
            try:
                return self._analyze_image_gemini(image_bytes, prompt_instruction, prompt)
            except Exception as e:
                print(f"Model chính Gemini gặp sự cố đọc ảnh ({e}). Đang chuyển sang Model dự phòng ({config.FALLBACK_AI_MODEL})...")

        # 2. Chuyển sang Model dự phòng (GPT-4o Vision)
        if config.FALLBACK_AI_API_KEY:
            try:
                return self._analyze_image_fallback(image_bytes, prompt_instruction, prompt)
            except Exception as e2:
                print(f"Model dự phòng ({config.FALLBACK_AI_MODEL}) đọc ảnh gặp lỗi: {e2}")

        return {
            "intent": "CHAT",
            "transactions": [],
            "debt_items": [],
            "reply_message": "Không thể đọc thông tin từ ảnh do các dịch vụ AI tạm thời không khả dụng."
        }

ai_service = AIService()

