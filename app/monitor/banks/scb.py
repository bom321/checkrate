#!/usr/bin/env python3
"""
banks/scb.py — ตัวอ่านอัตราดอกเบี้ยของ ธนาคารไทยพาณิชย์ (SCB)
parser id: "scb_passbook"

ย้ายมาจาก scb_rate_monitor.py เดิม โดย **ไม่เปลี่ยนพฤติกรรมการ extract/parse**
เพิ่มธนาคารใหม่ = สร้างไฟล์ banks/<code>.py แบบเดียวกัน แล้วลงทะเบียนใน banks/__init__.py

แต่ละ bank module ต้องมี:
  PARSER_IDS : list[str]              รายชื่อ parser id ที่ไฟล์นี้รองรับ
  extract_rates(pdf_bytes, bank)      -> dict | None
  (ทางเลือก) get_effective_date(pdf_bytes) -> str | None  ถ้า format วันที่ต่างจากค่าเริ่มต้น
"""

import io, re
import pdfplumber

from ..common import log

PARSER_IDS = ["scb_passbook"]


def _parse_tier_type_and_amount(line: str) -> tuple[str, int] | None:
    m = re.search(r"น\D{0,8}ยกว\D{0,8}(\d[\d,]*)\s*ล\D{0,6}นบาท", line)
    if m:
        return ("less_than", int(m.group(1).replace(",", "")))
    m = re.search(r"ตงั\D{0,6}แต\D{0,8}(\d[\d,]*)\s*ล\D{0,6}นบาทขึน.ไป", line)
    if not m:
        m = re.search(r"ตั้งแต่\s+(\d[\d,]*)\s*ล\D{0,4}นบาทขึ้นไป", line)
    if m:
        return ("at_least", int(m.group(1).replace(",", "")))
    return None


def _extract_first_rate(line: str) -> float | None:
    m = re.search(r"\b(\d+\.\d+)\b", line)
    if m:
        v = float(m.group(1))
        if 0.01 <= v <= 10.0:
            return v
    return None


def _find_rate_for_amount(tiers: list[tuple], target_m: float) -> tuple[float | None, str]:
    less_than = sorted([(am, r) for (t, am, r) in tiers if t == "less_than"], key=lambda x: x[0])
    at_least  = sorted([(am, r) for (t, am, r) in tiers if t == "at_least"],  key=lambda x: x[0])
    for upper_m, rate in less_than:
        if target_m < upper_m:
            return (rate, f"น้อยกว่า {upper_m} ล้านบาท")
    if at_least:
        lower_m, rate = at_least[0]
        return (rate, f"ตั้งแต่ {lower_m} ล้านบาทขึ้นไป (fallback)")
    return (None, "ไม่พบ tier ที่เหมาะสม")


def extract_rates(pdf_bytes: bytes, bank: dict) -> dict | None:
    """SCB Regular Passbook parser — คืน dict {key: rate, ..., 'tiers_used': {...}}"""
    rate_targets = bank["rate_targets"]
    TARGET_TENORS = {t["tenor_months"] for t in rate_targets}
    SECTION_RE = re.compile(r"แบบม.{0,4}สมุด|แบบม[สี ]{0,5}มุด")
    SECTION_END_RE = re.compile(
        r"แบบผ.{0,2}กพ.น|ประจา.{0,2}เผ.{0,2}อเหล|ประจา.{0,3}เผ.{0,2}|"
        r"เงนิ ฝากสาน|เงินฝากสาน|^4\.\s+แบบ"
    )
    TENOR_RE = re.compile(r"^\s*(\d+)\s*เด[ือ]{1,2}น\s*$")

    in_section = False
    current_tenor: int | None = None
    tiers: dict[int, list] = {t: [] for t in TARGET_TENORS}

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    if SECTION_RE.search(s):
                        in_section = True
                        current_tenor = None
                        continue
                    if not in_section:
                        continue
                    if SECTION_END_RE.search(s):
                        in_section = False
                        current_tenor = None
                        continue
                    m = TENOR_RE.match(s)
                    if m:
                        t = int(m.group(1))
                        current_tenor = t if t in TARGET_TENORS else None
                        continue
                    if current_tenor in TARGET_TENORS:
                        tier_info = _parse_tier_type_and_amount(s)
                        if tier_info:
                            rate = _extract_first_rate(s)
                            if rate is not None:
                                tiers[current_tenor].append((tier_info[0], tier_info[1], rate))
    except Exception as e:
        log.error(f"_extract_scb_passbook: {e}")
        return None

    result: dict = {}
    tiers_used: dict = {}
    for target in rate_targets:
        key      = target["key"]
        tenor    = target["tenor_months"]
        amount_m = target["amount_m"]
        if not tiers.get(tenor):
            log.error(f"extract_rates: ไม่พบ tier ใดๆ สำหรับ {tenor}M")
            return None
        rate, desc = _find_rate_for_amount(tiers[tenor], amount_m)
        if rate is None:
            log.error(f"extract_rates: ไม่พบ rate สำหรับ {tenor}M/{amount_m}M")
            return None
        result[key] = rate
        tiers_used[key] = desc
        log.info(f"  {target['label']}: {rate:.2f}%  ← {desc}")

    result["tiers_used"] = tiers_used
    return result
