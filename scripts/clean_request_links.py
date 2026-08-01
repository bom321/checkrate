#!/usr/bin/env python3
"""
clean_request_links.py — งานครั้งเดียว (SEC-01): ล้างฟิลด์ 'link' ใน requests.json ที่ scheme ไม่ใช่
http(s) (เช่น javascript:) ออก

requests.html เรนเดอร์ r.link เป็น href ตรง ๆ — โค้ดใน main.py/requests.html แก้ให้กันค่าใหม่แล้ว
(api_request ปฏิเสธตอนรับเข้า + เทมเพลตซ่อนปุ่มถ้า scheme ไม่ปลอดภัย) แต่ข้อมูลเก่าที่หลุดเข้ามา
ก่อนแก้ยังอันตรายอยู่จนกว่าจะรันสคริปต์นี้ (idempotent — รันซ้ำได้ปลอดภัย ไม่มีอะไรให้ล้างครั้งที่สอง)

ใช้:
    export DATA_DIR="$PWD/data"; python3 scripts/clean_request_links.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.web import data_access as da  # noqa: E402


def _is_safe_link(url: str | None) -> bool:
    return bool(url) and url.strip().lower().startswith(("http://", "https://"))


def main() -> None:
    items = da.load_requests()
    removed = 0
    for r in items:
        link = r.get("link")
        if link is not None and not _is_safe_link(link):
            print(f"  ลบ link ของคำขอ id={r.get('id')}: {link!r}")
            del r["link"]
            removed += 1

    if removed:
        da._save_requests(items)  # atomic write เดิม
        print(f"ล้างแล้ว {removed} รายการ จากทั้งหมด {len(items)}")
    else:
        print(f"ไม่มี link ที่ scheme ไม่ปลอดภัย ({len(items)} คำขอทั้งหมด) — ไม่ต้องแก้")


if __name__ == "__main__":
    main()
