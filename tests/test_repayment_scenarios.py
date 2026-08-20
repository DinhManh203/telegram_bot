import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config
from services.sheets_service import sheets_service

def test_partial_and_full_by_person():
    print("=== TEST 1: TRẢ 1 PHẦN NỢ CỦA TRỊNH DŨNG (NỢ 122K, TRẢ 22K) ===")
    res_partial = sheets_service.mark_debt_as_paid(person="Trịnh Dũng", amount=22000, is_full=False)
    print("Kết quả trả 1 phần:", res_partial)
    
    vals = sheets_service.debt_worksheet.get_all_values()
    print("Row Trịnh Dũng sau trả 1 phần:", vals[2])
    assert int(vals[2][4].replace(".", "")) == 100000, f"Expected 100.000, got {vals[2][4]}"
    assert vals[2][7] == "Nợ", f"Expected Nợ, got {vals[2][7]}"

    print("\n=== TEST 2: TRẢ HẾT PHẦN CÒN LẠI CỦA TRỊNH DŨNG (100K) ===")
    res_full = sheets_service.mark_debt_as_paid(person="Trịnh Dũng", is_full=True)
    print("Kết quả trả hết:", res_full)

    vals = sheets_service.debt_worksheet.get_all_values()
    print("Row Trịnh Dũng sau trả hết:", vals[2])
    assert int(vals[2][4]) == 0, f"Expected 0, got {vals[2][4]}"
    assert vals[2][7] == "Đã trả", f"Expected Đã trả, got {vals[2][7]}"

    print("\n=== KHÔI PHỤC LẠI DỮ LIỆU NỢ BAN ĐẦU CHO TRỊNH DŨNG (122K, NỢ) ĐỂ USER THEO DÕI ===")
    sheets_service.debt_worksheet.update_cell(3, 5, 122000)
    sheets_service.debt_worksheet.update_cell(3, 8, "Nợ")
    print("Đã khôi phục dòng Trịnh Dũng thành 122k, Nợ.")

    vals_final = sheets_service.debt_worksheet.get_all_values()
    print("\n=== BẢNG SỔ GHI NỢ CUỐI CÙNG ===")
    for idx, r in enumerate(vals_final, start=1):
        print(f"Row {idx}: {r}")

if __name__ == "__main__":
    test_partial_and_full_by_person()
