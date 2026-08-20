import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config
from services.sheets_service import sheets_service

def main():
    print("=== DỮ LIỆU BAN ĐẦU ===")
    vals = sheets_service.debt_worksheet.get_all_values()
    for idx, r in enumerate(vals, start=1):
        print(f"Row {idx}: {r}")

    # Xóa dòng rác NO260820CA4B nếu có
    for idx, r in enumerate(vals, start=1):
        if len(r) > 0 and r[0].strip().upper() == "NO260820CA4B":
            print(f"\n=> Xóa dòng rác tạo sai NO260820CA4B tại Row {idx}...")
            sheets_service.debt_worksheet.delete_rows(idx)
            break

    print("\n=== THỬ NGHIỆM TRẢ NỢ BẰNG MÃ GD (NO260820F66D) ===")
    res = sheets_service.mark_debt_as_paid(debt_id="NO260820F66D", is_full=True)
    print("Kết quả cập nhật:", res)

    print("\n=== DỮ LIỆU SAU KHI CẬP NHẬT ===")
    vals = sheets_service.debt_worksheet.get_all_values()
    for idx, r in enumerate(vals, start=1):
        print(f"Row {idx}: {r}")

if __name__ == "__main__":
    main()
