#!/usr/bin/env python3
"""
banks/__init__.py — registry ของตัวอ่านอัตราดอกเบี้ยแยกตามธนาคาร

การเพิ่มธนาคารใหม่ (อาจมี PDF format ต่างจากเดิม):
  1. สร้างไฟล์ banks/<code>.py — กำหนด PARSER_IDS และ extract_rates(pdf_bytes, bank)
     (ทางเลือก: get_effective_date(pdf_bytes) ถ้ารูปแบบวันที่ต่างจากค่าเริ่มต้น)
  2. เพิ่มชื่อ module ลงใน _MODULES ด้านล่าง
ระบบส่วนกลาง (rate_monitor.py / common.py) ไม่มี logic เฉพาะธนาคาร
"""

import importlib

from ..common import log, get_effective_date as _default_effective_date

# รายชื่อ module ของแต่ละธนาคาร (เพิ่มไฟล์ใหม่ที่นี่)
_MODULES = ["scb"]

# parser_id -> module object
_REGISTRY: dict = {}

for _name in _MODULES:
    try:
        _mod = importlib.import_module(f"{__name__}.{_name}")
        for _pid in getattr(_mod, "PARSER_IDS", []):
            _REGISTRY[_pid] = _mod
    except Exception as e:  # pragma: no cover - ป้องกัน module เดียวพังทั้งระบบ
        log.error(f"banks: โหลด module '{_name}' ไม่สำเร็จ: {e}")


def available_parsers() -> list[str]:
    return sorted(_REGISTRY.keys())


def extract_rates(pdf_bytes: bytes, bank: dict) -> dict | None:
    """dispatch ตาม bank['parser'] → ตัวอ่านของธนาคารนั้น"""
    parser = bank.get("parser", "")
    mod = _REGISTRY.get(parser)
    if mod is None:
        log.error(f"extract_rates: ยังไม่รองรับ parser '{parser}' "
                  f"(มี: {', '.join(available_parsers()) or 'ไม่มี'})")
        return None
    return mod.extract_rates(pdf_bytes, bank)


def effective_date(pdf_bytes: bytes, bank: dict) -> str | None:
    """ใช้ get_effective_date ของ bank module ถ้ามี ไม่งั้นใช้ตัว default (Thai date)"""
    mod = _REGISTRY.get(bank.get("parser", ""))
    if mod is not None and hasattr(mod, "get_effective_date"):
        return mod.get_effective_date(pdf_bytes)
    return _default_effective_date(pdf_bytes)
