#!/usr/bin/env python3
"""
thaidate.py — แปลงวันที่ ISO เป็นรูปแบบไทย (พ.ศ.) สำหรับ template

ลงทะเบียนเป็น Jinja filter ใน main.py — ทุกฟังก์ชันทนค่า None/สตริงเพี้ยน (คืน "-")
เพราะข้อมูลมาจาก CSV/result.json ที่อาจหายหรือเสียได้
"""

from datetime import datetime

_BE_OFFSET = 543

_MONTH_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

_MONTH_FULL = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]


def _parse(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(str(value).strip()[:len("2026-07-12")], fmt)
    except (TypeError, ValueError):
        return None


def thai_date(value) -> str:
    """'2026-07-12' → '12 ก.ค. 69'"""
    d = _parse(value, "%Y-%m-%d")
    if not d:
        return "-"
    return f"{d.day:02d} {_MONTH_ABBR[d.month - 1]} {(d.year + _BE_OFFSET) % 100:02d}"


def thai_date_full(value) -> str:
    """'2026-07-12' → '12 ก.ค. 2569' (ใช้ตรงที่ต้องเห็นปีเต็ม)"""
    d = _parse(value, "%Y-%m-%d")
    if not d:
        return "-"
    return f"{d.day:02d} {_MONTH_ABBR[d.month - 1]} {d.year + _BE_OFFSET}"


def thai_month(value) -> str:
    """'2026-07' → 'กรกฎาคม 2569'"""
    try:
        y, m = str(value).strip().split("-")[:2]
        return f"{_MONTH_FULL[int(m) - 1]} {int(y) + _BE_OFFSET}"
    except (AttributeError, IndexError, ValueError):
        return "-"


def thai_month_short(value) -> str:
    """'2026-07' → 'ก.ค. 69' (ใช้ใน pill ตัวกรองเดือน)"""
    try:
        y, m = str(value).strip().split("-")[:2]
        return f"{_MONTH_ABBR[int(m) - 1]} {(int(y) + _BE_OFFSET) % 100:02d}"
    except (AttributeError, IndexError, ValueError):
        return "-"


def thai_year(value) -> str:
    """'2026' → '2569' (กลุ่มไฟล์รายปี — ค่าที่ไม่ใช่ตัวเลข เช่น 'อื่น ๆ' คืนตามเดิม)"""
    s = str(value).strip()
    return str(int(s) + _BE_OFFSET) if s.isdigit() else s


def thai_datetime(value) -> str:
    """'2026-07-12T09:00:14' → '12 ก.ค. 09:00 น.'"""
    try:
        d = datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return "-"
    return f"{d.day:02d} {_MONTH_ABBR[d.month - 1]} {d:%H:%M} น."


FILTERS = {
    "thai_date": thai_date,
    "thai_date_full": thai_date_full,
    "thai_month": thai_month,
    "thai_month_short": thai_month_short,
    "thai_year": thai_year,
    "thai_datetime": thai_datetime,
}
