# 🤖 Telegram AI Expense Tracker Bot (Quản Lý Chi Tiêu Cá Nhân Bằng AI & Google Sheets)

Bot Telegram thông minh ứng dụng **Google Gemini AI** giúp bạn ghi chép, theo dõi và phân tích chi tiêu cá nhân trong tháng hoàn toàn tự động bằng ngôn ngữ tự nhiên tiếng Việt, đồng thời **lưu trữ và đồng bộ dữ liệu trực tiếp vào Google Sheets**.

---

## 🌟 Tính Năng Nổi Bật

- 💬 **Ghi chép tự nhiên**: Chỉ cần nhắn *"Ăn sáng phở bò 45k, cafe 35k"* hoặc *"Lương về 20 củ"* -> AI tự bóc tách số tiền, phân loại danh mục (Ăn uống, Đi lại, Mua sắm, Hóa đơn...) và thêm vào Google Sheet.
- 📸 **Quét hóa đơn qua ảnh**: Chụp ảnh hóa đơn hoặc biên lai chuyển khoản gửi cho Bot, AI sẽ tự động đọc tổng tiền và lưu lại.
- 📊 **Báo cáo chi tiêu tháng**: Xem tổng thu nhập, tổng chi tiêu, số dư và tỉ lệ phần trăm từng nhóm chi tiêu trong tháng hiện tại hoặc tháng bất kỳ (`/baocao`).
- 📈 **Biểu đồ tròn trực quan (Pie Chart)**: Bot tự động vẽ biểu đồ phân bổ chi tiêu và gửi ảnh trực tiếp trong Telegram (`/thongke`).
- 🔗 **Google Sheets Cloud Sync**: Dữ liệu lưu an toàn trên Google Drive của bạn, mở xem và chỉnh sửa trên điện thoại hoặc máy tính mọi lúc mọi nơi.
- 🗑 **Quản lý & Xóa giao dịch**: Xem danh sách giao dịch gần nhất (`/xem`) và xóa dòng nhập nhầm (`/xoa <Mã GD>`).

---

## 📋 Hướng Dẫn Cài Đặt Chi Tiết

### 1. Chuẩn bị môi trường
Cài đặt các thư viện cần thiết:
```bash
pip install -r requirements.txt
```

---

### 2. Lấy Telegram Bot Token (1 phút)
1. Mở Telegram, tìm kiếm bot **`@BotFather`**.
2. Gõ lệnh `/newbot`.
3. Đặt tên hiển thị cho Bot và `username` (kết thúc bằng đuôi `bot`, ví dụ: `my_expense_ai_bot`).
4. `@BotFather` sẽ gửi cho bạn một đoạn mã **HTTP API Token** (Ví dụ: `7123456789:AAFxxx...`).
5. Sao chép Token này để điền vào `.env`.

---

### 3. Lấy Google Gemini API Key Miễn Phí (1 phút)
1. Truy cập: [https://aistudio.google.com/](https://aistudio.google.com/) (đăng nhập bằng tài khoản Google).
2. Bấm nút **"Get API key"** -> **"Create API key"**.
3. Sao chép mã API Key được cấp.

---

### 4. Thiết lập Google Sheets API & Service Account (2 phút)

Để Bot có quyền ghi dữ liệu vào Google Sheet của bạn:

1. **Tạo Service Account trên Google Cloud:**
   - Truy cập [Google Cloud Console](https://console.cloud.google.com/).
   - Tạo một dự án mới (ví dụ: `Expense Bot`).
   - Vào mục **APIs & Services** > **Library**, tìm kiếm và **Enable** 2 API sau:
     + **Google Sheets API**
     + **Google Drive API**
   - Vào mục **APIs & Services** > **Credentials** > Bấm **Create Credentials** > Chọn **Service Account**.
   - Đặt tên (ví dụ: `bot-sheets`) > Bấm **Done**.
   - Bấm vào Service Account vừa tạo, chuyển sang tab **Keys** > Bấm **Add Key** > **Create new key** > Chọn **JSON** > Bấm **Create**.
   - Một file JSON sẽ được tải về máy tính của bạn. Hãy đổi tên file đó thành **`credentials.json`** và đặt vào thư mục dự án `telegram-bot/`.

2. **Tạo Google Sheet và Chia Sẻ Quyền Cho Bot:**
   - Tạo một bảng tính Google Sheet mới tại [sheets.google.com](https://sheets.google.com) (đặt tên ví dụ: `Chi Tieu Ca Nhan`).
   - Mở file `credentials.json` vừa tải về, copy địa chỉ email ở trường `"client_email"` (có dạng: `bot-sheets@ten-du-an.iam.gserviceaccount.com`).
   - Bấm nút **Chia sẻ (Share)** trên Google Sheet của bạn -> Dán email của Service Account vào -> Chọn quyền **Người chỉnh sửa (Editor)** -> Bấm **Gửi (Share)**.

---

### 5. Cấu hình file `.env`

Tạo file `.env` từ `.env.example`:
```bash
cp .env.example .env
```
Mở file `.env` và điền các thông tin:
```env
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxx
GOOGLE_CREDENTIALS_FILE=credentials.json
SPREADSHEET_ID_OR_NAME=Chi Tieu Ca Nhan
TIMEZONE=Asia/Ho_Chi_Minh
```

---

## 🚀 Khởi Chạy Bot

Chạy lệnh sau trong terminal:
```bash
python main.py
```

Khi màn hình hiện:
```
🚀 Đang khởi động Telegram AI Expense Bot...
✅ Bot đã sẵn sàng nhận tin nhắn trên Telegram!
```
Bạn đã có thể mở Telegram, tìm bot của mình và bắt đầu chat! 🎉

---

## 💬 Hướng Dẫn Sử Dụng Bot

### Ghi chép chi tiêu bằng tin nhắn:
- *"Ăn phở 45k"*
- *"Đổ xăng 50 cành, mua nước 15k"*
- *"Đi chợ hết 150 nghìn"*
- *"Lương về 18 củ"*
- *"Hôm qua mua giày 450k"*

### Các lệnh điều khiển:
| Lệnh | Ý nghĩa |
| :--- | :--- |
| `/start` | Mở menu bàn phím và lời chào |
| `/baocao` | Báo cáo tổng thu, tổng chi và chi tiết danh mục tháng này |
| `/baocao [tháng] [năm]` | Xem báo cáo tháng cụ thể (ví dụ: `/baocao 7 2026`) |
| `/thongke` | Nhận ảnh biểu đồ tròn phân bổ chi tiêu |
| `/homnay` | Xem danh sách các khoản chi trong ngày hôm nay |
| `/xem` | Xem danh sách 8 giao dịch gần nhất kèm Mã GD |
| `/xoa <Mã GD>` | Xóa dòng giao dịch trên Google Sheet (ví dụ: `/xoa TX260820A1B2`) |
| `/link` | Lấy đường link mở nhanh Google Sheet trên trình duyệt |
| `/help` | Xem hướng dẫn sử dụng |
