import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config
from services.sheets_service import sheets_service
from services.ai_service import ai_service
import json

def test_ai_parsing():
    print("=" * 60)
    print("1. KIỂM THỬ AI TRÍCH XUẤT INTENT TRẢ NỢ")
    print("=" * 60)
    test_cases = [
        "Tuấn Anh đã trả nợ nhé",
        "Tuấn Anh trả xong nợ mã NO260820F66D",
        "Đã hoàn thành trả nợ mã NO2608202215",
        "Trịnh Dũng trả 50k",
        "Cho Nam vay 500k"
    ]
    for tc in test_cases:
        print(f"\n[Test case]: '{tc}'")
        try:
            res = ai_service.analyze_text(tc)
            print(f"-> Intent: {res.get('intent')}, debt_id: {res.get('debt_id')}, person: {res.get('person')}, amount: {res.get('amount')}, is_full: {res.get('is_full_payment')}")
        except Exception as e:
            print(f"-> Error: {e}")

def test_sheet_clean_and_update():
    print("\n" + "=" * 60)
    print("2. KIỂM TRA VÀ DỌN DẸP TAB SỔ GHI NỢ")
    print("=" * 60)
    
    vals = sheets_service.debt_worksheet.get_all_values()
    print("Dữ liệu hiện tại:")
    for idx, r in enumerate(vals, start=1):
        print(f"Row {idx}: {r}")

    # Xóa dòng NO260820CA4B (dòng rác tạo sai trước đó) nếu còn tồn tại
    for idx, r in enumerate(vals, start=1):
        if len(r) > 0 and r[0].strip().upper() == "NO260820CA4B":
            print(f"Đang xóa dòng rác bị tạo sai: Row {idx} ({r[0]})...")
            sheets_service.debt_worksheet.delete_rows(idx)
            print("Đã xóa xong dòng rác!")
            break

if __name__ == "__main__":
    test_sheet_clean_and_update()
    test_ai_parsing()
