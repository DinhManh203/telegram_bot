import json
import io
import re
import time
import asyncio
import inspect
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable, Set
from PIL import Image
from google import genai
from google.genai import types
import config

SYSTEM_PROMPT = """
Bạn là Gấu Trắng trợ lý - Quản lý tài chính, chi tiêu và theo dõi công nợ cá nhân bằng tiếng Việt cho người dùng Telegram.
Nhiệm vụ của bạn là phân tích tin nhắn của người dùng (hoặc hình ảnh hóa đơn) và trả về kết quả dưới định dạng JSON có cấu trúc chuẩn xác.

Thời gian hệ thống hiện tại: {current_time}

QUY TẮC PHÂN LOẠI Ý ĐỊNH (INTENT):
1. "intent": "PAY_DEBT" -> KHI NGƯỜI DÙNG BÁO TRẢ NỢ, HOÀN THÀNH TRẢ NỢ, ĐÃ TRẢ, THANH TOÁN NỢ HOẶC THU HỒI NỢ:
   - Tất cả các câu có hành vi TRẢ TIỀN NỢ / THANH TOÁN NỢ:
     + "Tuấn Anh trả 500k", "Tuấn Anh trả nợ 500k", "Tuấn Anh trả nợ nhé", "Tuấn Anh trả tiền", "Tuấn Anh đã trả"
     + "Tuấn Anh trả xong nợ rồi", "Tuấn Anh hoàn thành trả nợ", "Tuấn Anh đã thanh toán"
     + "Nam trả 200k", "Nam trả hết nợ rồi", "Đã thu nợ anh Hùng", "Tôi đã trả nợ Tuấn", "Trịnh Dũng đã trả"
     + "Đã hoàn thành trả nợ", "Mã NO260820ABB2 đã trả", "Thanh toán nợ mã NO260820F66D"
   - QUY TẮC BẮT BUỘC:
     + Tuyệt đối để "debt_items": [] (mảng rỗng), KHÔNG ĐƯỢC sinh ra debt_items khi người dùng báo trả nợ!
     + "debt_id": Mã giao dịch nếu có xuất hiện trong tin nhắn (ví dụ: "NO260820ABB2", "NO260820F66D", nếu không có thì null)
     + "person": Tên người nợ / người trả liên quan (ví dụ: "Tuấn Anh", "Trịnh Dũng", "Nam", nếu không có thì null)
     + "amount": Số tiền trả nếu có nói rõ (ví dụ: "Tuấn Anh trả 500k" -> 500000, "Nam trả 200k" -> 200000). Nếu trả hết hoặc không nói số tiền thì để null.
     + "is_full_payment": true nếu là trả hết / hoàn thành trả nợ (hoặc không nói số tiền cụ thể), false nếu nói rõ chỉ trả 1 phần nợ nhỏ hơn.

2. "intent": "ADD_DEBT" -> KHI GHI KHOẢN NỢ MỚI / CHO VAY MỚI / VAY MƯỢN MỚI:
   - Chỉ dùng khi có từ: "vay", "mượn", "nợ", "cho vay", "cho mượn" (ví dụ: "Cho Nam vay 500k", "Nam mượn 200k", "Vay Tuấn 1 triệu", "Mượn mẹ 2 củ", "Trịnh Dũng nợ 122k")
   - QUY TẮC BẮT BUỘC: TUYỆT ĐỐI KHÔNG dùng ADD_DEBT cho các câu có từ "trả", "thanh toán", "thu nợ", "hoàn thành"!
   => Khi là ADD_DEBT, trích xuất mảng "debt_items":
      - "person": Tên người vay / người cho vay (ví dụ: "Doãn Tuấn Anh", "Trịnh Dũng", "Nam", "Tuấn")
      - "debt_type": Một trong các loại: "Cho vay" | "Vay nợ"
      - "amount": Số tiền nguyên dương (VNĐ)
      - "debt_date": Ngày nợ nếu có (ví dụ: "15/08/2026"). Nếu không có thì BẮT BUỘC ĐỂ TRỐNG "" (chuỗi rỗng)!
      - "status": "Nợ"
      - "note": Ghi chú lý do nếu có nói rõ. Nếu không có thì để trống "".
      - "date": "{current_time}"

3. "intent": "QUERY_DEBT" -> KHI HỎI VỀ SỔ NỢ HOẶC XÁC NHẬN TÌNH TRẠNG NỢ HIỆN TẠI:
   - "Có những ai đang nợ tôi?", "Ai đang nợ tôi trong tháng này?", "Tôi đang nợ những ai?", "Xem sổ nợ", "Kiểm tra nợ", "Sổ ghi nợ", "Danh sách nợ"
   - "Tuấn Anh vẫn đang nợ 500k nhé", "Tuấn Anh còn nợ bao nhiêu?", "Trịnh Dũng còn nợ không?", "Kiểm tra nợ Tuấn Anh"
   => Trích xuất:
      - "person": Tên riêng cụ thể của người cần tra cứu (ví dụ: "Tuấn Anh", "Trịnh Dũng"). 
      - LƯU Ý QUAN TRỌNG: Tuyệt đối KHÔNG lấy "tôi", "ai", "những ai", "người nào" làm person. Nếu là câu hỏi chung ("ai nợ tôi", "có những ai đang nợ...") thì BẮT BUỘC để "person": null!

4. "intent": "DELETE" -> KHI NGƯỜI DÙNG YÊU CẦU XÓA GIAO DỊCH / XÓA KHOẢN NỢ THEO MÃ GD:
   - "xóa mã NO260820F66D", "xóa 2 NO260820F66D NO260820ABB2 này", "xóa giao dịch TX2608201234", "hủy mã NO...", "xóa NO260820F66D"
   => Trích xuất:
      - "delete_ids": Mảng các mã GD cần xóa, ví dụ: ["NO260820F66D", "NO260820ABB2"]

5. "intent": "ADD_TRANSACTION" -> KHI NGƯỜI DÙNG GHI NHẬN CHI TIÊU / THU NHẬP THÔNG THƯỜNG:
   - "Ăn phở 45k", "Đổ xăng 50k", "Mua áo 250k", "Lương về 15tr"
   => Trích xuất mảng "transactions" với các trường:
      - "amount": Số tiền nguyên dương (VNĐ)
      - "type": "Chi tiêu" hoặc "Thu nhập"
      - "category": "Ăn uống" | "Đi lại" | "Mua sắm" | "Hóa đơn" | "Giải trí" | "Sức khỏe" | "Giáo dục" | "Gia đình" | "Thu nhập" | "Khác"
      - "note": Mô tả ngắn gọn
      - "date": "{current_time}"

6. "intent": "QUERY_STATS" -> KHI HỎI VỀ THỐNG KÊ CHI TIÊU:
   - "Tháng này tiêu bao nhiêu rồi?", "Hôm nay ăn uống hết bao nhiêu?", "Báo cáo tháng này"

7. "intent": "CHAT" -> Lời chào hỏi hoặc trò chuyện thông thường.

QUY ĐỔI TIỀN TỆ TIẾNG VIỆT:
- "k", "cành", "nghìn", "ngàn" -> * 1.000 (vd: 50k = 50000, 30 cành = 30000)
- "lốp", "lít" -> * 100.000 (vd: 2 lốp = 200000)
- "củ", "triệu", "tr", "m" -> * 1.000.000 (vd: 1.5tr = 1500000, 2 củ = 2000000)

ĐỊNH DẠNG JSON TRẢ VỀ:
{{
  "intent": "ADD_DEBT" | "PAY_DEBT" | "QUERY_DEBT" | "DELETE" | "ADD_TRANSACTION" | "QUERY_STATS" | "CHAT",
  "debt_id": null,
  "delete_ids": [],
  "person": null,
  "amount": null,
  "is_full_payment": true,
  "debt_items": [],
  "transactions": [],
  "query_info": {{
    "scope": "this_month",
    "category": null,
    "month": 8,
    "year": 2026
  }},
  "reply_message": "..."
}}
"""

def _extract_json(raw_text: str) -> Dict[str, Any]:
    """Trích xuất và phân tích JSON an toàn từ phản hồi của các model AI."""
    cleaned = raw_text.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start:end+1])

    raise Exception("Không thể trích xuất JSON hợp lệ từ phản hồi AI.")

def parse_reset_time_info(error_text: str) -> Tuple[str, float]:
    """
    Trích xuất chuỗi hiển thị thời gian reset và số giây cooldown từ lỗi của Google Gemini API.
    Ví dụ: 'Please retry in 15h55m54.801153382s' -> ('15h55m55s', 57355.0)
    """
    m_delay = re.search(r"retryDelay['\":\s]+(\d+)s?", error_text, re.IGNORECASE)
    if m_delay:
        sec = int(m_delay.group(1))
        cooldown = float(sec)
        if sec >= 3600:
            h = sec // 3600
            m_rem = (sec % 3600) // 60
            disp = f"{h}h{m_rem:02d}m" if m_rem else f"{h}h"
        elif sec >= 60:
            m = sec // 60
            s_rem = sec % 60
            disp = f"{m}m{s_rem:02d}s" if s_rem else f"{m}m"
        else:
            disp = f"{sec}s"
        return disp, cooldown

    m_text = re.search(
        r"(?:retry\s+(?:in|after)|try again in)\s+([0-9a-zA-Z\.\s]+?)(?=[,\n;]|\.\s|\.$|$|details)",
        error_text,
        re.IGNORECASE
    )
    if m_text:
        raw_val = m_text.group(1).strip()
        def clean_decimal(match):
            val = float(match.group(1) + "." + match.group(2))
            unit = match.group(3) or ""
            return f"{round(val)}{unit}"
        clean_val = re.sub(r"(\d+)\.(\d+)([a-zA-Z]*)", clean_decimal, raw_val).strip()

        hours = 0
        mins = 0
        secs = 0
        h_m = re.search(r"(\d+)\s*(?:h|hour|hours)", clean_val, re.IGNORECASE)
        m_m = re.search(r"(\d+)\s*(?:m|min|minute|minutes)", clean_val, re.IGNORECASE)
        s_m = re.search(r"(\d+)\s*(?:s|sec|second|seconds)", clean_val, re.IGNORECASE)
        if h_m:
            hours = int(h_m.group(1))
        if m_m:
            mins = int(m_m.group(1))
        if s_m:
            secs = int(s_m.group(1))

        calc_sec = hours * 3600 + mins * 60 + secs
        if calc_sec > 0:
            if "minute" in clean_val.lower():
                disp = clean_val.replace("minutes", "phút").replace("minute", "phút")
            elif "second" in clean_val.lower():
                disp = clean_val.replace("seconds", "s").replace("second", "s")
            else:
                disp = clean_val
            return disp, float(calc_sec)
        elif clean_val:
            return clean_val, 60.0

    m_reset = re.search(
        r"(?:resets? in)\s+([0-9a-zA-Z\.\s]+?)(?=[,\n;]|\.\s|\.$|$|details)",
        error_text,
        re.IGNORECASE
    )
    if m_reset:
        raw_val = m_reset.group(1).strip()
        clean_val = re.sub(
            r"(\d+)\.(\d+)([a-zA-Z]*)",
            lambda m: f"{round(float(m.group(1) + '.' + m.group(2)))}{m.group(3) or ''}",
            raw_val
        ).strip()
        if clean_val:
            return clean_val, 60.0

    return "vài phút", 60.0

def is_quota_limit_error(err: Exception) -> bool:
    """Kiểm tra xem lỗi có phải do chạm hạn mức (Rate limit/Quota/High demand) hay không."""
    err_str = str(err).lower()
    code = getattr(err, "code", None)
    if code in (429, 503):
        return True
    keywords = [
        "429", "503", "resource_exhausted", "quota", "rate limit",
        "too many requests", "high demand", "unavailable", "temporarily overloaded",
        "requests per minute", "requests per day", "tokens per minute", "tokens per day",
        "free tier"
    ]
    return any(kw in err_str for kw in keywords)

def is_discontinued_error(err: Exception) -> bool:
    """Kiểm tra model đã bị ngừng hỗ trợ hoặc không tồn tại (404 Not Found)."""
    err_str = str(err).lower()
    code = getattr(err, "code", None)
    if code == 404:
        return True
    return "404" in err_str or "not_found" in err_str or "is not found for api version" in err_str or "no longer available" in err_str

MODEL_SPECS_METADATA = {
    "gemini-2.5-flash": {
        "category": "Dòng Flash Thế hệ 2.5 (Mặc định)",
        "desc": "Tốc độ cao, tối ưu chuẩn tiếng Việt và bóc tách hóa đơn",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-2.5-flash-lite": {
        "category": "Dòng Flash Lite (Tiết kiệm Quota)",
        "desc": "Bản Flash siêu nhẹ của đời 2.5, phản hồi gần như tức thì",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-3.5-flash": {
        "category": "Thế hệ 3.5 Mới nhất",
        "desc": "Hiệu năng xử lý ngữ cảnh tiếng Việt đột phá",
        "rpd_limit": 1000,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-3.5-flash-lite": {
        "category": "Bản rút gọn Thế hệ 3.5",
        "desc": "Bản rút gọn hiệu năng cao của Gemini 3.5, tối ưu quota",
        "rpd_limit": 1000,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-3.8-flash": {
        "category": "Thế hệ 3.8 Thử nghiệm",
        "desc": "Phiên bản 3.8 của Google AI Studio, thông minh vượt trội",
        "rpd_limit": 500,
        "rpm_limit": 10,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-3.7-flash": {
        "category": "Thế hệ 3.7 Cân bằng",
        "desc": "Cân bằng tốc độ và khả năng đọc hóa đơn",
        "rpd_limit": 500,
        "rpm_limit": 10,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-2.5-pro": {
        "category": "Dòng Pro Suy luận sâu",
        "desc": "Dòng Pro cao cấp, suy luận sâu sắc cho bài toán phức tạp",
        "rpd_limit": 50,
        "rpm_limit": 2,
        "tpm_limit": "32,000",
        "requires_billing": False
    },
    "gemini-flash-latest": {
        "category": "Alias Flash Mới nhất",
        "desc": "Bí danh trỏ về bản Flash mới nhất của Google",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-pro-latest": {
        "category": "Alias Pro Mới nhất",
        "desc": "Bí danh trỏ về bản Pro cao cấp nhất của Google",
        "rpd_limit": 50,
        "rpm_limit": 2,
        "tpm_limit": "32,000",
        "requires_billing": False
    },
    "gemini-2.0-flash": {
        "category": "Thế hệ 2.0 Kinh điển",
        "desc": "Thế hệ 2.0 kinh điển cho API truyền thống",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-2.0-flash-lite": {
        "category": "Thế hệ 2.0 Rút gọn",
        "desc": "Bản rút gọn thế hệ 2.0",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-1.5-flash": {
        "category": "Thế hệ 1.5 Tiêu chuẩn",
        "desc": "Thế hệ 1.5 ban đầu, hạn mức độc lập",
        "rpd_limit": 1500,
        "rpm_limit": 15,
        "tpm_limit": "1,000,000",
        "requires_billing": False
    },
    "gemini-1.5-pro": {
        "category": "Thế hệ 1.5 Pro",
        "desc": "Thế hệ 1.5 Pro, khả năng phân tích ngữ cảnh lớn",
        "rpd_limit": 50,
        "rpm_limit": 2,
        "tpm_limit": "32,000",
        "requires_billing": False
    }
}

class AIService:
    def __init__(self):
        self.client: Optional[genai.Client] = None
        self.models: List[str] = list(config.GEMINI_MODELS)
        self.current_model: str = self.models[0] if self.models else "gemini-2.5-flash"
        self.model_cooldowns: Dict[str, float] = {}
        self.model_reasons: Dict[str, str] = {}
        self.model_requests: Dict[str, int] = {}
        self.total_requests: int = 0
        self.system_prompt: str = SYSTEM_PROMPT
        self.discontinued_models: Set[str] = set()
        self.is_online: bool = True
        self._init_client()

    def toggle_online(self) -> bool:
        """Bật/tắt trạng thái hoạt động của Bot từ Web Console."""
        self.is_online = not self.is_online
        return self.is_online

    def _init_client(self):
        """Khởi tạo Gemini Client."""
        if not config.GEMINI_API_KEY:
            print("Cảnh báo: GEMINI_API_KEY chưa được thiết lập.")
            return

        try:
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        except Exception as e:
            print(f"Lỗi khởi tạo Gemini Client: {e}")

    def get_candidate_models(self) -> List[str]:
        """Lấy danh sách các model Gemini ưu tiên để thử gọi."""
        now = time.time()
        valid_models = [m for m in self.models if m not in self.discontinued_models]
        if not valid_models:
            valid_models = list(self.models)

        ready_models = [m for m in valid_models if self.model_cooldowns.get(m, 0) <= now]
        cooldown_models = [m for m in valid_models if self.model_cooldowns.get(m, 0) > now]
        cooldown_models.sort(key=lambda m: self.model_cooldowns.get(m, 0))

        if self.current_model in ready_models:
            ready_models.remove(self.current_model)
            ready_models.insert(0, self.current_model)

        return ready_models + cooldown_models

    def _trigger_switch_notice(
        self,
        current_model: str,
        reset_str: str,
        next_model: str,
        on_model_switch: Optional[Callable[[str], Any]]
    ) -> str:
        """Tạo thông báo chuyển model và kích hoạt callback gửi tin nhắn tới Telegram."""
        notice = f"⚠️ Model `{current_model}` đã tới giới hạn (còn {reset_str} reset) chuyển qua model `{next_model}`"
        print(f"[AIService] {notice}")

        if on_model_switch:
            try:
                res = on_model_switch(notice)
                if inspect.isawaitable(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as cb_err:
                print(f"[AIService] Lỗi callback chuyển model: {cb_err}")

        return notice

    def analyze_text(
        self,
        text: str,
        on_model_switch: Optional[Callable[[str], Any]] = None
    ) -> Dict[str, Any]:
        """Phân tích tin nhắn văn bản với cơ chế tự động chuyển model Gemini khi chạm giới hạn."""
        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)

        if not config.GEMINI_API_KEY:
            return {
                "intent": "CHAT",
                "transactions": [],
                "debt_items": [],
                "reply_message": "Chưa cấu hình GEMINI_API_KEY trong file .env."
            }

        if not self.client:
            self._init_client()
            if not self.client:
                return {
                    "intent": "CHAT",
                    "transactions": [],
                    "debt_items": [],
                    "reply_message": "Không thể kết nối tới Google Gemini Client."
                }

        candidates = self.get_candidate_models()
        notices: List[str] = []

        for idx, model_name in enumerate(candidates):
            now = time.time()
            if self.model_cooldowns.get(model_name, 0) > now and idx < len(candidates) - 1:
                continue

            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=f"Phân tích tin nhắn sau:\n{text}")]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=prompt,
                        response_mime_type="application/json",
                        temperature=0.1,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                    )
                )
                result_text = response.text.strip()
                result_json = _extract_json(result_text)
                self.current_model = model_name
                result_json["active_model"] = model_name
                result_json["model_switch_notices"] = notices
                return result_json

            except Exception as e:
                err_str = str(e)
                print(f"[AIService] Model {model_name} gặp lỗi: {err_str[:120]}")

                if is_discontinued_error(e):
                    self.discontinued_models.add(model_name)
                    continue

                if is_quota_limit_error(e):
                    reset_disp, cooldown_sec = parse_reset_time_info(err_str)
                    self.model_cooldowns[model_name] = time.time() + cooldown_sec

                    next_models = [m for m in candidates[idx + 1:] if m not in self.discontinued_models]
                    if not next_models:
                        next_models = [m for m in self.models if m != model_name and m not in self.discontinued_models]

                    next_model_name = next_models[0] if next_models else "dự phòng tiếp theo"
                    notice = self._trigger_switch_notice(
                        current_model=model_name,
                        reset_str=reset_disp,
                        next_model=next_model_name,
                        on_model_switch=on_model_switch
                    )
                    notices.append(notice)
                    continue

                continue

        return {
            "intent": "CHAT",
            "transactions": [],
            "debt_items": [],
            "reply_message": "Tất cả các model AI hiện tại đều đang đạt giới hạn hạn mức hoặc tạm thời không khả dụng. Vui lòng thử lại sau!",
            "model_switch_notices": notices
        }

    def analyze_image(
        self,
        image_bytes: bytes,
        caption: Optional[str] = None,
        on_model_switch: Optional[Callable[[str], Any]] = None
    ) -> Dict[str, Any]:
        """Phân tích ảnh hóa đơn/biên lai với cơ chế tự động chuyển model Gemini khi chạm giới hạn."""
        now_str = datetime.now(config.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        prompt = SYSTEM_PROMPT.format(current_time=now_str)
        prompt_instruction = "Đây là ảnh hóa đơn/biên lai. Hãy đọc hóa đơn và trích xuất các khoản chi tiêu."
        if caption:
            prompt_instruction += f"\nGhi chú kèm theo của người dùng: {caption}"

        if not config.GEMINI_API_KEY:
            return {
                "intent": "CHAT",
                "transactions": [],
                "debt_items": [],
                "reply_message": "Chưa cấu hình GEMINI_API_KEY trong file .env."
            }

        if not self.client:
            self._init_client()
            if not self.client:
                return {
                    "intent": "CHAT",
                    "transactions": [],
                    "debt_items": [],
                    "reply_message": "Không thể kết nối tới Google Gemini Client."
                }

        candidates = self.get_candidate_models()
        notices: List[str] = []

        for idx, model_name in enumerate(candidates):
            now = time.time()
            if self.model_cooldowns.get(model_name, 0) > now and idx < len(candidates) - 1:
                continue

            try:
                response = self.client.models.generate_content(
                    model=model_name,
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
                        temperature=0.1,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                    )
                )
                result_text = response.text.strip()
                result_json = _extract_json(result_text)
                self.current_model = model_name
                result_json["active_model"] = model_name
                result_json["model_switch_notices"] = notices
                return result_json

            except Exception as e:
                err_str = str(e)
                print(f"[AIService] Model {model_name} đọc ảnh thất bại: {err_str[:120]}")

                if is_discontinued_error(e):
                    self.discontinued_models.add(model_name)
                    continue

                if is_quota_limit_error(e):
                    reset_disp, cooldown_sec = parse_reset_time_info(err_str)
                    self.model_cooldowns[model_name] = time.time() + cooldown_sec

                    next_models = [m for m in candidates[idx + 1:] if m not in self.discontinued_models]
                    if not next_models:
                        next_models = [m for m in self.models if m != model_name and m not in self.discontinued_models]

                    next_model_name = next_models[0] if next_models else "dự phòng tiếp theo"
                    notice = self._trigger_switch_notice(
                        current_model=model_name,
                        reset_str=reset_disp,
                        next_model=next_model_name,
                        on_model_switch=on_model_switch
                    )
                    notices.append(notice)
                    continue

                continue

        return {
            "intent": "CHAT",
            "transactions": [],
            "debt_items": [],
            "reply_message": "Không thể đọc thông tin từ ảnh do tất cả các model AI đều đang đạt hạn mức hoặc không khả dụng.",
            "model_switch_notices": notices
        }

    def test_model(self, model_name: str) -> Dict[str, Any]:
        """Thử nghiệm nhanh gọi 1 model để kiểm tra hạn mức."""
        if not self.client:
            self._init_client()
        if not self.client:
            return {"status": "FAIL", "model": model_name, "duration": 0, "reason": "Chưa có GEMINI_API_KEY"}

        start = time.time()
        try:
            resp = self.client.models.generate_content(
                model=model_name,
                contents="Ping",
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
            )
            duration = round(time.time() - start, 2)
            self.model_cooldowns.pop(model_name, None)
            self.model_reasons.pop(model_name, None)
            return {"status": "OK", "model": model_name, "duration": duration, "message": "Hoạt động tốt"}
        except Exception as e:
            duration = round(time.time() - start, 2)
            err_str = str(e)
            if is_quota_limit_error(e):
                reset_disp, cooldown_sec = parse_reset_time_info(err_str)
                self.model_cooldowns[model_name] = time.time() + cooldown_sec
                self.model_reasons[model_name] = f"Hết limit ({reset_disp})"
                return {"status": "FAIL", "model": model_name, "duration": duration, "reason": f"Hết limit ({reset_disp})"}
            elif is_discontinued_error(e):
                self.discontinued_models.add(model_name)
                return {"status": "FAIL", "model": model_name, "duration": duration, "reason": "404 Not Found"}
            return {"status": "FAIL", "model": model_name, "duration": duration, "reason": err_str[:80]}

    def get_status_dict(self) -> Dict[str, Any]:
        """Tổng hợp toàn bộ thông tin trạng thái theo định dạng Console Dashboard."""
        now = time.time()
        primary_model = self.models[0] if self.models else "gemini-2.5-flash"
        models_data = []
        ready_count = 0
        exhausted_count = 0

        for m in self.models:
            meta = MODEL_SPECS_METADATA.get(m, {
                "category": "Google Gemini",
                "desc": "Mô hình ngôn ngữ đa phương thức của Google",
                "rpd_limit": 1500,
                "rpm_limit": 15,
                "tpm_limit": "1,000,000",
                "requires_billing": False
            })

            cooldown_until = self.model_cooldowns.get(m, 0)
            is_cooldown = cooldown_until > now
            rem_sec = max(0, int(cooldown_until - now)) if is_cooldown else 0

            if rem_sec >= 3600:
                h = rem_sec // 3600
                m_rem = (rem_sec % 3600) // 60
                rem_fmt = f"{h}h {m_rem:02d}m" if m_rem else f"{h}h"
            elif rem_sec >= 60:
                m_val = rem_sec // 60
                s_val = rem_sec % 60
                rem_fmt = f"{m_val}m {s_val:02d}s" if s_val else f"{m_val}m"
            elif rem_sec > 0:
                rem_fmt = f"{rem_sec}s"
            else:
                rem_fmt = "0s"

            if is_cooldown:
                exhausted_count += 1
            else:
                ready_count += 1

            rpd_used = self.model_requests.get(m, 0)
            rpd_limit = meta.get("rpd_limit", 1500)
            percent = round((rpd_used / rpd_limit) * 100, 1) if rpd_limit > 0 else 0

            models_data.append({
                "name": m,
                "is_active": (m == self.current_model),
                "is_primary": (m == primary_model),
                "is_cooldown": is_cooldown,
                "expiry_timestamp": cooldown_until if is_cooldown else 0,
                "remaining_formatted": rem_fmt,
                "reason": self.model_reasons.get(m, ""),
                "quota": {
                    "category": meta.get("category", ""),
                    "desc": meta.get("desc", ""),
                    "rpd_used": rpd_used,
                    "rpd_limit": rpd_limit,
                    "rpm_used": 0,
                    "rpm_limit": meta.get("rpm_limit", 15),
                    "tpm_limit": meta.get("tpm_limit", "1,000,000"),
                    "quota_percent": percent,
                    "requires_billing": meta.get("requires_billing", False)
                }
            })

        return {
            "bot": {
                "online": self.is_online,
                "name": "Gấu Trắng",
                "username": "polarbear_wallet_bot",
                "id": "8807144463",
                "latency_ms": 15,
                "guilds_count": 1,
                "guilds_summary": "Sổ Chi Tiêu Google Sheets",
                "guilds": [
                    {
                        "id": config.SPREADSHEET_ID_OR_NAME[:18] if config.SPREADSHEET_ID_OR_NAME else "telegram_bot",
                        "name": "Sổ Chi Tiêu & Công Nợ Cá Nhân",
                        "member_count": 1,
                        "is_admin": True,
                        "has_specific_channel": "Sổ Thu Chi",
                        "icon": None
                    }
                ]
            },
            "quota": {
                "current_active": self.current_model,
                "primary": primary_model,
                "total_daily_requests": self.total_requests,
                "ready_count": ready_count,
                "exhausted_count": exhausted_count,
                "models": models_data
            },
            "settings": {
                "specific_channel": config.ALLOWED_USER_IDS_RAW,
                "spreadsheet_id": config.SPREADSHEET_ID_OR_NAME,
                "timezone": config.TIMEZONE_STR
            },
            "prompt": self.system_prompt
        }

ai_service = AIService()
