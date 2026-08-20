# 🤖 Telegram AI Expense & Debt Tracker Bot

Bot Telegram thông minh ứng dụng **Google Gemini AI** giúp bạn ghi chép, theo dõi và phân tích chi tiêu cá nhân cũng như quản lý sổ nợ hoàn toàn tự động bằng ngôn ngữ tự nhiên tiếng Việt, đồng thời **lưu trữ và đồng bộ dữ liệu trực tiếp vào Google Sheets**.

---

## 🌟 Tính Năng Nổi Bật

- 💬 **Ghi chép tự nhiên**: Nhắn tin *"Ăn sáng phở bò 45k"* hoặc *"Cho Nam vay 500k"* -> AI tự bóc tách và phân loại vào đúng tab **Sổ Chi Tiêu** hoặc **Sổ Ghi Nợ**.
- 📌 **Chuyên biệt từng tab**:
  - **Sổ Chi Tiêu (6 cột)**: Tự động gom nhóm theo tháng, tính tổng thu chi và số dư.
  - **Sổ Ghi Nợ (8 cột)**: Tự động ghi nhận người vay/chủ nợ, trạng thái Nợ / Đã trả với định dạng màu sắc trực quan.
- 📸 **Quét hóa đơn qua ảnh**: Chụp ảnh hóa đơn gửi cho Bot, AI sẽ tự động bóc tách và lưu vào Sổ Chi Tiêu.
- 📊 **Báo cáo tài chính tháng (`/baocao`)**: Xem chi tiết thu chi và các khoản nợ phát sinh trong tháng.
- 📈 **Thống kê (`/thongke`)**: Nhận bảng thống kê chi tiêu tháng hiện tại.
- 🔗 **Google Sheets Cloud Sync**: Dữ liệu lưu an toàn trên Google Drive của bạn.

---

## 💬 Hướng Dẫn Sử Dụng Bot

### 1. Ghi chép chi tiêu:
- Dùng lệnh: `/chitieu <nội dung>` (vd: `/chitieu Ăn phở 45k`, `/ct Đổ xăng 50k`)
- Hoặc nhắn tự nhiên: `Ăn trưa 40k`, `Đi siêu thị 250k`, `Lương về 15tr`

### 2. Ghi chép vay nợ:
- Dùng lệnh: `/no <nội dung>` (vd: `/no Cho Nam vay 500k`, `/no Vay anh Tuấn 2tr`)
- Hoặc nhắn tự nhiên: `Cho Tuấn vay 200k`, `Nam trả nợ 500k`

### 3. Các lệnh điều khiển:
| Lệnh | Ý nghĩa |
| :--- | :--- |
| `/start` | Mở menu bàn phím và lời chào |
| `/chitieu` | Xem tổng hợp chi tiêu tháng hiện tại |
| `/no` | Xem danh sách các khoản nợ chưa trả |
| `/baocao` | Báo cáo chi tiết cả chi tiêu và sổ nợ trong tháng |
| `/baocao [tháng] [năm]` | Xem báo cáo tháng cụ thể (ví dụ: `/baocao 8 2026`) |
| `/thongke` | Thống kê số liệu chi tiêu trong tháng |
| `/homnay` | Xem danh sách các khoản chi trong ngày hôm nay |
| `/xem` | Xem danh sách các giao dịch gần nhất |
| `/xoa <Mã GD>` | Xóa dòng giao dịch trên Google Sheet |
| `/link` | Lấy đường link mở Google Sheet trên trình duyệt |

---

## 🚀 Hướng Dẫn Deploy 24/7 Trên Railway

1. Đăng nhập [railway.com](https://railway.com/) bằng GitHub.
2. Tạo New Project -> Chọn repo `SutieXuXi203/telegram_bot_wallet`.
3. Vào tab **Variables** -> Chuyển sang **RAW Editor** và dán:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
SPREADSHEET_ID_OR_NAME=your_spreadsheet_id
TIMEZONE=Asia/Ho_Chi_Minh
ALLOWED_USER_IDS=
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
```
4. Bấm Save để Railway tự động chạy bot 24/7!
