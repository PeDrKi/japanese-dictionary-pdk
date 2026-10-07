"""
infrastructure/id_gen.py — sinh UUIDv7 để làm khoá chính (id) cho mọi bảng.

Vì sao UUIDv7 thay vì INTEGER AUTOINCREMENT:
  - Không bao giờ trùng giữa các thiết bị khác nhau (khắc phục rủi ro
    "trùng ID" khi sync 2 chiều qua Supabase — xem infrastructure/supabase_sync.py).
  - Vẫn SẮP XẾP ĐƯỢC theo thứ tự tạo: 48 bit đầu của UUIDv7 là timestamp
    (mili-giây), nên so sánh chuỗi UUID theo thứ tự = so sánh theo thời
    gian tạo, y hệt ID số tăng dần — khác với UUIDv4 (hoàn toàn ngẫu
    nhiên, sắp xếp vô nghĩa).
  - Số thứ tự đẹp (1, 2, 3...) để hiển thị cho người dùng được tính lại
    mỗi lần hiển thị (xem infrastructure/stt.py), KHÔNG lưu trong DB —
    nên không cần ID trông "đẹp".

Python 3.14+ đã có uuid.uuid7() sẵn trong thư viện chuẩn; app này có thể
chạy trên Python cũ hơn nên tự cài đặt theo đúng RFC 9562 (48-bit
timestamp ms + 4-bit version + 12-bit random_a + 2-bit variant + 62-bit
random_b), không phụ thuộc phiên bản Python.
"""

import os
import time
import uuid


def uuid7() -> str:
    """Sinh 1 UUIDv7 mới dạng chuỗi chuẩn (vd '018f4d2a-...-...')."""
    unix_ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bit
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF  # 12 bit
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bit

    time_hi = unix_ts_ms >> 16          # 32 bit cao của timestamp
    time_lo = unix_ts_ms & 0xFFFF       # 16 bit thấp của timestamp

    field3 = (0x7 << 12) | rand_a       # version=7 (0111) + rand_a
    field4 = (0b10 << 62) | rand_b      # variant=10 + rand_b

    as_int = (
        (time_hi << 96)
        | (time_lo << 80)
        | (field3 << 64)
        | field4
    )
    return str(uuid.UUID(int=as_int))
