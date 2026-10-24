# Sửa lỗi sau đợt rà soát (đồng bộ & backup)

| Lỗi | Hậu quả trước khi sửa | Đã sửa |
|---|---|---|
| Xóa / khôi phục / ★ / đổi trạng thái hàng loạt / **ôn tập** không cập nhật `updated_at` của thẻ | Sync coi là "không đổi": xóa & tiến độ không sang máy khác, bản xóa có thể bị bản cũ trên cloud "hồi sinh" | `database/_cards.py`, `database/_study.py` |
| Sync không mang theo `srs_interval / srs_ease / srs_due_date` | Thẻ kéo về mất lịch ôn (đang "Đã nhớ" nhưng đến hạn ôn ngay) | `infrastructure/supabase_sync.py` (`_CARD_COLS`) |
| `deck_categories` không được đồng bộ | Bộ thẻ kéo về có `category_id` mồ côi | `_merge_categories` (gộp theo tên) |
| Sync chèn `deck_cards` / `radical_cards` / `study_sessions` với `id = NULL` | Dòng không có khoá chính; nhập vào bản web bị lỗi NOT NULL | Cấp UUIDv7 khi chèn + `init_db` tự vá dữ liệu cũ |
| Backup chép file `.db` thô khi đang bật WAL | **File backup thiếu dữ liệu mới nhất (có thể rỗng)** | Dùng SQLite Backup API |
| Restore thay file thô khi app còn mở | Khi thoát, file `-wal` cũ bị áp lên bản khôi phục → bản khôi phục bị hủy/hỏng | Restore bằng Backup API + kiểm tra `integrity_check` trước |
| Backup chứa `settings.json` kèm khoá Supabase | Gửi file backup cho người khác là lộ khoá | Loại các khoá `supabase_*` khỏi backup; restore giữ cấu hình Supabase hiện tại |

Test hồi quy: `tests/infrastructure/test_sync_and_backup_fixes.py` (17 test fail trên code cũ, pass trên code mới). Toàn bộ: 246 test pass.


## Đợt 2 — đồng nhất desktop ↔ web
- Desktop đồng bộ vào CÙNG Postgres/schema v3 với web (`infrastructure/cloud_sync.py`, `cloud_config.py`, `ui/sync_dialog.py`): đăng nhập Supabase Auth, khoá anon + RLS, CAS theo `version`, gộp theo trường, tombstone, `log_study` phía server, UTC.
- Thay thế sync file `.db` qua Storage (khoá anon không ghi được → lỗi RLS bạn gặp; dùng service_role thì lộ toàn quyền).
- Backup/restore: dùng SQLite Backup API; settings xuất ra bỏ mọi khoá bí mật `cloud_*`.
- CSV: `status` lạ → `new` (như web) để không vi phạm CHECK khi sync.
- Kiểm chứng: giới hạn độ dài, hằng số SRS, nhãn trạng thái đã đối chiếu khớp web; test tích hợp engine ↔ Postgres+PostgREST thật; e2e desktop↔web (Playwright) 9/9.
- CHƯA kiểm chứng: giao diện Tkinter/Qt (không chạy được GUI ở đây), đăng nhập GoTrue thật trên Supabase thật.

## Đợt 3 — rà soát lại toàn bộ (web + desktop)
Đã sửa (đều có test hồi quy, `tests/infrastructure/test_audit_fixes.py`):
- Đổi tài khoản/máy chủ trên cùng DB: trước đây xoá sạch dữ liệu tài khoản cũ khỏi máy và đẩy dữ liệu chưa gửi sang tài khoản mới. Nay engine **từ chối** (lưu `user_id` + URL ở lần sync đầu); hộp thoại hỏi "Đặt lại liên kết" → cấp ID mới và gửi dữ liệu trên máy lên tài khoản mới.
- Khôi phục backup bị lần sync sau ghi đè bằng trạng thái máy chủ → sau khi khôi phục, trạng thái đồng bộ được đặt lại (bản khôi phục được coi là chưa gửi).
- Danh mục bị xoá ở nơi khác khiến sync lỗi lặp vô hạn (FOREIGN KEY) → bỏ tham chiếu rồi xoá; lỗi từng hàng không còn chặn cả lần sync.
- UNIQUE tên bộ thẻ/ký tự bộ thủ tính cả hàng đã xoá mềm (xoá "A" rồi tạo lại "A" báo lỗi) → chỉ mục duy nhất có điều kiện + tự migrate DB cũ (không mất liên kết thẻ).
- Chữ ký đồng bộ lưu ở cuối lần sync có thể nuốt thay đổi của máy khác → chỉ lưu chữ ký đọc trước khi kéo và chỉ khi lần đó không ghi gì.
- Hai lần sync chạy chồng (hộp thoại + tự sync/khi thoát) → khoá toàn cục; sync lúc thoát có hạn tổng 20 giây.
- Phân trang không phụ thuộc max-rows; mục đã xoá vĩnh viễn nhưng DELETE lỗi không bị tạo lại; ghi settings.json nguyên tử + khoá.
- Yêu thích hàng loạt: cả nhóm cùng một trạng thái (như web); CSV: JLPT ngoài N1–N5 bỏ.
Chưa làm (ghi nhận): `after()` gọi từ luồng nền (Tk thường chịu được), sync lúc thoát vẫn chặn cửa sổ tối đa ~20 giây.

## Đợt 4 — Từ loại (pos)
Thẻ từ vựng có thêm từ loại (Danh từ, Động từ [hoặc nhóm 1/2/3], Tính từ đuôi い/な, Đại từ, Trợ từ, Trạng từ, Liên từ, Thán từ), đồng bộ cùng bản web. Có: cột DB `cards.pos` (tự thêm khi mở app), ô chọn trong form thẻ, dòng trong chi tiết thẻ, cột "Từ loại" trong bảng, bộ lọc trên thanh công cụ, CSV (cột `pos`), đồng bộ đám mây. Schema Supabase lên phiên bản 5 → phải chạy lại `docs/supabase_schema.sql`; app từ chối đồng bộ nếu chưa nâng cấp.

## Đợt 5 — Giao diện (UX)
- Bảng: cột Ký tự → Kana → On/Kun → Nghĩa → Từ loại → JLPT → Status hiện ngay không cần cuộn ngang; STT/Hán Việt/Romaji/Nguồn/Ngày thêm ẩn mặc định. **Chuột phải vào tiêu đề cột** để bật/tắt cột (lưu lại).
- Thanh công cụ: gom Import/Export CSV, Anki, Template vào menu "📁 Nhập / Xuất"; ô lọc gọn lại để không bị cắt khi cửa sổ hẹp (≥ 980px).
- Thanh điều hướng: nút lớn/rõ hơn. Panel chi tiết: tiêu đề không còn bị cắt.

## Đợt 6 — Xử lý giới hạn đã biết
- Sync lúc thoát chạy ở luồng nền: cửa sổ chính ẩn ngay, hộp nhỏ báo "Đang đồng bộ lần cuối…", tối đa ~22s, không còn "Not Responding".
- Mọi callback từ luồng nền (sync, tra Jisho, dịch gợi ý, thống kê) về giao diện qua hàng đợi `ui/threadsafe.py` thay vì gọi `after()` từ luồng nền.
- `docs/supabase_schema.sql` cập nhật theo bản web (log_study chặn giờ tương lai) — chạy lại 1 lần trên Supabase.

## Đợt 7 — Đồng bộ chạy ngầm sau khi đóng app
- Đóng cửa sổ → app lưu trạng thái, ẩn ngay và bật `main.pyw --sync-only` (tiến trình tách rời, không cửa sổ). Tiến trình này đồng bộ tới khi xong (tối đa ~2 phút) rồi tự thoát. Nếu không bật được → dự phòng đồng bộ trong app như trước.
- `infrastructure/sync_lock.py`: khoá liên-tiến-trình (file `japanese.db.sync.lock`, tự dọn khi tiến trình chết/quá 10 phút) — mở lại app khi sync ngầm còn chạy sẽ không chạy chồng (app im lặng, lần sau bù).
- `settings.py` đọc lại file trước khi ghi để không ghi đè refresh token do tiến trình ngầm vừa xoay.
- Log của tiến trình ngầm nằm trong `app.log`.

## Đợt 8 — Sau khi có phân quyền
- Thông báo rõ khi tài khoản bị khóa (thay vì lỗi RLS thô); dữ liệu trên máy giữ nguyên, tự gửi lại khi được mở khóa.
- `docs/supabase_schema.sql` = schema bản 6 (vai trò user/admin).

## Đợt 9 — Phím tắt
- Ctrl+1/2/3 chuyển tab; Ctrl+R ôn hôm nay; F2/F3/F4 Thẻ ghi nhớ/Quiz/Luyện gõ; F9 Sync; Ctrl+B Backup; Enter sửa thẻ đang chọn; F1 (hoặc nút ⌨ trên thanh trên cùng) mở bảng phím tắt. Phím mở công cụ bỏ qua khi đang có hộp thoại modal hoặc giữ phím.
- Danh sách nằm ở `constants.py` (`KB_*`, `SHORTCUT_HELP`) — thêm/sửa phím ở đó.

## Đợt 10 — UX desktop ngang bản web
- Form thêm thẻ: gõ ký tự Nhật → sau 0,65s tự tra Jisho và điền ô còn trống (nghĩa Anh, cách đọc, romaji, JLPT, nguồn). Không ghi đè ô bạn đã gõ; lỗi mạng thì im lặng.
- Ví dụ, trạng thái, nguồn, ảnh/âm thanh, ghi chú nằm trong mục "Tùy chọn thêm" (thu gọn khi thêm mới, mở sẵn khi sửa).
- Hộp "Bắt đầu ôn" của Flashcard/Quiz/Gõ nhớ lại lựa chọn lần trước (`ui/launcher_prefs.py`, lưu trong settings.json; bộ thẻ đã xóa thì bỏ qua).
- Nhãn thống nhất với web: "Trạng thái", "Bộ thẻ".
- Kiểm tra: pytest 300 pass; thử GUI trên Xvfb (tự điền, không ghi đè, nhớ cài đặt) pass. Chưa thử trên Windows thật / Jisho thật.

## Đợt 11 — Khớp bản web v3.35
- **Quy tắc trạng thái theo số lần học**: đúng +1, sai −1 (không âm); ≥ 20 = Đã thuộc, 0 = Mới, còn lại = Đang học. Trạng thái giờ tự tính, không sửa tay trong form (chỉ xem); đổi trạng thái hàng loạt sẽ quy về số lần học. Server vẫn là nơi tính SRS, máy chỉ phản chiếu (`domain/srs.py`, kiểm tra khớp web bằng `tests/fixtures/web_parity.json`).
- **Chọn icon lớn** cho Deck/Danh mục (`ui/icon_picker.py`, nhóm icon ở `constants.ICON_GROUPS`).
- **Tab mới**: Ngữ pháp (Ctrl+4), Chia động từ (Ctrl+5), Bản dịch (Ctrl+6, hai bên + từ vựng, chọn từ để thêm vào bộ thẻ, chọn câu/đoạn làm ví dụ ngữ pháp).
- **Đồng bộ thêm 5 bảng**: grammar_points, translations, conj_forms, conj_verbs, conj_cells (xóa cứng có tombstone; conj_cells không có version, ghi sau thắng).
- **Bắt buộc**: chạy lại toàn bộ `docs/supabase_schema.sql` (schema v12) trong Supabase; app yêu cầu schema ≥ 12.
- Thanh tab gọn lại (cửa sổ tối thiểu 1040px); sửa lỗi tab đang chọn không được tô màu; tự tải lại sau khi Sync.
- Kiểm tra: pytest 320 pass (có Postgres 16 + PostgREST thật), thử GUI trên Xvfb pass. Chưa thử trên Supabase thật / Windows thật / Jisho thật. Chưa port: nhiều âm On/Kun, menu "Khác" gọn.
