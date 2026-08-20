"""
Script thử nghiệm nhanh AI bóc tách chi tiêu từ câu văn tiếng Việt
Chạy: python test_ai_demo.py
"""
import os
import json
import config
from services.ai_service import ai_service

TEST_SENTENCES = [
    "Sáng nay ăn phở bò 45k, uống highland 55k",
    "Đổ xăng 70k và mua áo thun 250 cành",
    "Đi siêu thị hết 450.000đ, tiền điện tháng này 1.2tr",
    "Hôm nay nhận lương tháng 8 18 củ",
    "Tháng này tôi đã tiêu bao nhiêu tiền rồi?",
    "Hôm nay tiền ăn uống hết bao nhiêu?"
]

def main():
    print("=" * 60)
    print("🧪 KIỂM THỬ KHẢ NĂNG BÓC TÁCH TIẾNG VIỆT CỦA GEMINI AI")
    print("=" * 60)

    if not config.GEMINI_API_KEY:
        print("⚠️ Chưa có GEMINI_API_KEY trong file .env.")
        print("👉 Vui lòng thêm GEMINI_API_KEY vào .env để chạy thử nghiệm AI thực tế.")
        return

    for i, sentence in enumerate(TEST_SENTENCES, 1):
        print(f"\n[{i}] Câu nhập: \"{sentence}\"")
        result = ai_service.analyze_text(sentence)
        print("➡️ Kết quả AI trích xuất:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("-" * 50)

if __name__ == "__main__":
    main()
