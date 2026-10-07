"""
infrastructure/stt.py — gắn số thứ tự (STT) hiển thị 1, 2, 3... vào danh
sách bản ghi, dựa theo thứ tự created_at (mặc định) hoặc thứ tự đang có
sẵn trong list.

STT KHÔNG lưu trong database — chỉ tính khi hiển thị. Lý do: nếu lưu cứng
STT vào DB thì 2 thiết bị khác nhau có thể tính ra STT khác nhau cho cùng
1 bản ghi (y hệt vấn đề trùng ID mà việc chuyển sang UUIDv7 đang khắc
phục), lại phải merge lần nữa. Tính lại mỗi lần hiển thị thì luôn đúng,
luôn nhất quán trên mọi thiết bị, và không có gì để xung đột khi sync.
"""


def with_stt(rows: list, *, key: str = "stt", start: int = 1) -> list:
    """
    Trả về list dict mới, mỗi dict được thêm key `stt` = 1, 2, 3...
    theo ĐÚNG thứ tự đã có sẵn trong `rows` (không tự sắp xếp lại — hàm
    gọi nơi khác chịu trách nhiệm ORDER BY created_at hay theo tiêu chí
    nào trước khi gọi hàm này).

    Không sửa list gốc — trả về list dict mới (copy nông từng dict).
    """
    result = []
    for i, row in enumerate(rows, start=start):
        r = dict(row)
        r[key] = i
        result.append(r)
    return result
