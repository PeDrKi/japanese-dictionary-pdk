# 日本語 — Học Tiếng Nhật

Ứng dụng desktop học từ vựng tiếng Nhật (Python + CustomTkinter), lưu dữ liệu cục bộ bằng SQLite. Hỗ trợ Kanji, Hiragana, Katakana, và từ vựng, với các chế độ ôn tập theo phương pháp lặp lại ngắt quãng (spaced repetition).

## Tính năng

- **Quản lý thẻ từ vựng** — thêm/sửa/xóa, phân loại theo Kanji/Hiragana/Katakana/Từ vựng, gắn vào Deck và Danh mục, đánh dấu yêu thích, thùng rác (xóa mềm + khôi phục).
- **Ôn tập** — Flashcard, Quiz trắc nghiệm, Luyện gõ (typing practice), lịch ôn tập theo SRS (spaced repetition).
- **Nhập liệu nhanh** — tra cứu tự động qua Jisho.org, gợi ý dịch Anh→Việt, dán nhiều dòng để tạo hàng loạt thẻ, import/export CSV, export sang Anki (.apkg).
- **Bàn phím ảo** hiragana/katakana (bật bằng F8), gõ được vào bất kỳ ô nhập liệu nào đang mở, kể cả trong hộp thoại con.

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
infrastructure/  → SQLite, Supabase Sync, Jisho API, export Anki/CSV, dịch thuật
database/        → tầng dữ liệu SQLite gốc, chỉ được infrastructure/ gọi tới
```

`domain/` và `application/` có 100% test coverage (`tests/domain/`, `tests/application/`, `tests/infrastructure/`). `ui/` hiện chưa có test tự động.

## Đồng bộ Supabase (tùy chọn)

Đồng bộ file `japanese.db` 2 chiều giữa các thiết bị qua [Supabase](https://supabase.com) Storage — không cần đăng nhập OAuth, chỉ cần Project URL + API key:

1. Tạo project miễn phí trên [supabase.com](https://supabase.com).
2. Vào **Storage** → tạo bucket mới (ví dụ `japanese-db-sync`).
3. Vào **Settings → API**, copy **Project URL** và **API key** (anon hoặc service_role).
4. Mở app → nút Sync → dán URL + key + tên bucket → **Bắt đầu Sync**.

Cài đặt được lưu lại trong `settings.json` (cạnh DB) để lần sau không phải nhập lại. Cùng một project + bucket có thể dùng chung cho mọi thiết bị đang chạy app này.
4. Mở app → **☁️ Sync** → đăng nhập Google lần đầu qua trình duyệt.

Token đăng nhập (`database/drive_token.json`) và file database cá nhân (`database/japanese.db`) đã được `.gitignore` loại trừ — không bị commit lên GitHub.
