#!/usr/bin/env python3
"""
banks/scb.py — ตัวอ่านอัตราดอกเบี้ยของ ธนาคารไทยพาณิชย์ (SCB)
parser id: "scb_passbook"

อ่านตารางเมทริกซ์จากประกาศ (แถว = ผลิตภัณฑ์/ระยะเวลา/วงเงิน, คอลัมน์ = ประเภทลูกค้า 13 คอลัมน์)
โดยแต่ละ rate_target กำหนดได้เองว่าจะอ่าน:
  - section_keyword : ข้อความหัวข้อกลุ่มผลิตภัณฑ์ (เช่น "เงินฝากประจำ แบบมีสมุด", "ออมทรัพย์แบบไม่มีสมุดคู่ฝาก")
                       default = DEFAULT_SECTION_KEYWORD (เงินฝากประจำ แบบมีสมุด — พฤติกรรมเดิม)
  - row_keyword     : ข้อความหัวแถว/ผลิตภัณฑ์ (เช่น "12 เดือน") default = "{tenor_months} เดือน"
  - depositor       : ประเภทลูกค้า/คอลัมน์ — คีย์เวิร์ดไทย/อังกฤษ หรือเลขคอลัมน์ 1-13 (ดู DEPOSITOR_COLUMNS)
                       default = "บุคคลธรรมดา" (คอลัมน์ 1 — พฤติกรรมเดิม)
  - amount_m        : ใช้เลือก tier วงเงิน ถ้าแถวที่พบมีหลาย tier

เพิ่มธนาคารใหม่ = สร้างไฟล์ banks/<code>.py แบบเดียวกัน แล้วลงทะเบียนใน banks/__init__.py
(ใช้ helper ที่ generic จาก banks/_tablekit.py ร่วมกันได้)

แต่ละ bank module ต้องมี:
  PARSER_IDS : list[str]              รายชื่อ parser id ที่ไฟล์นี้รองรับ
  extract_rates(pdf_bytes, bank)      -> dict | None
  (ทางเลือก) get_effective_date(pdf_bytes) -> str | None  ถ้า format วันที่ต่างจากค่าเริ่มต้น
"""

import io, json, os, random, re, time
from datetime import datetime

import pdfplumber

from .. import common
from ..common import log
from ._tablekit import (
    thai_skeleton, kw_in_line, line_equals_kw, row_values,
    pick_amount_tier, parse_tier_type_and_amount,
    find_joined_row, find_joined_section,
)
from . import _maxscan

PARSER_IDS = ["scb_passbook"]

DEFAULT_SECTION_KEYWORD = "เงินฝากประจำ แบบมีสมุด"
DEFAULT_DEPOSITOR = "บุคคลธรรมดา"

# ตารางประเภทลูกค้าของ SCB มี 13 คอลัมน์เสมอ — บรรทัดค่าที่ถอดได้ต้องมีครบ 13 token
# ถ้าไม่ครบ แปลว่า pdfplumber ถอด "-" หลุด → index คอลัมน์จะเลื่อน (อ่านผิดคอลัมน์แบบเงียบ ๆ)
# จึงปฏิเสธบรรทัดนั้นแทนที่จะคืนค่าที่อาจผิด
EXPECTED_COLUMNS = 13

# ─────────────────────────── Depositor column map (13 คอลัมน์ตายตัวของ SCB) ───────────────────────────
DEPOSITOR_COLUMNS: dict[int, list[str]] = {
    1:  ["บุคคลธรรมดา", "personal", "individual"],
    2:  ["นิติบุคคลทั่วไป", "juristic person"],
    3:  ["ราชการ", "government agency", "government"],
    4:  ["นิติบุคคลไม่แสวงหากำไรและบริษัทประกันภัย", "non-profit juristic person"],
    5:  ["สถาบันการเงิน", "financial institution"],
    6:  ["สถานศึกษา", "educational institution", "school"],
    7:  ["กองทุน", "fund"],
    8:  ["สหกรณ์", "cooperative"],
    9:  ["ผู้มีถิ่นฐานนอกประเทศบุคคลธรรมดา", "non-resident personal"],
    10: ["ผู้มีถิ่นฐานนอกประเทศนิติบุคคล", "non-resident juristic person"],
    11: ["ผู้มีถิ่นฐานนอกประเทศสถาบันการเงิน", "non-resident financial institution"],
    12: ["นิติบุคคลพิเศษ", "special juristic person"],
    13: ["บุคคลพิเศษ", "special person"],
}

_ALIAS_TO_COLUMN: dict[str, int] = {}
for _col, _aliases in DEPOSITOR_COLUMNS.items():
    for _alias in _aliases:
        _ALIAS_TO_COLUMN[thai_skeleton(_alias)] = _col


def resolve_depositor(value) -> int | None:
    """แปลงค่า depositor (คีย์เวิร์ดไทย/อังกฤษ หรือเลข 1-13) → หมายเลขคอลัมน์ หรือ None ถ้าไม่รู้จัก"""
    if isinstance(value, int):
        return value if 1 <= value <= 13 else None
    s = str(value).strip()
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 13 else None
    return _ALIAS_TO_COLUMN.get(thai_skeleton(s))


# ─────────────────────────── Row/section scanning ───────────────────────────
_TOP_LEVEL_RE = re.compile(r"^\d+\.\s+\S")


def _section_range(lines: list[str], section_kw: str) -> tuple[int | None, int]:
    """คืน (start, end) ของ section (start = บรรทัดหัวข้อ, end = boundary ถัดไป) หรือ (None, len)"""
    start = None
    for i, s in enumerate(lines):
        if kw_in_line(section_kw, s):
            start = i
            break
    if start is None:
        return None, len(lines)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _TOP_LEVEL_RE.match(lines[i]):
            end = i
            break
    return start, end


def _scan_tiers_and_pick(lines: list[str], tier_start: int, end: int,
                          row_line: str, amount_m: float | None) -> tuple[str | None, str]:
    """รับ row_line (หัวข้อที่พบแล้ว อาจเป็นบรรทัดเดียวหรือ join 2 บรรทัด) + ช่วงหา tier ลูก → (line, desc)"""
    if row_values(row_line):
        return row_line, "บรรทัดเดียว (ไม่มี tier วงเงิน)"

    tiers: list[tuple[str, int, str]] = []
    for i in range(tier_start, end):
        s = lines[i]
        if not kw_in_line("วงเงิน", s):
            break
        info = parse_tier_type_and_amount(s)
        if info and row_values(s):
            tiers.append((info[0], info[1], s))

    if not tiers:
        return None, ""
    if amount_m is None:
        return tiers[0][2], "ไม่ระบุวงเงิน (ใช้ tier แรกที่พบ)"
    return pick_amount_tier(tiers, amount_m)


def _find_row_line(lines: list[str], section_kw: str, row_kw: str,
                    amount_m: float | None) -> tuple[str | None, str]:
    """หาแถวข้อมูล (บรรทัดที่มีค่าตัวเลข 13 คอลัมน์) ที่ตรงกับ section + row keyword ที่กำหนด

    two-pass: pass 1 = จับรายบรรทัด (พฤติกรรมเดิมทุกตัวอักษร); pass 2 (เรียกเมื่อ pass 1 ล้มเหลว
    ทั้งกระบวน — หา section/row ไม่เจอ หรือเจอแต่ดึงค่าไม่ได้) = จับหัวข้อ/section ที่ pdfplumber
    ตัดเป็น 2 บรรทัด ด้วย find_joined_* — กัน false positive เพราะเข้า pass 2 เฉพาะตอน pass 1 ไม่ได้ผล

    ห้ามแก้ฟังก์ชันนี้เพื่อรองรับโหมด max — เป็น path ของโหมด 'cell' เดิมที่ต้อง regression-free
    เป๊ะ ๆ (ดู CLAUDE.md) โหมด max ใช้ _find_row_range() ด้านล่างแทน (หาแถวอย่างเดียว ไม่เลือก tier)"""
    # ── pass 1: รายบรรทัด ──
    start, end = _section_range(lines, section_kw)
    if start is not None:
        row_idx = None
        for i in range(start + 1, end):
            if line_equals_kw(row_kw, lines[i]):
                row_idx = i
                break
        if row_idx is None:
            for i in range(start + 1, end):
                if kw_in_line(row_kw, lines[i]):
                    row_idx = i
                    break
        if row_idx is not None:
            line, desc = _scan_tiers_and_pick(lines, row_idx + 1, end, lines[row_idx], amount_m)
            if line is not None:
                return line, desc

    # ── pass 2: หัวข้อ/section ถูกตัด 2 บรรทัด ──
    if start is not None:
        sec_start, sec_end = start + 1, end
    else:
        js = find_joined_section(lines, section_kw)
        if js is None:
            return None, ""
        sec_start = js + 1
        sec_end = len(lines)
        for i in range(sec_start, len(lines)):
            if _TOP_LEVEL_RE.match(lines[i]):
                sec_end = i
                break

    row_line, tier_start = find_joined_row(lines, sec_start, sec_end, row_kw)
    if row_line is None:
        return None, ""
    return _scan_tiers_and_pick(lines, tier_start, sec_end, row_line, amount_m)


# ─────────────────────────── โหมด max_tier/top_tier/max_all (①②③ "อัตราสูงสุด") ───────────────────────────
def _find_row_range(lines: list[str], section_kw: str,
                     row_kw: str) -> tuple[str | None, int | None, int | None]:
    """เหมือน _find_row_line แต่คืนแค่ 'แถวที่พบ + ช่วงหา tier ลูก' โดยไม่เลือก tier ด้วย amount_m
    (row_line, tier_start, end) — ใช้กับโหมด max ที่ต้องเก็บ tier ทุกตัว ไม่ใช่เลือกตัวเดียว
    ไม่แตะ/ไม่เรียก _scan_tiers_and_pick หรือ pick_amount_tier เลย จึงไม่กระทบ path โหมด cell"""
    start, end = _section_range(lines, section_kw)
    if start is not None:
        row_idx = None
        for i in range(start + 1, end):
            if line_equals_kw(row_kw, lines[i]):
                row_idx = i
                break
        if row_idx is None:
            for i in range(start + 1, end):
                if kw_in_line(row_kw, lines[i]):
                    row_idx = i
                    break
        if row_idx is not None:
            return lines[row_idx], row_idx + 1, end

    if start is not None:
        sec_start, sec_end = start + 1, end
    else:
        js = find_joined_section(lines, section_kw)
        if js is None:
            return None, None, None
        sec_start = js + 1
        sec_end = len(lines)
        for i in range(sec_start, len(lines)):
            if _TOP_LEVEL_RE.match(lines[i]):
                sec_end = i
                break

    row_line, tier_start = find_joined_row(lines, sec_start, sec_end, row_kw)
    if row_line is None:
        return None, None, None
    return row_line, tier_start, sec_end


def _collect_max_tiers(row_line: str, lines: list[str], tier_start: int, end: int) -> list[tuple]:
    """เก็บ tier ทุกตัวของแถวที่พบ (kind, lower_m, upper_m, desc, raw_line) ด้วย _maxscan.classify_tier_ext
    (กว้างกว่า parse_tier_type_and_amount ที่ path โหมด cell ใช้ — รองรับ up_to/between/above และฟอนต์
    ประกาศยุคเก่าที่ regex เดิมพลาด — ดู CLAUDE.md) แถวที่ไม่มี tier วงเงินเลย (ค่าอยู่บรรทัดเดียวกับหัวข้อ)
    ถือเป็น tier เดียว"""
    if row_values(row_line):
        return [("single", 0.0, None, "บรรทัดเดียว (ไม่มี tier วงเงิน)", row_line)]
    tiers: list[tuple] = []
    for i in range(tier_start, end):
        s = lines[i]
        if not (kw_in_line("วงเงิน", s) or kw_in_line("ยอดเงินฝาก", s)):
            break
        info = _maxscan.classify_tier_ext(s)
        if info and row_values(s):
            kind, lo, hi, desc = info
            tiers.append((kind, lo, hi, desc, s))
    return tiers


def _value_of(tier: tuple, col: int) -> str | None:
    """callback ของ _maxscan.select() — ดึงค่าดิบที่คอลัมน์ col จากบรรทัดดิบของ tier นั้น"""
    vals = row_values(tier[4])
    if len(vals) != EXPECTED_COLUMNS:
        return None
    return vals[col - 1]


def _extract_lines(pdf_bytes: bytes) -> list[str] | None:
    """ถอดข้อความทุกหน้าเป็น list ของบรรทัด (ตัดบรรทัดว่าง/หัวตาราง 'ประเภทลูกค้า' ทิ้ง)
    ใช้ร่วมกันทั้ง extract_rates() และ debug_tiers() — คืน None ถ้าอ่าน PDF ไม่ได้เลย"""
    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for raw in text.splitlines():
                    s = raw.strip()
                    if not s:
                        continue
                    if line_equals_kw("ประเภทลูกค้า", s) or line_equals_kw("ประเภทเงินฝาก", s):
                        continue
                    lines.append(s)
    except Exception as e:
        log.error(f"scb: อ่าน PDF ล้มเหลว: {e}")
        return None
    return lines


def extract_rates(pdf_bytes: bytes, bank: dict) -> dict | None:
    """อ่านค่าอัตราดอกเบี้ยตาม rate_targets (แต่ละตัวกำหนด section/row/depositor เอง)
    target ปกติ (ไม่ระบุ mode หรือ mode='cell') ใช้ path เดิม (amount_m เลือก tier เดียว) — ไม่แตะ
    target ที่ระบุ mode='max_tier'/'top_tier'/'max_all' ("อัตราสูงสุด" ①②③ — ดู CLAUDE.md) ใช้
    _collect_max_tiers() + _maxscan.select() แทน คนละ code path กับโหมด cell เดิมโดยสิ้นเชิง"""
    rate_targets = bank["rate_targets"]

    lines = _extract_lines(pdf_bytes)
    if lines is None:
        return None

    result: dict = {}
    tiers_used: dict = {}
    failed: list[str] = []
    # target ที่ตั้งค่าผิด/หาไม่เจอ จะถูก "ข้าม" ไม่ทำให้ทั้งธนาคารล้ม (target อื่นยังอ่านต่อได้)

    for target in rate_targets:
        key = target["key"]
        mode = target.get("mode", "cell")
        section_kw = target.get("section_keyword") or DEFAULT_SECTION_KEYWORD
        tenor = target.get("tenor_months")
        row_kw = target.get("row_keyword") or (f"{tenor} เดือน" if tenor else None)
        if not row_kw:
            log.error(f"extract_rates [{key}]: ไม่มี row_keyword และไม่มี tenor_months — ข้าม target นี้")
            failed.append(key); continue

        if mode == "cell":
            depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
            col = resolve_depositor(depositor_value)
            if col is None:
                log.error(f"extract_rates [{key}]: ไม่รู้จัก depositor '{depositor_value}' — ข้าม target นี้")
                failed.append(key); continue

            line, desc = _find_row_line(lines, section_kw, row_kw, target.get("amount_m"))
            if line is None:
                log.error(f"extract_rates [{key}]: ไม่พบแถวที่ตรง section='{section_kw}' row='{row_kw}' — ข้าม target นี้")
                failed.append(key); continue

            vals = row_values(line)
            if len(vals) != EXPECTED_COLUMNS:
                log.error(f"extract_rates [{key}]: บรรทัดมี {len(vals)} คอลัมน์ (คาดว่า {EXPECTED_COLUMNS}) "
                          f"— ถอดข้อมูลไม่น่าเชื่อถือ ข้าม target นี้กันอ่านผิดคอลัมน์: {line}")
                failed.append(key); continue

            raw_v = vals[col - 1]
            if raw_v == "-":
                log.error(f"extract_rates [{key}]: ไม่มีอัตราสำหรับคอลัมน์ {col} (แสดง '-') — ข้าม target นี้: {line}")
                failed.append(key); continue
            try:
                rate = float(raw_v)
            except ValueError:
                log.error(f"extract_rates [{key}]: ค่าไม่ใช่ตัวเลข: {raw_v!r} — ข้าม target นี้")
                failed.append(key); continue

        elif mode in _maxscan.MODES:
            row_line, tier_start, end = _find_row_range(lines, section_kw, row_kw)
            if row_line is None:
                log.error(f"extract_rates [{key}]: ไม่พบแถวที่ตรง section='{section_kw}' row='{row_kw}' — ข้าม target นี้")
                failed.append(key); continue

            col = None
            if mode != "max_all":
                depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
                col = resolve_depositor(depositor_value)
                if col is None:
                    log.error(f"extract_rates [{key}]: ไม่รู้จัก depositor '{depositor_value}' — ข้าม target นี้")
                    failed.append(key); continue

            tiers = _collect_max_tiers(row_line, lines, tier_start, end)
            rate, desc = _maxscan.select(mode, tiers, col, DEPOSITOR_COLUMNS, _value_of)
            if rate is None:
                log.error(f"extract_rates [{key}]: {desc} — ข้าม target นี้")
                failed.append(key); continue

        else:
            log.error(f"extract_rates [{key}]: ไม่รู้จัก mode '{mode}' — ข้าม target นี้")
            failed.append(key); continue

        result[key] = rate
        tiers_used[key] = desc
        log.info(f"  {target.get('label', key)}: {rate:.2f}%  ← {desc}")

    if not result:
        log.error("extract_rates: อ่านค่าไม่ได้เลยสักตัว (ทุก target ล้มเหลว)")
        return None
    if failed:
        log.warning(f"extract_rates: ข้าม {len(failed)} target ที่ตั้งค่าผิด/หาไม่เจอ: {', '.join(failed)} "
                    f"(อีก {len(result)} ตัวอ่านได้ปกติ)")

    result["tiers_used"] = tiers_used
    return result


def debug_tiers(pdf_bytes: bytes, bank: dict) -> list[dict] | None:
    """ใช้กับ CLI `--show-tiers SCB` — คืนต่อ target: tier ที่เก็บได้ (คำอธิบาย + ค่าทุกคอลัมน์)
    พร้อมผลลัพธ์ทั้ง 4 โหมด (cell เดิม ตาม amount_m, max_tier①, top_tier②, max_all③) โดยไม่สนใจว่า
    target นั้นตั้ง mode อะไรไว้จริง — เป็นเครื่องมือตรวจตาก่อนติ๊กใช้งานจริงในหน้า /config"""
    lines = _extract_lines(pdf_bytes)
    if lines is None:
        return None

    report: list[dict] = []
    for target in bank["rate_targets"]:
        key = target["key"]
        section_kw = target.get("section_keyword") or DEFAULT_SECTION_KEYWORD
        tenor = target.get("tenor_months")
        row_kw = target.get("row_keyword") or (f"{tenor} เดือน" if tenor else None)
        depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
        col = resolve_depositor(depositor_value)

        item: dict = {"key": key, "label": target.get("label", key), "depositor": depositor_value}
        if not row_kw or col is None:
            item["row_found"] = "ตั้งค่า row_keyword/tenor_months หรือ depositor ไม่ถูกต้อง"
            item["results"] = {}
            item["tiers"] = []
            report.append(item)
            continue

        row_line, tier_start, end = _find_row_range(lines, section_kw, row_kw)
        if row_line is None:
            item["row_found"] = None
            item["results"] = {}
            item["tiers"] = []
            report.append(item)
            continue
        item["row_found"] = row_line

        tiers = _collect_max_tiers(row_line, lines, tier_start, end)

        results: dict = {}
        cell_line, cell_desc = _find_row_line(lines, section_kw, row_kw, target.get("amount_m"))
        if cell_line is not None:
            vals = row_values(cell_line)
            if len(vals) == EXPECTED_COLUMNS and vals[col - 1] != "-":
                try:
                    results["cell"] = (float(vals[col - 1]), cell_desc)
                except ValueError:
                    pass
        for mode in _maxscan.MODES:
            m_col = None if mode == "max_all" else col
            rate, desc = _maxscan.select(mode, tiers, m_col, DEPOSITOR_COLUMNS, _value_of)
            if rate is not None:
                results[mode] = (rate, desc)
        item["results"] = results

        item["tiers"] = [
            {"desc": t[3],
             "col_values": {DEPOSITOR_COLUMNS[c][0]: (_value_of(t, c) or "-") for c in DEPOSITOR_COLUMNS}}
            for t in tiers
        ]
        report.append(item)

    return report


# ─────────────────────────── Full-year discovery (manual, ละเอียด) ───────────────────────────
# SCB เก็บประกาศเก่าไว้ที่ URL รูปแบบ:
#   https://www.scb.co.th/.../deposits/{ปี ค.ศ.}/deposit{พ.ศ. 2 หลักท้าย}-{เลขลำดับประกาศ 2 หลัก}.pdf
# เลขท้ายเป็น "เลขที่ประกาศของปี พ.ศ. นั้น" (ตรงกับ "ครั้งที่ N/พ.ศ." ที่พิมพ์ในตัวประกาศ) **ไม่ใช่เดือนปฏิทิน**
# — ยืนยันจากเนื้อหาจริง: deposit69-04→9เม.ย./69-05→28เม.ย./69-06→23พ.ค./69-07→29พ.ค.69 (เลขไม่ตรงเดือนในชื่อไฟล์)
#
# ⚠️ SCB มีระบบจำกัดอัตรา request (Incapsula) — ยิงถี่เกินไปโดนบล็อกชั่วคราวได้จริง (ทดสอบแล้ว: ยิง ~9
# request ไม่หน่วงเวลา ทำให้แม้แต่ URL ที่ใช้ตรวจสอบปกติทุกวันก็โดนบล็อกไปด้วยชั่วคราว — บล็อกเป็น
# rate-based ไม่ถาวร แต่ระยะเวลาไม่แน่นอน ~1-20 นาที) จึงต้อง:
#   1. หน่วงเวลา (+jitter) ระหว่างทุก request เสมอ (ห้ามลดโดยไม่ทดสอบผลกระทบก่อน)
#   2. ตรวจจับสัญญาณบล็อก (หน้า challenge มี "_Incapsula_Resource") → ลองปลดบล็อกด้วย
#      common.solve_incapsula_challenge หนึ่งครั้งต่อรอบสแกน ถ้ายังโดนซ้ำ = rate-limit จริง **หยุดทันที**
#      ไม่ใช่นับเป็น "ไม่พบไฟล์" ธรรมดา (ป้องกันยิงต่อตอนโดนบล็อกซึ่งจะยิ่งแย่ลง)
#   3. จำความคืบหน้า (resume state) ข้าม sequence ที่ยืนยันมีไฟล์แล้ว ไม่ยิง request ซ้ำทุกครั้งที่กด
REQUEST_DELAY_SEC = 6.0     # หน่วงเวลาฐานระหว่างแต่ละ request (บวก jitter เพิ่ม) ห้ามลดโดยไม่ทดสอบก่อน
REQUEST_JITTER_SEC = 2.0    # สุ่มเพิ่มเวลาหน่วง 0-2 วิ กัน pattern สม่ำเสมอเกินไป
MAX_SEQ_PER_YEAR = 30       # เพดานเลขลำดับสูงสุดที่ไล่ (SCB ประกาศจริง ~8-15 ครั้ง/ปี กันไว้เกินพอ)
MAX_CONSECUTIVE_MISSES = 3  # เจอ "ไม่พบ" ติดกันกี่ครั้งถึงหยุด (แปลว่าน่าจะหมดแล้ว — ไม่รวมกรณีโดนบล็อก)


def _discover_state_path(code: str) -> str:
    return os.path.join(common.OUTPUT_DIR, f"{code.lower()}_discover_state.json")


def _load_confirmed_seq(code: str, year: int) -> int:
    """คืนเลขลำดับสูงสุดที่ยืนยันแล้วว่ามีไฟล์จริง (ของปีที่ระบุ) — 0 ถ้ายังไม่เคยสแกน/คนละปี"""
    try:
        with open(_discover_state_path(code)) as f:
            state = json.load(f)
        if state.get("year") == year:
            return int(state.get("confirmed_through_seq", 0))
    except Exception:
        pass
    return 0


def _save_confirmed_seq(code: str, year: int, seq: int) -> None:
    try:
        with open(_discover_state_path(code), "w") as f:
            json.dump({"year": year, "confirmed_through_seq": seq}, f)
    except Exception as e:
        log.warning(f"scb: บันทึก discover_state ไม่ได้: {e}")


SITE_BASE = "https://www.scb.co.th"


def _new_session():
    from curl_cffi import requests as cffi_requests
    return cffi_requests.Session(impersonate="chrome")


def _fetch_raw(session, url: str, referer: str) -> bytes:
    """คืน raw bytes เสมอ (ไม่ทิ้งถ้าไม่ใช่ PDF) เพื่อให้ discover_year ตรวจจับสัญญาณบล็อกของ
    Incapsula ได้ (แยกจาก 'ไม่พบไฟล์' ธรรมดา) — ใช้ curl_cffi session ร่วมกันทั้งรอบสแกน
    เพื่อให้การปลดบล็อก (solve_incapsula_challenge) มีผลต่อ request ถัด ๆ ไปด้วย"""
    try:
        r = session.get(url, timeout=60,
                        headers={"Referer": referer, "Accept": "application/pdf,*/*"})
        return r.content
    except Exception as e:
        log.error(f"scb._fetch_raw exception: {e}")
        return b""


def _is_blocked(raw: bytes) -> bool:
    return b"Incapsula" in raw or b"_Incapsula_Resource" in raw


def discover_year(bank: dict, year: int | None = None) -> list[str]:
    """สแกนหาไฟล์ประกาศทั้งปี (ค.ศ.) จาก archive URL แบบเลขลำดับ (ไม่ใช่ไล่ทุกวันแบบ KBANK)
    ดาวน์โหลด+บันทึกเฉพาะไฟล์ที่ยังไม่มีในเครื่อง (เทียบจากวันที่จริงในเนื้อหา PDF ไม่ใช่เดาจากชื่อไฟล์)
    หน่วงเวลาระหว่าง request เสมอกันโดนบล็อก, หยุดทันทีถ้าเจอสัญญาณบล็อก, และข้าม sequence ที่เคย
    ยืนยันแล้วในรอบก่อนหน้า (resume — ไม่โหลดซ้ำ) คืนรายชื่อไฟล์ที่บันทึกใหม่ในรอบนี้"""
    code = bank["code"]
    yr = year or datetime.now().year
    be_suffix = (yr + 543) % 100
    referer = bank.get("referer", "")

    pdf_dir, _ = common.get_bank_paths(code)
    os.makedirs(pdf_dir, exist_ok=True)
    existing_dates = set()
    for f in os.listdir(pdf_dir):
        m = re.match(rf"{code.lower()}_deposit_(\d{{4}}-\d{{2}}-\d{{2}})\.pdf$", f)
        if m:
            existing_dates.add(m.group(1))

    confirmed_seq = _load_confirmed_seq(code, yr)
    start_seq = confirmed_seq + 1

    saved: list[str] = []
    misses = 0
    blocked = False
    session = _new_session()
    tried_unblock = False  # ปลดบล็อก Incapsula ได้หนึ่งครั้งต่อรอบสแกน — โดนซ้ำหลังปลดแล้ว = rate-limit จริง
    log.info(f"scb.discover_year: สแกนปี {yr} (พ.ศ. {yr + 543}) เลขลำดับ {start_seq}-{MAX_SEQ_PER_YEAR} "
             f"(ข้าม 1-{confirmed_seq} ที่ยืนยันแล้ว) หน่วง ~{REQUEST_DELAY_SEC}-"
             f"{REQUEST_DELAY_SEC + REQUEST_JITTER_SEC:.0f}s/request — ใช้เวลานาน")

    for seq in range(start_seq, MAX_SEQ_PER_YEAR + 1):
        url = (f"{SITE_BASE}/content/media/personal-banking/rates-fees/deposits/"
               f"{yr}/deposit{be_suffix:02d}-{seq:02d}.pdf")
        raw = _fetch_raw(session, url, referer)
        time.sleep(REQUEST_DELAY_SEC + random.uniform(0, REQUEST_JITTER_SEC))

        if _is_blocked(raw) and not tried_unblock:
            tried_unblock = True
            # ทางที่ 1: โหลดสคริปต์ปลดบล็อกใน session เดิม (ได้ผลกับ Incapsula แบบ KTB)
            if common.solve_incapsula_challenge(session, raw.decode("utf-8", "replace"), SITE_BASE):
                time.sleep(REQUEST_DELAY_SEC + random.uniform(0, REQUEST_JITTER_SEC))
                raw = _fetch_raw(session, url, referer)
            # ทางที่ 2: challenge ของ SCB ผูกกับ session (ทดสอบแล้ว: ปลดใน session เดิมไม่หลุด
            # แต่ session ใหม่ผ่านทันที) — เปิด session ใหม่ cookie ใหม่ แล้วลองอีกครั้งเดียว
            if _is_blocked(raw):
                log.info("scb.discover_year: ปลดบล็อกใน session เดิมไม่สำเร็จ — เปิด session ใหม่ลองซ้ำ")
                session = _new_session()
                time.sleep(REQUEST_DELAY_SEC + random.uniform(0, REQUEST_JITTER_SEC))
                raw = _fetch_raw(session, url, referer)

        if _is_blocked(raw):
            log.warning(f"scb.discover_year: โดน rate-limit บล็อกที่เลขลำดับ {seq:02d} (ปลดบล็อกไม่สำเร็จ) "
                        f"— หยุดสแกนทันที (รอสักครู่ค่อยกดใหม่ ความคืบหน้าที่ทำได้แล้วถูกบันทึกไว้)")
            blocked = True
            break

        if not raw or raw[:4] != b"%PDF":
            misses += 1
            if misses >= MAX_CONSECUTIVE_MISSES:
                log.info(f"scb.discover_year: ไม่พบติดกัน {misses} ครั้ง (ที่เลขลำดับ {seq}) — หยุดสแกนปีนี้")
                break
            continue
        misses = 0

        # ยืนยันแล้วว่า sequence นี้มีไฟล์จริง — เลื่อน confirmed_seq ทันที (กันเสียความคืบหน้าถ้าโดนบล็อกถัดไป)
        confirmed_seq = seq
        _save_confirmed_seq(code, yr, confirmed_seq)

        eff_date = common.get_effective_date(raw)
        if eff_date is None:
            log.warning(f"scb.discover_year: seq={seq:02d} ดาวน์โหลดได้แต่หาวันที่ในเนื้อหาไม่เจอ — ข้าม")
            continue
        # URL อยู่ใต้โฟลเดอร์ปี yr บนเว็บ แต่ "วันที่มีผล" ในเนื้อหาอาจเป็นคนละปี (ประกาศออกปลายปีก่อน
        # แต่มีผลปีถัดไป ฯลฯ) — ต้องกรองซ้ำด้วยวันที่จริง ไม่ใช่เชื่อแค่ตำแหน่ง URL
        if not common.is_date_in_year(eff_date, yr):
            log.info(f"scb.discover_year: seq={seq:02d} วันที่มีผล {eff_date} ไม่ใช่ปี {yr} — ข้าม (ไม่นับเป็นไฟล์ใหม่)")
            continue
        if eff_date in existing_dates:
            continue

        fname = f"{code.lower()}_deposit_{eff_date}.pdf"
        with open(os.path.join(pdf_dir, fname), "wb") as f:
            f.write(raw)
        saved.append(fname)
        existing_dates.add(eff_date)
        log.info(f"scb.discover_year: พบและบันทึก {fname} (seq={seq:02d})")

    if not blocked:
        _save_confirmed_seq(code, yr, confirmed_seq)  # เซฟรอบสุดท้าย (เผื่อจบ loop ด้วย miss-streak)

    log.info(f"scb.discover_year: เสร็จสิ้น — พบไฟล์ใหม่ {len(saved)} ไฟล์: {', '.join(saved) or '-'} "
             f"(ยืนยันถึงเลขลำดับ {confirmed_seq})")
    return saved
