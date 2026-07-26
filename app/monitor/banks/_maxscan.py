#!/usr/bin/env python3
"""
banks/_maxscan.py — helper กลางสำหรับ rate_target โหมด max_tier/top_tier/max_all
("อัตราสูงสุด" ①②③ — ดู CLAUDE.md) รวมยอด "ภายในผลิตภัณฑ์เดียวกัน" จาก tier ที่ parser
เก็บมาแล้ว (ไม่ใช่ full-table scan ข้ามผลิตภัณฑ์)

แยกจาก _tablekit.py โดยเจตนา: parser_signature() (banks/__init__.py) แฮช _tablekit.py รวมกับซอร์ส
parser ทุกตัวเสมอ (รวม BBL) — ถ้าใส่ฟังก์ชันพวกนี้ไว้ใน _tablekit.py จะทำให้ parse_cache ของ BBL ตกไป
ด้วยทั้งที่ BBL ไม่ได้ใช้โมดูลนี้เลย (BBL ยังไม่รองรับโหมด max ในรอบนี้) ไฟล์นี้จึงถูกใช้เฉพาะจาก
scb.py/ktb.py/bay.py/kbank.py (parser ที่มี text layer) เท่านั้น

รูปแบบการใช้งานร่วมกันของทุก parser: parser เก็บ tier ของแถวที่พบ (เหมือนที่ทำอยู่แล้วก่อนเลือกด้วย
amount_m) เป็น list ของ tuple (kind, lower_m, upper_m, desc, raw) — raw คือข้อมูลดิบที่ value_of()
ของ parser นั้นใช้ดึงค่าตัวเลขในแต่ละคอลัมน์ (เช่น บรรทัดข้อความสำหรับ SCB/KTB/BAY, tier dict/words
สำหรับ KBANK) แล้วเรียก select(mode, tiers, col, depositor_columns, value_of) ให้ตัดสินใจแทน
"""

import re

from ._tablekit import kw_in_line, amount_to_million

# ─────────────────────────── Tier classification (ถ้อยคำ "วงเงิน...") ───────────────────────────
# ต้องจับด้วย consonant skeleton (ผ่าน kw_in_line) ไม่ใช่ regex บนข้อความดิบ — ฟอนต์ประกาศบางยุค (ยืนยัน
# แล้วกับ SCB ปี 2562) ถอด "ตั้งแต่ N ล้านบาทขึ้นไป" เป็น "ตงั<แต่ N ล้านบาทขึน< ไป" (มีช่องว่าง/สัญลักษณ์
# แทรกกลางคำ) ซึ่ง skeleton ของทั้งสองฟอนต์เท่ากันเป๊ะ แต่ regex ที่เขียนดักด้วยมือพลาดเกือบทุกกรณี
_AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(แสน|ล.{0,3}?น)?\s*บาท")


def _amount_to_million_ext(num_s: str, unit: str | None) -> float:
    """เหมือน _tablekit.amount_to_million แต่รองรับ 'บาทเปล่า' (ไม่มีหน่วยแสน/ล้านนำหน้า) เพิ่ม —
    กรณีนี้ตัวเลขเป็นบาทเต็มจริง ๆ (ไม่ใช่หน่วยล้าน) จึงหารด้วย 1,000,000 ก่อนแปลงเป็นล้านบาท"""
    if unit:
        return amount_to_million(num_s, unit)
    return float(num_s.replace(",", "")) / 1_000_000


def classify_tier_ext(line: str) -> tuple[str, float, float | None, str] | None:
    """จำแนกบรรทัด tier วงเงินแบบครบชุด (กว้างกว่า _tablekit.parse_tier_type_and_amount ที่รองรับแค่
    less_than/at_least หน่วยล้านบาท) — คืน (kind, lower_m, upper_m, desc) หรือ None ถ้าไม่ใช่บรรทัด tier
    kind: 'less_than' (< upper) · 'up_to' (<= upper) · 'between' (lower..upper) ·
          'at_least' (>= lower) · 'above' (> lower)"""
    if not (kw_in_line("วงเงิน", line) or kw_in_line("ยอดเงินฝาก", line)):
        return None
    amounts = _AMOUNT_RE.findall(line)
    if not amounts:
        return None
    vals = [_amount_to_million_ext(n, u) for n, u in amounts]

    has_above = kw_in_line("ส่วนที่เกิน", line)
    has_up_to = kw_in_line("ไม่เกิน", line)
    has_at_least = kw_in_line("ตั้งแต่", line) and kw_in_line("ขึ้นไป", line)
    has_not_reach = kw_in_line("ไม่ถึง", line)
    has_less_than = kw_in_line("น้อยกว่า", line)

    # เช็คคู่ (between) ก่อนเสมอ — บรรทัด between มี marker ของฝั่งเดียว (above/at_least) ปนอยู่ด้วย
    if has_above and has_up_to and len(vals) >= 2:
        return ("between", vals[0], vals[1], f"ส่วนที่เกิน {vals[0]:g} แต่ไม่เกิน {vals[1]:g} ล้านบาท")
    if kw_in_line("ตั้งแต่", line) and has_not_reach and len(vals) >= 2:
        return ("between", vals[0], vals[1], f"ตั้งแต่ {vals[0]:g} แต่ไม่ถึง {vals[1]:g} ล้านบาท")

    if has_above:
        return ("above", vals[0], None, f"ส่วนที่เกิน {vals[0]:g} ล้านบาทขึ้นไป")
    if has_at_least:
        return ("at_least", vals[0], None, f"ตั้งแต่ {vals[0]:g} ล้านบาทขึ้นไป")
    if has_up_to:
        return ("up_to", 0.0, vals[0], f"ไม่เกิน {vals[0]:g} ล้านบาท")
    if has_less_than:
        return ("less_than", 0.0, vals[0], f"น้อยกว่า {vals[0]:g} ล้านบาท")
    return None


def tier_rank(kind: str, lower_m: float, upper_m: float | None) -> tuple[int, float]:
    """จัดอันดับ 'วงเงินสูงสุด' — ใช้เลือก tier บนสุดสำหรับโหมด top_tier (②)
    kind ที่ไม่มีเพดานบน ('at_least'/'above') มาก่อน kind ที่มีเพดานบนเสมอ (วงเงินไม่จำกัดถือว่า
    'สูงสุด' โดยธรรมชาติ) แล้วค่อยเทียบกันเองด้วยขอบล่าง (lower_m ยิ่งมาก ยิ่งเป็น tier บนสุด)
    kind ที่มีเพดานบนเทียบกันเองด้วย upper_m — ห้ามคืน inf ให้ at_least/above ทุกตัวเท่ากัน (บั๊กเดิม
    ที่เจอตอนทดลอง: ทำให้ผลิตภัณฑ์ที่มี tier ตั้งแต่ 10/500/1,000 ล้าน ถูกมองว่าเป็น top ทั้งสามตัว)"""
    if kind in ("at_least", "above"):
        return (1, lower_m)
    return (0, upper_m if upper_m is not None else float("inf"))


def _valid_rate(raw) -> float | None:
    """แปลงค่าดิบเป็นอัตราดอกเบี้ย — คืน None ถ้าเป็น '-'/อ่านไม่ได้/นอกช่วงที่สมเหตุสมผล (0.0-10.0)
    ค่าสูงสุดอ่อนไหวต่อการอ่านผิดเป็นพิเศษ (ค่าผิดแบบสูงเกินจริงกลายเป็นคำตอบทันที) จึงเช็คช่วงเสมอ"""
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "" or s == "-":
        return None
    try:
        r = float(s)
    except ValueError:
        return None
    return r if 0.0 <= r <= 10.0 else None


MODES = ("max_tier", "top_tier", "max_all")


def select(mode: str, tiers: list[tuple], col: int, depositor_columns: dict[int, list[str]], value_of):
    """ตัวเลือกร่วมของทุก parser สำหรับโหมด max — คืน (rate, desc) หรือ (None, เหตุผล)
    tiers: list ของ (kind, lower_m, upper_m, desc, raw) ที่ parser เก็บมาจากแถวเดียวกัน
    value_of(tier, col): callback ของแต่ละ parser คืนค่าดิบ (str) ที่คอลัมน์ col ของ tier นั้น
    col: คอลัมน์ผู้ฝากเป้าหมาย (ใช้กับ max_tier/top_tier — max_all ไล่ทุกคอลัมน์ใน depositor_columns เอง)"""
    if not tiers:
        return None, "ไม่พบ tier ในแถวนี้"

    if mode == "max_tier":
        best, best_desc = None, ""
        for tier in tiers:
            r = _valid_rate(value_of(tier, col))
            if r is not None and (best is None or r > best):
                best, best_desc = r, f"สูงสุดทุกวงเงิน ({tier[3]})"
        if best is None:
            return None, "ไม่พบค่าที่อ่านได้ในคอลัมน์นี้"
        return best, best_desc

    if mode == "top_tier":
        for tier in sorted(tiers, key=lambda t: tier_rank(t[0], t[1], t[2]), reverse=True):
            r = _valid_rate(value_of(tier, col))
            if r is not None:
                return r, f"วงเงินสูงสุด ({tier[3]})"
        return None, "ไม่พบค่าที่อ่านได้ในคอลัมน์นี้"

    if mode == "max_all":
        best, best_desc = None, ""
        for tier in tiers:
            for c, aliases in depositor_columns.items():
                r = _valid_rate(value_of(tier, c))
                if r is not None and (best is None or r > best):
                    best, best_desc = r, f"สูงสุดทุกประเภทผู้ฝาก ({tier[3]} · {aliases[0]})"
        if best is None:
            return None, "ไม่พบค่าที่อ่านได้เลยสักคอลัมน์"
        return best, best_desc

    return None, f"ไม่รู้จักโหมด '{mode}'"
