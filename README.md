# 日本語 — Học Tiếng Nhật

Ứng dụng desktop học từ vựng tiếng Nhật (Python + CustomTkinter), lưu dữ liệu cục bộ bằng SQLite. Hỗ trợ Kanji, Hiragana, Katakana, và từ vựng, với các chế độ ôn tập theo phương pháp lặp lại ngắt quãng (spaced repetition).

## Tính năng

- **Quản lý thẻ từ vựng** — thêm/sửa/xóa, phân loại theo Kanji/Hiragana/Katakana/Từ vựng, gắn vào Deck và Danh mục, đánh dấu yêu thích, thùng rác (xóa mềm + khôi phục).
- **Ôn tập** — Flashcard, Quiz trắc nghiệm, Luyện gõ (typing practice), lịch ôn tập theo SRS (spaced repetition).
- **Nhập liệu nhanh** — tra cứu tự động qua Jisho.org, gợi ý dịch Anh→Việt, dán nhiều dòng để tạo hàng loạt thẻ, import/export CSV, export sang Anki (.apkg).
- **Ngữ pháp, Chia động từ, Bản dịch** (Ctrl+4/5/6) — giống bản web, đồng bộ chung dữ liệu. Trạng thái thẻ tự tính theo số lần học (≥ 20 = đã thuộc).
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

## Đồng bộ đám mây (dùng chung dữ liệu với bản web)

Bản desktop và bản web `jpdic-web` đồng bộ vào **cùng một Postgres Supabase** (schema v3, mỗi người dùng chỉ thấy dữ liệu của mình nhờ RLS). Học trên điện thoại → mở app desktop → thấy ngay, và ngược lại.

1. Chạy toàn bộ `docs/supabase_schema.sql` (cùng file với `schema.sql` của bản web) trong Supabase → SQL Editor (chạy lại nhiều lần vẫn an toàn).
2. Authentication → tạo/đăng ký tài khoản (cùng email với bản web).
3. Settings → API: lấy **Project URL** và khoá **anon / publishable**. **KHÔNG dùng service_role / secret** — app sẽ cảnh báo và từ chối.
4. Mở app → **☁️ Sync** → dán URL + khoá anon + email + mật khẩu → đăng nhập. Mật khẩu không được lưu; app chỉ giữ refresh token (thu hồi được) trong `settings.json`, và file này không đi vào bản backup.

Cách hoạt động: SQLite vẫn là bản làm việc offline; mỗi dòng có cờ "đã sửa", ảnh chụp gốc (`base_json`) và `server_version`. Khi sync: đẩy bằng so sánh phiên bản (CAS), nếu server đã đổi thì gộp theo **từng trường** (3 bên: gốc/máy này/server); chỉ khi cả hai sửa cùng một trường thì lấy bản **mới hơn** và ghi giá trị thua vào bảng `sync_conflicts` trong SQLite cục bộ (kèm thông báo sau khi sync). Xoá được đồng bộ bằng tombstone. Lịch sử học và SRS do hàm `log_study` trên server tính (không trùng, không mất khi 2 máy học cùng lúc). Giờ local được đổi sang UTC khi gửi.

Khác biệt còn lại so với bản web: file âm thanh/ảnh chỉ nằm cục bộ; desktop tự giải quyết xung đột cùng trường (web thì hỏi bạn); hai thẻ trùng nội dung nhưng khác id không tự gộp.

Cơ chế cũ (đẩy cả file `japanese.db` lên Storage bằng khoá anon) đã **ngừng dùng** vì không an toàn/không có khoá phiên bản; code vẫn còn trong `infrastructure/supabase_sync.py` nhưng giao diện không còn gọi.

Token đăng nhập (`database/drive_token.json`) và file database cá nhân (`database/japanese.db`) đã được `.gitignore` loại trừ — không bị commit lên GitHub.
