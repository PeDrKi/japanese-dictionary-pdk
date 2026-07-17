# 日本語 — Học Tiếng Nhật

Ứng dụng desktop học từ vựng tiếng Nhật (Python + CustomTkinter), lưu dữ liệu cục bộ bằng SQLite. Hỗ trợ Kanji, Hiragana, Katakana, và từ vựng, với các chế độ ôn tập theo phương pháp lặp lại ngắt quãng (spaced repetition).

## Tính năng

- **Quản lý thẻ từ vựng** — thêm/sửa/xóa, phân loại theo Kanji/Hiragana/Katakana/Từ vựng, gắn vào Deck và Danh mục, đánh dấu yêu thích, thùng rác (xóa mềm + khôi phục).
- **Ôn tập** — Flashcard, Quiz trắc nghiệm, Luyện gõ (typing practice), lịch ôn tập theo SRS (spaced repetition).
- **Nhập liệu nhanh** — tra cứu tự động qua Jisho.org, gợi ý dịch Anh→Việt, dán nhiều dòng để tạo hàng loạt thẻ, import/export CSV, export sang Anki (.apkg).
- **Bàn phím ảo** hiragana/katakana (bật bằng F8), gõ được vào bất kỳ ô nhập liệu nào đang mở, kể cả trong hộp thoại con.
- **Thống kê** tiến độ học, tìm kiếm/lọc nâng cao, phân trang tùy chỉnh.
- **Backup thủ công** và **đồng bộ 2 chiều với Google Drive** (tùy chọn).

## Cài đặt

Yêu cầu Python 3.10+.

```bash
pip install -r requirements.txt
python main.pyw
```

Lần đầu chạy, ứng dụng sẽ tự tạo database trống tại `database/japanese.db` — không có sẵn dữ liệu mẫu.

## Chạy test

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```

## Kiến trúc

Dự án theo hướng Clean Architecture, tách 4 tầng theo hướng phụ thuộc:

```
ui/              → chỉ gọi application/, không đụng database/ trực tiếp
application/     → use-case (CardService, DeckService, StudyService, StatsService)
domain/          → business rule thuần (validators, SRS, kana, parser...) — không import ra ngoài
infrastructure/  → SQLite, Google Drive, Jisho API, export Anki/CSV, dịch thuật
database/        → tầng dữ liệu SQLite gốc, chỉ được infrastructure/ gọi tới
```

`domain/` và `application/` có 100% test coverage (`tests/domain/`, `tests/application/`, `tests/infrastructure/`). `ui/` hiện chưa có test tự động.

## Đồng bộ Google Drive (tùy chọn)

Tính năng Sync cần file OAuth Client Secret riêng của bạn (không đi kèm repo này vì lý do bảo mật):

1. Tạo project trên [Google Cloud Console](https://console.cloud.google.com/), bật **Google Drive API**.
2. Tạo OAuth 2.0 Client ID loại **Desktop app**, tải file `client_secret_*.json`.
3. Đặt file đó vào thư mục `database/`.
4. Mở app → **☁️ Sync** → đăng nhập Google lần đầu qua trình duyệt.

Token đăng nhập (`database/drive_token.json`) và file database cá nhân (`database/japanese.db`) đã được `.gitignore` loại trừ — không bị commit lên GitHub.

## Giấy phép

Chưa có file LICENSE — nghĩa là mặc định giữ toàn quyền tác giả. Mã nguồn công khai để tham khảo, nhưng không cấp phép cho việc sao chép, sửa đổi, hay phân phối lại nếu chưa có sự đồng ý của tác giả.
