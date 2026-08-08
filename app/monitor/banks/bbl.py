#!/usr/bin/env python3
"""
banks/bbl.py — ตัวอ่านอัตราดอกเบี้ยของ ธนาคารกรุงเทพ (BBL)
parser id: "bbl"

ต่างจาก parser ธนาคารอื่นอย่างมีนัยสำคัญ: **PDF ประกาศของ BBL เป็นภาพสแกน** (1 ภาพ/หน้า ไม่มี text layer
เลย — pdfplumber.extract_text() คืนค่าว่าง) จึงต้อง render หน้า 1 เป็นภาพแล้ว OCR ด้วย tesseract (tha+eng)
ต้องติดตั้ง tesseract + ภาษาไทยก่อนใช้งาน:
  macOS : brew install tesseract tesseract-lang
  Debian: apt-get install tesseract-ocr tesseract-ocr-tha

โครงตาราง (ตรวจแล้วกับประกาศปี 2023-2026 — เหมือนกันทุกฉบับ):
  - ตารางอัตราทั้งหมดอยู่ "หน้า 1" หน้าเดียว (หน้าที่เหลือเป็นหมายเหตุ/เงื่อนไข)
  - 9 คอลัมน์ประเภทลูกค้า เรียงคงที่: 1 บุคคลธรรมดา, 2 นิติบุคคลทั่วไป, 3 หน่วยงานราชการ,
    4 บริษัทประกันภัย/ประกันชีวิต, 5 นิติบุคคลที่ไม่แสวงหากำไร, 6 สถาบันการเงิน,
    7 กองทุนฯ และสหกรณ์ออมทรัพย์, 8 ผู้มีถิ่นฐานนอกประเทศ-บุคคลธรรมดา, 9 ผู้มีถิ่นฐานนอกประเทศ-นิติบุคคล
  - เงินฝากประจำอยู่ใต้หัวข้อ "ประจำ" แถวย่อยรูปแบบ "X.Y ระยะเวลาการฝาก N เดือน"
  - ผลิตภัณฑ์อื่น (สะสมทรัพย์ ฯลฯ) เป็นแถวชื่อผลิตภัณฑ์ตรง ๆ — ตั้ง row_keyword ใน rate_targets เพื่ออ่าน
  - **tier วงเงิน**: บางแถวแบ่ง tier บางแถวไม่แบ่ง และเปลี่ยนไปตามปีด้วย (เช่น สะสมทรัพย์ ปี 2023-2024
    แบ่งเป็น "น้อยกว่า 10 ล้านบาท"/"10 ล้านบาทขึ้นไป" แต่ปี 2026 เป็นอัตราเดียว; e-Savings แบ่งทุกปี;
    เงินฝากประจำตอนนี้ไม่แบ่ง) — parser นี้จึงรองรับ tier กับ **ทุกแถวเสมอ**: ถ้าแถวมีค่าอยู่บนบรรทัด
    เดียวกันก็ใช้เลย ถ้าเป็นหัวข้อเปล่าก็ไล่หาบรรทัดลูก "- วงเงิน..." แล้วเลือกตาม amount_m

รองรับ target โหมด max_tier/top_tier/max_all (①②③ "อัตราสูงสุด" — ดู CLAUDE.md) เหมือน SCB/KTB/BAY/KBANK
โดยเส้นทาง cell เดิมข้างบนไม่ถูกแตะเลยสักบรรทัด (`_collect_max_tiers`/`_make_value_of` เป็นฟังก์ชันคู่ขนาน
ใหม่ ดูหัวข้อ "โหมด max_tier/top_tier/max_all" ก่อน `_tenor_unit`) **ต่างจาก SCB/KTB/BAY/KBANK ตรงที่ค่า
โหมด max ต้องผ่านการ "โหวต" ข้าม OCR variant ก่อนยอมรับ** (≥2 variant อ่านตรงกัน — ดู `VOTE_MIN` และ
docstring ของ `extract_rates`) เพราะพิสูจน์แล้วว่า OCR อ่านค่าสูงสุด "สูงเกินจริง" ได้จริงและผ่าน
`MIN_WORD_CONF` ปกติทุกอย่าง (เช่น 0.75 → OCR อ่านเป็น 0,76 conf 81) ถ้าเชื่อ variant แรกเหมือน cell
ค่าที่ผิดจะกลายเป็นคำตอบทันที — โหวตแก้ได้เพราะ variant อื่นอ่านถูก 2 ใน 3 ครั้ง เคสทองที่พิสูจน์ ①≠②
ในไฟล์ปัจจุบันเลย (ไม่ต้องย้อนหาไฟล์เก่า): "7. สะสมทรัพย์ e-Savings" แบ่ง tier ไม่เกิน 1 ล้านบาท = 1.25
กับ ส่วนที่เกิน 1 ล้านบาท = 0.35 → ① = 1.25, ② = 0.35

หลักการ anchoring ที่ต้องระวัง (ทั้งหมดเจอจริงตอนทดสอบ 8 ฉบับ — อย่ารื้อโดยไม่ทดสอบซ้ำ):
  - **ห้าม anchor ด้วยเลขข้อ** เพราะเลื่อนตามปี (12 เดือน = ข้อ 8.8 ปี 2023 แต่ = 9.9 ปี 2026)
  - หัวข้อ "ประจำ" ต้องเทียบ skeleton แบบ "เท่ากันทั้งบรรทัด" ไม่ใช่ substring ไม่งั้นชน "ประจำขวัญบัวหลวง"
  - หมวดหลัง ๆ (ประจำขวัญบัวหลวง / สินมัธยะทรัพย์ทวี / บัตรเงินฝาก) มีแถว "N เดือน" ซ้ำ → ต้องตัดที่ขอบหมวด
  - แถว "7 วัน" กับ "7 เดือน" อยู่หมวดเดียวกัน → ต้องเช็คหน่วยหลังตัวเลข ไม่ใช่ดูแค่ตัวเลข
  - OCR เพี้ยนที่พบจริง: เลขข้อ "8." → "8,", "9.8" → "9.B", ค่า "0.30" → "0,30"/"030",
    เดือน "ธันวาคม" → "ชันวาคม", หน่วย "เดือน" → "Wau" (อักษรละติน) — โค้ดด้านล่างรับมือทุกเคส

Bot-protection: เว็บ BBL บล็อก TLS fingerprint ของ curl ธรรมดา (HTTP/2 INTERNAL_ERROR)
→ ต้องตั้ง "fetch_mode": "impersonate" ใน banks_config.json และใช้ curl_cffi ทุก request ที่นี่
"""

import contextlib
import contextvars
import csv as csv_mod
import hashlib
import io
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import quote

import pdfplumber
from PIL import ImageFilter

from .. import common
from ..common import log, THAI_MONTHS
from ._tablekit import thai_skeleton
from . import _maxscan

PARSER_IDS = ["bbl"]

SITE_BASE = "https://www.bangkokbank.com"
RATES_PAGE_URL = f"{SITE_BASE}/th-TH/Personal/Other-Services/View-Rates/Deposit-Interest-Rates"

REQUEST_DELAY_SEC = 2.0      # ไม่พบ challenge page แบบ SCB/KTB แต่หน่วงไว้เพื่อความสุภาพ
REQUEST_JITTER_SEC = 1.0

OCR_DPI = 300                # ต้นฉบับสแกน ~200 DPI คมชัด — 300 DPI ให้ conf ~90 ขึ้นไปสม่ำเสมอ
OCR_TIMEOUT_SEC = 180
MIN_WORD_CONF = 60.0         # ค่าที่อ่านได้จริงมี conf 76-95; ต่ำกว่า 60 = ไม่น่าเชื่อถือ ทิ้ง
MIN_CLUSTER_MEMBERS = 5      # คอลัมน์จริงมีค่าหลายสิบตัว — cluster เล็กกว่านี้คือ noise จาก OCR
# เพดานค่าที่ยอมรับจากการอ่านหนึ่งครั้ง — เดิม 10.0 กว้างเกินจนกันเคสจริงไม่อยู่: ประกาศ 30 ก.ค. 2568
# OCR variant#2 อ่าน `0.60` (กองทุน 12 เดือน) เป็น `6.60` ด้วย conf ปกติ แล้วชนะเพราะมาก่อน variant ที่
# อ่านถูก 5.0 ตัดเคสนี้ทิ้งได้โดยยังเหลือที่ว่างเยอะ — อัตราสูงสุดที่ BBL เคยประกาศในตารางนี้คือ 3.40
# (ประจำบัวหลวงซุปเปอร์โบนัส) ค่าที่เกิน 5 จึงเป็นสัญญาณว่า OCR อ่านหลักแรกเกินมา ไม่ใช่อัตราจริง
MAX_PLAUSIBLE_RATE = 5.0

# ค่า 0.00 ที่อ่านได้ถือเป็น "ค่าสำรอง" ไม่ใช่คำตอบทันที — variant ที่อ่านตัวเลขหลุดหายทั้งตัวมักคืน 0.00
# (เจอจริง: 30 ก.ค. 2568 variant#2 อ่าน `0.90` เป็น `0.00` ส่วน variant#3/#4 อ่านถูกทั้งคู่) จึงเก็บไว้ก่อน
# แล้วไล่ variant ที่เหลือต่อ ถ้ามีตัวไหนอ่านได้ค่าที่ไม่ใช่ 0.00 ให้ตัวนั้นชนะ — ครบทุก variant แล้วยังมี
# แต่ 0.00 ค่อยยอมรับ 0.00 (BBL ประกาศ 0.00 จริงในบางแถว เช่น กระแสรายวัน จึงห้ามตัดทิ้งเด็ดขาด)
SUSPECT_RATE = 0.0

# target โหมด max_tier/top_tier/max_all (①②③ "อัตราสูงสุด") เสี่ยงต่อ OCR อ่าน "สูงเกินจริง" เป็นพิเศษ
# (พิสูจน์แล้วกับไฟล์จริง — ดู CLAUDE.md: variant[0] อ่าน 0.75 เป็น 0,76 conf 81 ผ่านเกณฑ์ MIN_WORD_CONF
# ปกติทุกอย่าง) จึงต้องให้ ≥2 OCR variant อ่าน "ตรงกัน" ก่อนยอมรับค่า (ไม่ใช่แค่ variant แรกที่อ่านได้แบบ
# cell) — ต่ำกว่านี้ปล่อยว่างไว้ ไม่เดา (ดู extract_rates ส่วนโหวต)
VOTE_MIN = 2

# ไฟล์สแกนคุณภาพต่ำ (พบจริง: ขนาด 300-400KB เทียบกับ 1.1-1.6MB ของไฟล์ปกติ) ทำให้ tesseract อ่าน "ป้ายชื่อ"
# แถว/หมวดเพี้ยนได้ (ตัวเลขอัตรามักอ่านถูก แค่ป้ายที่ผิด) — ไม่มี config เดียวที่ชนะทุกไฟล์ที่พังจึงลองไล่ทีละ
# variant แล้วเติมเฉพาะ target ที่ variant ก่อนหน้ายังอ่านไม่ได้ (ดู extract_rates)
#
# **ห้ามสลับลำดับ/แก้ variant[0] โดยไม่ทดสอบ CSV diff ใหม่** — variant[0] ต้องตรงกับพฤติกรรมเดิมเป๊ะ
# (ไฟล์ปกติ 13/19 ไฟล์ที่ทดสอบ ต้องได้ค่าเดิม 100% เพราะ remaining ว่างตั้งแต่ variant[0] จึงไม่มีการลอง
# variant อื่นเลย) ลำดับ variant ถัดจากนั้นมาจากการวัดผลจริงกับไฟล์ที่พัง (ก.ค. 2568) — ดู CLAUDE.md
#
# ช่องที่ 4 ของทูเพิล (มีหรือไม่มีก็ได้) = ชื่อ preprocess ใน _PREPROCESSORS — เพิ่มมาเพื่อไฟล์ที่สแกนเป็น
# **ขาว-ดำ 1 บิต (CCITTFax)** ซึ่งเป็นต้นเหตุจริงของไฟล์ที่อ่านป้ายไม่ออก (วัดแล้ว: ไฟล์ที่อ่านได้ปกติทุก
# ไฟล์เป็น JPEG 8 บิต มีพิกเซลกลางโทนที่ขอบตัวอักษร 1.3-1.8% ส่วนไฟล์ที่พังมี 0.00% — ความละเอียดต้นทาง
# เท่ากันทั้งคู่ ~283 DPI ไม่ได้เอียง/เบลอต่างกัน) ภาพ 1 บิตถูก threshold แข็งจนสระ/วรรณยุกต์ขาดและเส้น
# ขอบตารางแตกเป็นเม็ด noise — median filter ลบเม็ดพวกนั้นโดยคงขอบตัวอักษรไว้ ตัวเลขอัตราในไฟล์เหล่านี้
# OCR อ่านถูกอยู่แล้วตั้งแต่ variant[0] ที่พังคือ "ป้ายแถว/หมวด" เท่านั้น (เช่น "ระยะเวลา" → "ระแหเวลา",
# "9. ประจำ" → "จ. ประจำ") จึงหาแถวไม่เจอแล้วทิ้งทั้งแถว
OCR_VARIANTS: list[tuple] = [
    ("tha+eng", 6, 300),   # ค่าเดิม/ค่าเริ่มต้น
    ("tha", 6, 300),       # กู้ป้ายที่ OCR ปนอักษรละตินมั่ว (เช่น "สะสมทรัพย์" → "avauwiwed")
    ("tha+eng", 4, 300),   # psm 4 (single column) ช่วยไฟล์ที่ตารางเพี้ยนทั้งหน้า
    ("tha+eng", 6, 400),   # DPI สูงขึ้น ช่วยไฟล์สแกนเบลอ/ตัวอักษรเล็ก
    ("tha+eng", 4, 500, "denoise"),   # สแกน 1 บิต: median filter + DPI สูง (ดูคอมเมนต์ข้างบน)
]

DEFAULT_DEPOSITOR = "บุคคลธรรมดา"
EXPECTED_COLUMNS = 9

# ─────────────────────────── Buffer เหตุผลระหว่างไล่ OCR variant (ตัดเสียงรบกวน log) ───────────────────────────
# extract_rates() ไล่ลอง OCR_VARIANTS หลายชุด — ชุดก่อน ๆ ที่หา target ไม่เจอ/อ่านไม่ได้ไม่ใช่ error จริงเสมอ
# ไป เพราะชุดถัดไปมักกู้ค่าคืนได้ (ดู docstring extract_rates) log.error จากทุกจุดที่เกิด "ต่อ variant ต่อ
# target" (ใน _locate_row/_extract_targets) จึงต้องผ่าน _attempt_error() แทนการยิง log.error ตรง ๆ:
#   - ถ้า extract_rates() เปิด buffer ไว้ (_ATTEMPT_BUFFER ไม่ใช่ None) → เก็บเหตุผลใส่ buffer ต่อ key แล้ว
#     log.debug() แทน (ยังอยู่ในไฟล์ log ให้ดีบั๊กได้ เพราะ handler ไฟล์รับ DEBUG) ไม่รบกวนระดับ ERROR/WARNING
#   - ถ้าไม่ได้เปิด buffer (เช่น debug_tiers() ที่ตั้งใจไม่เปิด — ต้องการพฤติกรรม log เดิมทุกตัวอักษร
#     เพื่อตรวจตาก่อนติ๊กใช้จริง) → log.error() ตรง ๆ เหมือนเดิมทุกประการ
# ContextVar (ไม่ใช่ตัวแปร global ธรรมดา) เพราะ backfill/main รันหลายธนาคารขนานกันด้วย ThreadPool
_ATTEMPT_BUFFER: contextvars.ContextVar[dict[str, list[str]] | None] = contextvars.ContextVar(
    "bbl_attempt_buffer", default=None)


@contextlib.contextmanager
def _attempt_buffering():
    """เปิด buffer เก็บเหตุผลระหว่างไล่ OCR variant — ครอบเฉพาะใน extract_rates() (ไม่ใช่ debug_tiers())"""
    token = _ATTEMPT_BUFFER.set({})
    try:
        yield
    finally:
        _ATTEMPT_BUFFER.reset(token)


def _attempt_error(key: str, msg: str) -> None:
    """log.error สำหรับ path "ต่อ variant ต่อ target" — key="" ใช้กับปัญหาระดับไฟล์ที่เกิดต่อ variant
    เหมือนกันแต่ไม่ผูกกับ target ตัวใดตัวหนึ่ง (เช่น จับคอลัมน์ได้ไม่ครบ) ดูหมายเหตุเหนือ _ATTEMPT_BUFFER"""
    buf = _ATTEMPT_BUFFER.get()
    if buf is not None:
        buf.setdefault(key, []).append(msg)
        log.debug(msg)
    else:
        log.error(msg)


def _buffered_reasons(key: str, limit: int = 3) -> str:
    """เหตุผลที่สะสมไว้ของ key นี้ระหว่างไล่ variant (ตัดซ้ำ จำกัดจำนวน) + เหตุผลระดับไฟล์ (key="") ต่อท้าย
    — ใช้พ่วงท้าย log.error สรุปตอนจบ extract_rates() เมื่อ key นั้นสุดท้ายอ่านไม่ได้จริง ๆ คืนสตริงว่างถ้า
    ไม่มี buffer เปิดอยู่หรือไม่มีเหตุผลอะไรเก็บไว้เลย (ไม่มี prefix — ผู้เรียกจัดรูปประโยคเอง)"""
    buf = _ATTEMPT_BUFFER.get()
    if buf is None:
        return ""
    seen: list[str] = []
    for msg in buf.get(key, []) + buf.get("", []):
        if msg not in seen:
            seen.append(msg)
        if len(seen) >= limit:
            break
    if not seen:
        return ""
    return " / ".join(seen)


# ─────────────────────────── Depositor column map (9 คอลัมน์ตายตัวของ BBL) ───────────────────────────
DEPOSITOR_COLUMNS: dict[int, list[str]] = {
    1: ["บุคคลธรรมดา", "บุคคล", "personal", "individual"],
    2: ["นิติบุคคลทั่วไป", "นิติบุคคล", "juristic person"],
    3: ["หน่วยงานราชการ", "ราชการ", "government"],
    4: ["บริษัทประกันภัยบริษัทประกันชีวิต", "บริษัทประกันภัย", "ประกันชีวิต", "ประกัน", "insurance"],
    5: ["นิติบุคคลที่ไม่แสวงหากำไร", "ไม่แสวงหากำไร", "มูลนิธิ", "non-profit"],
    6: ["สถาบันการเงิน", "การเงิน", "financial institution"],
    7: ["กองทุนและสหกรณ์ออมทรัพย์", "กองทุน", "สหกรณ์ออมทรัพย์", "fund"],
    8: ["ผู้มีถิ่นฐานอยู่นอกประเทศบุคคลธรรมดา", "นอกประเทศบุคคลธรรมดา", "non-resident personal"],
    9: ["ผู้มีถิ่นฐานอยู่นอกประเทศนิติบุคคล", "นอกประเทศนิติบุคคล", "non-resident juristic person"],
}

_ALIAS_TO_COLUMN: dict[str, int] = {}
for _col, _aliases in DEPOSITOR_COLUMNS.items():
    for _alias in _aliases:
        _ALIAS_TO_COLUMN.setdefault(thai_skeleton(_alias), _col)


def resolve_depositor(value) -> int | None:
    """แปลงค่า depositor (คีย์เวิร์ดไทย/อังกฤษ หรือเลข 1-9) → หมายเลขคอลัมน์ หรือ None ถ้าไม่รู้จัก"""
    if isinstance(value, int):
        return value if 1 <= value <= EXPECTED_COLUMNS else None
    s = str(value).strip()
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= EXPECTED_COLUMNS else None
    return _ALIAS_TO_COLUMN.get(thai_skeleton(s))


# ─────────────────────────── OCR ───────────────────────────
# ค่าอัตรา: OCR อาจอ่านจุดเป็นจุลภาค ("0,30") หรือทำจุดหล่น ("030"/"145") — ค่าจริงเป็น X.YY เสมอ
_VALUE_RE = re.compile(r"^(\d)[.,]?(\d{2})$")


def _value_of(token: str) -> float | None:
    m = _VALUE_RE.match(token)
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def _denoise(img):
    """grayscale → median filter 3x3 — ลบเม็ด noise ของสแกน 1 บิตโดยคงขอบตัวอักษรไว้
    (วัดแล้ว: รัศมี 5 แรงเกินไป ตัวเลขเริ่มเพี้ยน 0.90→9.90; autocontrast/otsu/adaptive/sharpen ไม่ช่วยเลย)"""
    return img.convert("L").filter(ImageFilter.MedianFilter(3))


_PREPROCESSORS = {"denoise": _denoise}


def _render_page1_png(pdf_bytes: bytes, top_frac: float | None = None, dpi: int = OCR_DPI,
                      preprocess: str | None = None) -> bytes | None:
    """render หน้า 1 เป็น PNG (top_frac = ครอปเฉพาะสัดส่วนบนของหน้า เช่น 0.25 สำหรับหัวกระดาษ)
    preprocess = ชื่อใน _PREPROCESSORS (None = ภาพดิบเหมือนเดิมทุกประการ)"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            if top_frac:
                page = page.crop((0, 0, page.width, page.height * top_frac))
            img = page.to_image(resolution=dpi).original
    except Exception as e:
        log.error(f"bbl: render PDF เป็นภาพไม่สำเร็จ: {e}")
        return None
    fn = _PREPROCESSORS.get(preprocess) if preprocess else None
    if fn is not None:
        img = fn(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ocr_words(png_bytes: bytes, lang: str = "tha+eng", psm: int = 6, dpi: int = OCR_DPI) -> list[dict] | None:
    """OCR ภาพด้วย tesseract → รายการคำพร้อมพิกัด/ความมั่นใจ (TSV mode)
    lang/psm/dpi รับพารามิเตอร์ได้ — extract_rates ไล่ลอง OCR_VARIANTS หลายชุดกับไฟล์ที่อ่านป้ายไม่ออก"""
    # tesseract แตก thread เองด้วย OpenMP — เมื่อ backfill รันหลายธนาคารขนานกัน thread จะแย่ง CPU
    # กันจนแต่ละตัวช้าลง (บนเครื่องเล็กอาจถึงขั้นชน OCR_TIMEOUT_SEC) บังคับให้ 1 thread ต่อ process
    # แล้วปล่อยให้ ThreadPool ข้างนอกเป็นตัวจัดการความขนานแทน
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "--dpi", str(dpi),
             "-l", lang, "--psm", str(psm), "tsv"],
            input=png_bytes, capture_output=True, timeout=OCR_TIMEOUT_SEC, env=env,
        )
    except FileNotFoundError:
        log.error("bbl: ไม่พบคำสั่ง tesseract — PDF ของ BBL เป็นภาพสแกน ต้องใช้ OCR "
                  "(macOS: brew install tesseract tesseract-lang / "
                  "Debian: apt-get install tesseract-ocr tesseract-ocr-tha)")
        return None
    except subprocess.TimeoutExpired:
        log.error(f"bbl: tesseract ทำงานเกิน {OCR_TIMEOUT_SEC}s — ข้าม")
        return None
    if proc.returncode != 0:
        log.error(f"bbl: tesseract ล้มเหลว (exit {proc.returncode}): "
                  f"{proc.stderr.decode('utf-8', 'replace')[:200]}")
        return None

    words: list[dict] = []
    reader = csv_mod.DictReader(io.StringIO(proc.stdout.decode("utf-8", "replace")),
                                delimiter="\t", quoting=csv_mod.QUOTE_NONE)
    for row in reader:
        if row.get("level") != "5":     # level 5 = คำเดี่ยว (ระดับอื่นเป็น block/paragraph/line)
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            left, top, width = int(row["left"]), int(row["top"]), int(row["width"])
            words.append({"text": text, "conf": float(row["conf"]),
                          "top": top, "cx": left + width / 2, "left": left,
                          "lid": (row["block_num"], row["par_num"], row["line_num"])})
        except (KeyError, ValueError):
            continue
    return words or None


def _group_lines(words: list[dict]) -> list[dict]:
    """จัดคำเป็นบรรทัดตาม line id ของ tesseract (ตัด '|' ที่ OCR อ่านจากเส้นตารางทิ้ง)"""
    by_line: dict = {}
    for w in words:
        by_line.setdefault(w["lid"], []).append(w)
    lines: list[dict] = []
    for ws in by_line.values():
        content = sorted([w for w in ws if w["text"] != "|"], key=lambda w: w["left"])
        if not content:
            continue
        lines.append({"words": content,
                      "text": " ".join(w["text"] for w in content),
                      "top": min(w["top"] for w in content)})
    lines.sort(key=lambda l: l["top"])
    return lines


# OCR หน้าเดียวกันถูกเรียกซ้ำใน run_bank (effective_date แล้วตามด้วย extract_rates) — cache ไว้กันทำซ้ำ
# key รวม variant ด้วย เพราะไฟล์เดียวกันให้ lines ต่างกันตาม (lang, psm, dpi) ที่ใช้อ่าน
# มี lock เพราะ backfill/main รันหลายธนาคารขนานกันด้วย ThreadPool (clear() + set ไม่ atomic)
_LINES_CACHE: dict[tuple[str, tuple], list[dict]] = {}
_LINES_CACHE_LOCK = threading.Lock()


def _page1_lines(pdf_bytes: bytes, variant: tuple[str, int, int] = OCR_VARIANTS[0]) -> list[dict] | None:
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    cache_key = (sha, variant)
    with _LINES_CACHE_LOCK:
        if cache_key in _LINES_CACHE:
            return _LINES_CACHE[cache_key]
    lang, psm, dpi = variant[:3]
    png = _render_page1_png(pdf_bytes, dpi=dpi, preprocess=variant[3] if len(variant) > 3 else None)
    if png is None:
        return None
    words = _ocr_words(png, lang=lang, psm=psm, dpi=dpi)
    if not words:
        log.error(f"bbl: OCR ไม่ได้ข้อความจากหน้า 1 เลย (variant {lang}/psm{psm}/{dpi}dpi)")
        return None
    lines = _group_lines(words)
    with _LINES_CACHE_LOCK:
        _LINES_CACHE.clear()      # เก็บแค่ (ไฟล์, variant) ล่าสุดพอ (backfill วนหลายไฟล์ ไม่ต้องกินแรม)
        _LINES_CACHE[cache_key] = lines
    return lines


# ─────────────────────────── Table anchoring ───────────────────────────
# เลขข้อ: OCR อ่านเครื่องหมายหลังเลขข้อเพี้ยนได้ ("8. ประจำ" → "8, ประจำ", "2. สะสมทรัพย์" → "(2: สะสมทรัพย์")
_ITEM_RE = re.compile(r"^[^\dก-ฮa-zA-Z]*(\d{1,2})[.,:;](\d{1,2})?")
_TOPLEVEL_RE = re.compile(r"^[^\dก-ฮa-zA-Z]*\d{1,2}[.,:;](?!\d)")

_SK_MONTH = thai_skeleton("เดือน")
_SK_DAY = thai_skeleton("วัน")
_SK_ROW = thai_skeleton("ระยะเวลาการฝาก")
_SK_EFFECTIVE = thai_skeleton("มีผลบังคับใช้")
_SK_LIMIT = thai_skeleton("วงเงิน")


def _data_words(line: dict) -> list[dict]:
    """token ค่าอัตราในบรรทัด — ข้าม token แรกเสมอเพราะเป็นเลขข้อ ("9.11" หน้าตาเหมือนค่าอัตรา)"""
    return [w for w in line["words"][1:] if _value_of(w["text"]) is not None]


def _label_sk(line: dict) -> str:
    """skeleton ของ "ส่วนชื่อแถว" (ข้อความก่อนค่าอัตราตัวแรก) หลังตัดเลขข้อทิ้ง
    ใช้เทียบชื่อหมวด/ชื่อแถวโดยไม่โดนค่าตัวเลขท้ายบรรทัดกวน"""
    ws = line["words"]
    idx = next((i for i in range(1, len(ws)) if _value_of(ws[i]["text"]) is not None), len(ws))
    text = " ".join(w["text"] for w in ws[:idx])
    return thai_skeleton(_ITEM_RE.sub("", text))


def _column_centers(lines: list[dict]) -> list[float]:
    """หาจุดกึ่งกลาง x ของแต่ละคอลัมน์ จากตำแหน่งค่าอัตราทั้งหน้า (ไม่พึ่ง header ที่ OCR อ่านเพี้ยนบ่อย)"""
    xs = sorted(w["cx"] for l in lines for w in _data_words(l))
    if not xs:
        return []
    clusters: list[list[float]] = []
    cur = [xs[0]]
    for a, b in zip(xs, xs[1:]):
        if b - a > 40:            # ระยะห่างระหว่างคอลัมน์จริง >100px ที่ 300 DPI; ในคอลัมน์เดียวกัน <10px
            clusters.append(cur)
            cur = []
        cur.append(b)
    clusters.append(cur)
    return [sum(c) / len(c) for c in clusters if len(c) >= MIN_CLUSTER_MEMBERS]


def _find_section(lines: list[dict], keyword: str) -> tuple[int | None, int]:
    """หาช่วงบรรทัดของหมวด (เช่น "ประจำ" หรือ "สะสมทรัพย์") — เทียบ skeleton ของชื่อแถวแบบ "เท่ากัน"
    ไม่ใช่ substring จึงไม่ชนหมวดชื่อคล้ายกัน ("ประจำขวัญบัวหลวง", "สะสมทรัพย์ e-Savings" ฯลฯ
    ซึ่ง skeleton ยาวกว่า) — BBL มีหมวดชื่อขึ้นต้นเหมือนกันหลายหมวด จุดนี้จึงสำคัญมาก"""
    sk_kw = thai_skeleton(keyword)
    start = None
    for i, l in enumerate(lines):
        if _label_sk(l) == sk_kw:
            start = i
            break
    if start is None:
        return None, 0

    # จุดจบหมวด = หัวข้อระดับบนถัดไป แต่ต้องไม่ใช่แถวข้อมูล — OCR อ่านเลขข้อย่อยเพี้ยนได้
    # (พบจริง: "9.8" → "9.B" ทำให้ดูเหมือนหัวข้อระดับบน แล้วตัดหมวดก่อนถึงแถว 12 เดือน)
    # แถวข้อมูลมีคำว่า "ระยะเวลาการฝาก" เสมอ ใช้เป็นตัวกันพลาด
    end = len(lines)
    for i in range(start + 1, len(lines)):
        text = lines[i]["text"]
        if _TOPLEVEL_RE.match(text) and _SK_ROW not in thai_skeleton(text):
            end = i
            break
    return start, end


# ─────────────────────────── Tier วงเงิน ───────────────────────────
# BBL แบ่ง tier วงเงินในบางผลิตภัณฑ์ (ปัจจุบัน: สะสมทรัพย์ e-Savings; ประกาศปี 2023-2024: สะสมทรัพย์ทุกตัว)
# ส่วนเงินฝากประจำตอนนี้ไม่มี tier (อัตราเดียวทุกวงเงิน) — แต่โค้ดนี้รองรับ tier กับ "ทุกแถว" เสมอ
# ถ้าอนาคต BBL เพิ่ม tier ให้เงินฝากประจำ จะอ่านได้ทันทีโดยไม่ต้องแก้ parser
#
# ถ้อยคำ tier ที่พบจริงในประกาศ BBL (เทียบบน skeleton เพราะ OCR แทรกช่องว่าง/สระเพี้ยน):
#   "วงเงินฝากน้อยกว่า 10 ล้านบาท"      → ใช้เมื่อ วงเงิน < 10
#   "วงเงินฝาก 10 ล้านบาทขึ้นไป"        → ใช้เมื่อ วงเงิน >= 10
#   "วงเงินฝากไม่เกิน 1 ล้านบาท"        → ใช้เมื่อ วงเงิน <= 1
#   "วงเงินฝากส่วนที่เกิน 1 ล้านบาท"    → ใช้เมื่อ วงเงิน > 1
_TIER_RULES = [
    ("สวนทกน", "above",     lambda amt, n: amt > n,  "วงเงินส่วนที่เกิน {n:g} ล้านบาท"),
    ("มกน",    "up_to",     lambda amt, n: amt <= n, "วงเงินไม่เกิน {n:g} ล้านบาท"),
    ("นอยกว",  "less_than", lambda amt, n: amt < n,  "วงเงินน้อยกว่า {n:g} ล้านบาท"),
    ("ขนป",    "at_least",  lambda amt, n: amt >= n, "วงเงินตั้งแต่ {n:g} ล้านบาทขึ้นไป"),
]
_NUM_RE = re.compile(r"(\d+)")


def _parse_tier(label_sk: str) -> tuple[int, float, str] | None:
    """แปลงชื่อแถว tier → (ลำดับกฎ, จำนวนล้านบาท, คำอธิบาย) — None ถ้าไม่ใช่บรรทัด tier"""
    if not label_sk.startswith(_SK_LIMIT):
        return None
    num = _NUM_RE.search(label_sk)
    if not num:
        return None
    amount = float(num.group(1))
    for idx, (marker, _name, _match, desc) in enumerate(_TIER_RULES):
        if marker in label_sk:
            return idx, amount, desc.format(n=amount)
    return None


def _collect_tiers(lines: list[dict], row_idx: int, end: int) -> list[tuple[int, float, str, dict]]:
    """บรรทัดลูก "- วงเงิน..." ที่ต่อเนื่องกันใต้แถวหลัก (หยุดทันทีที่เจอบรรทัดที่ไม่ใช่ tier)"""
    tiers = []
    for i in range(row_idx + 1, end):
        info = _parse_tier(_label_sk(lines[i]))
        if info is None:
            break
        tiers.append((*info, lines[i]))
    return tiers


def _pick_tier(tiers: list, amount_m: float | None) -> tuple[dict, str]:
    """เลือกบรรทัด tier ที่ตรงกับวงเงินเป้าหมาย"""
    if amount_m is None:
        rule_idx, amount, desc, line = tiers[0]
        return line, f"{desc} (ไม่ได้ระบุ amount_m — ใช้ tier แรก)"
    for rule_idx, amount, desc, line in tiers:
        if _TIER_RULES[rule_idx][2](amount_m, amount):
            return line, desc
    rule_idx, amount, desc, line = tiers[0]
    return line, f"{desc} (fallback: วงเงิน {amount_m:g} ล้านบาท ไม่เข้า tier ใดเลย)"


# ─────────────────────────── โหมด max_tier/top_tier/max_all (①②③ "อัตราสูงสุด") ───────────────────────────
# path คู่ขนานกับ _collect_tiers/_pick_tier ด้านบน — ไม่แตะของเดิมเลยสักบรรทัด (ดู CLAUDE.md)
def _collect_max_tiers(lines: list[dict], row_idx: int, end: int) -> list[tuple]:
    """เก็บ tier ทุกตัวของแถวที่พบ → (kind, lower_m, upper_m, desc, raw_line) ตามที่ _maxscan.select()/
    tier_rank() ต้องการ — reuse _collect_tiers เดิมแล้วแปลงรูปแบบ (ไม่ใช้ _maxscan.classify_tier_ext
    เพราะ _TIER_RULES ของไฟล์นี้จำแนก tier ได้ถูกต้องอยู่แล้ว [รวมเคส OCR เพี้ยนของ BBL] — reuse ตัวจำแนก
    เดิมปลอดภัยกว่าเขียนตัวกลางใหม่ เหมือน KTB/BAY/KBANK)
    _TIER_RULES index ↔ kind: 0 "above" (เกิน N) · 1 "up_to" (ไม่เกิน N) · 2 "less_than" (น้อยกว่า N) ·
    3 "at_least" (ตั้งแต่ N ขึ้นไป) — _TIER_RULES[i][1] เก็บชื่อ kind ไว้ตรงตัวอยู่แล้ว ใช้ต่อได้เลย
    แถวที่ค่าอยู่บนบรรทัดหัวเอง (ไม่แบ่ง tier) คืน tier เดียว kind 'single' เหมือน bay.py"""
    line = lines[row_idx]
    if _data_words(line):
        return [("single", 0.0, None, "ไม่แบ่ง tier วงเงิน (อัตราเดียวทุกวงเงิน)", line)]
    raw = _collect_tiers(lines, row_idx, end)
    out: list[tuple] = []
    for rule_idx, amount, desc, ln in raw:
        kind = _TIER_RULES[rule_idx][1]
        if kind in ("above", "at_least"):
            out.append((kind, amount, None, desc, ln))
        else:  # up_to / less_than
            out.append((kind, 0.0, amount, desc, ln))
    return out


def _make_value_of(cols: list[float]):
    """closure คืน callback value_of(tier, col) สำหรับ _maxscan.select() — เรียก _cell_value() เดิม
    (คอลัมน์เดียวกับโหมด cell ทุกประการ) แล้วคืน None ถ้า conf < MIN_WORD_CONF (ด่านความมั่นใจของ OCR
    ต้องอยู่ในเส้นทาง max ด้วย ไม่งั้นค่ามั่วความมั่นใจต่ำจะชนะทันที) ส่วนช่วง 0-10 เช็คอยู่แล้วใน
    _maxscan._valid_rate() (= MAX_PLAUSIBLE_RATE เดิม)"""
    def value_of(tier: tuple, col: int) -> float | None:
        rate, conf = _cell_value(tier[4], cols, col)
        if rate is None or conf < MIN_WORD_CONF:
            return None
        return rate
    return value_of


def _tenor_unit(line: dict, tenor: int) -> str | None:
    """skeleton ของ "หน่วย" ที่ตามหลังเลข tenor ในบรรทัด (None ถ้าบรรทัดไม่มีเลขนั้น)
    เทียบเลขแบบ int ตรง ๆ กัน "1" ไปแมตช์ "12"; OCR แตกอักษรไทยเป็นหลาย token ("เด","ื","อ","น")
    จึงรวม token ถัดไปจนกว่าจะถึงค่าอัตราตัวแรก"""
    ws = line["words"]
    for j, w in enumerate(ws):
        if w["text"].isdigit() and int(w["text"]) == tenor:
            unit: list[str] = []
            for x in ws[j + 1:]:
                if _value_of(x["text"]) is not None:
                    break
                unit.append(x["text"])
            return thai_skeleton("".join(unit))
    return None


def _find_tenor_row(lines: list[dict], start: int, end: int, tenor: int) -> tuple[int | None, bool]:
    """หาแถว "ระยะเวลาการฝาก N เดือน" ในหมวด — คืน (index บรรทัด, ใช้การเทียบหน่วยแบบผ่อนปรนหรือไม่)

    label (ส่วนก่อนค่าตัวแรก หลังตัดเลขข้อ) ต้อง**ขึ้นต้นด้วย** "ระยะเวลาการฝาก" ทันที ไม่ใช่แค่มีคำนี้
    อยู่ในบรรทัด — กันแถวของผลิตภัณฑ์อื่นที่ OCR รวมหัวข้อ+แถวข้อมูลเป็นบรรทัดเดียว (พบจริงกับไฟล์สแกน
    คุณภาพต่ำ: "10. ประจำบัวหลวงซุปเปอร์โบนัส (2) ระยะเวลาการฝาก 6 เดือน ..." มีคำว่า "ระยะเวลาการฝาก"
    อยู่ในบรรทัดเหมือนกัน แต่เป็นคนละผลิตภัณฑ์ ไม่ใช่แถวของหมวด "ประจำ" จริง — ถ้าใช้ตรวจแบบ 'มีคำนี้อยู่ใน
    บรรทัด' เฉย ๆ จะจับผิดแถวได้เมื่อแถวที่ถูกต้องมีคำว่า 'เดือน' OCR เพี้ยน เช่น 'เตือน' จนไม่ผ่านการเทียบหน่วย)"""
    cands = [i for i in range(start + 1, end) if _label_sk(lines[i]).startswith(_SK_ROW)]

    for i in cands:                       # รอบแรก: หน่วยอ่านออกชัดว่าเป็น "เดือน"
        sk = _tenor_unit(lines[i], tenor)
        if sk is not None and sk.startswith(_SK_MONTH):
            return i, False

    for i in cands:                       # รอบสอง: OCR อ่านหน่วยเพี้ยนจนไม่เป็นไทย (พบจริง: "12 เดือน" → "12 Wau")
        sk = _tenor_unit(lines[i], tenor)  # ยอมรับได้ถ้า "ไม่ใช่วัน" — แถว 7/14 วัน ยังถูกกันออกอยู่
        if sk is not None and not sk.startswith(_SK_DAY):
            return i, True
    return None, False


def _find_keyword_row(lines: list[dict], start: int, end: int, row_kw: str) -> int | None:
    """หาแถวตามชื่อ (row_keyword) — เทียบ skeleton แบบเท่ากันทั้งชื่อแถว ไม่ใช่ substring
    ("สะสมทรัพย์" ต้องไม่ไปโดน "สะสมทรัพย์ขวัญบัวหลวง" / "สะสมทรัพย์ e-Savings" ที่มีอีก 6 แถว)

    two-pass: pass 1 = เท่ากันทั้งชื่อรายบรรทัด (เดิม); pass 2 (เมื่อ pass 1 ไม่เจอ) = ชื่อแถวถูก OCR ตัด
    เป็น 2 บรรทัด → เทียบ label(i)+label(i+1) 'เท่ากัน' กับ row_kw (เท่านั้น ห้าม substring เคารพกับดัก
    OCR ที่รวมหัวข้อ+แถวข้อมูลเป็นบรรทัดเดียว) คืน i+1 = บรรทัดที่สอง (บรรทัดที่มีค่าอัตรา)"""
    sk_kw = thai_skeleton(row_kw)
    for i in range(start, end):
        if _label_sk(lines[i]) == sk_kw:
            return i
    for i in range(start, end - 1):
        if _label_sk(lines[i]) + _label_sk(lines[i + 1]) == sk_kw:
            return i + 1
    return None


def _cell_value(line: dict, cols: list[float], col: int) -> tuple[float | None, float]:
    """ค่าในคอลัมน์ที่ต้องการของแถวนี้ — จับ token ที่อยู่ใกล้จุดกึ่งกลางคอลัมน์ที่สุด
    (ต้องอยู่ในระยะครึ่งหนึ่งของช่องไฟคอลัมน์ ไม่งั้นถือว่าไม่มีค่า — ไม่เดาคอลัมน์ข้างเคียง)"""
    half = min(b - a for a, b in zip(cols, cols[1:])) / 2
    target_x = cols[col - 1]
    best = None
    for w in _data_words(line):
        dist = abs(w["cx"] - target_x)
        if dist <= half and (best is None or dist < abs(best["cx"] - target_x)):
            best = w
    if best is None:
        return None, 0.0
    return _value_of(best["text"]), best["conf"]


def _locate_row(lines: list[dict], target: dict, key: str) -> tuple[int | None, int, str]:
    """หาแถวของ target — รองรับ 2 แบบ:
      1. tenor_months  → แถว "ระยะเวลาการฝาก N เดือน" (ค้นในหมวด section_keyword หรือ "ประจำ" เป็นค่าเริ่มต้น)
      2. row_keyword   → แถวชื่อตรงตัว เช่น "สะสมทรัพย์" (ค้นในหมวด section_keyword หรือทั้งหน้า)
    คืน (index แถว, index จบหมวด, คำอธิบายแถว)"""
    tenor = target.get("tenor_months")
    row_kw = target.get("row_keyword")
    section_kw = target.get("section_keyword")

    if tenor:
        sec_kw = section_kw or "ประจำ"
        start, end = _find_section(lines, sec_kw)
        if start is None:
            _attempt_error(key, f"extract_rates [{key}]: ไม่พบหมวด '{sec_kw}' ในตาราง — รูปแบบประกาศอาจเปลี่ยน")
            return None, 0, ""
        idx, relaxed = _find_tenor_row(lines, start, end, tenor)
        if idx is None:
            _attempt_error(key, f"extract_rates [{key}]: ไม่พบแถว 'ระยะเวลาการฝาก {tenor} เดือน' ในหมวด '{sec_kw}'")
            return None, 0, ""
        if relaxed:
            log.warning(f"extract_rates [{key}]: OCR อ่านหน่วยหลัง '{tenor}' ไม่ออกเป็น 'เดือน' "
                        f"— ใช้แถวนี้แบบผ่อนปรน (ไม่ใช่แถว 'วัน'): {lines[idx]['text'][:60]}")
        return idx, end, f"{tenor} เดือน"

    if row_kw:
        if section_kw:
            start, end = _find_section(lines, section_kw)
            if start is None:
                _attempt_error(key, f"extract_rates [{key}]: ไม่พบหมวด '{section_kw}' ในตาราง")
                return None, 0, ""
        else:
            start, end = 0, len(lines)
        idx = _find_keyword_row(lines, start, end, row_kw)
        if idx is None:
            _attempt_error(key, f"extract_rates [{key}]: ไม่พบแถวชื่อ '{row_kw}' (เทียบชื่อแบบตรงตัวทั้งแถว)")
            return None, 0, ""
        return idx, end, row_kw

    _attempt_error(key, f"extract_rates [{key}]: ต้องระบุ tenor_months หรือ row_keyword อย่างน้อยหนึ่งอย่าง")
    return None, 0, ""


def _extract_targets(lines: list[dict], targets: list[dict],
                     keys: set[str] | None = None) -> tuple[dict, dict, list[str]]:
    """อ่านค่าของ targets ที่ระบุจาก lines ของ OCR variant หนึ่ง (keys=None คือทุกตัว)
    คืน (result, tiers_used, failed_keys) — คอลัมน์จับไม่ได้ตามที่คาด = ทุก target ที่ขอ 'ล้มเหลว' หมด

    mode='cell' (ค่าเริ่มต้น ไม่ระบุก็ได้) ใช้เส้นทางเดิมทุกบรรทัด **ไม่แตะ** — mode ∈ _maxscan.MODES
    ('max_tier'①/'top_tier'②/'max_all'③ — "อัตราสูงสุด" ดู CLAUDE.md) ใช้เส้นทางคู่ขนานที่เก็บ tier ด้วย
    _collect_max_tiers() แล้วให้ _maxscan.select() ตัดสินใจแทน _pick_tier()/amount_m เดิม
    หมายเหตุ: ค่าที่ได้จากกิ่ง max ในฟังก์ชันนี้ยังไม่ผ่านการโหวตข้าม OCR variant — extract_rates
    (ผู้เรียก) เป็นผู้สะสมโหวตจากผลของฟังก์ชันนี้ที่เรียกซ้ำทุก variant อีกที (ดู extract_rates)"""
    wanted = [t for t in targets if keys is None or t["key"] in keys]

    cols = _column_centers(lines)
    if len(cols) != EXPECTED_COLUMNS:
        # ไม่ผูกกับ target ตัวใดตัวหนึ่ง (คอลัมน์จับผิดกระทบทุก target ใน variant นี้เหมือนกันหมด) — เก็บ
        # ใต้คีย์พิเศษ "" แล้วให้ extract_rates() พ่วงในบรรทัดสรุปท้ายสุดถ้าจบรอบแล้วยังมี target อ่านไม่ได้
        _attempt_error("", f"bbl.extract_rates: จับคอลัมน์ได้ {len(cols)} คอลัมน์ (คาดว่า {EXPECTED_COLUMNS}) "
                       f"— OCR/รูปแบบตารางผิดไปจากเดิม ไม่อ่านต่อกันได้ค่าผิดคอลัมน์")
        return {}, {}, [t["key"] for t in wanted]

    result: dict = {}
    tiers_used: dict = {}
    failed: list[str] = []

    for target in wanted:
        key = target["key"]
        mode = target.get("mode", "cell")

        if mode == "cell":
            depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
            col = resolve_depositor(depositor_value)
            if col is None:
                _attempt_error(key, f"extract_rates [{key}]: ไม่รู้จัก depositor '{depositor_value}' — ข้าม target นี้")
                failed.append(key); continue

            row_idx, end, row_desc = _locate_row(lines, target, key)
            if row_idx is None:
                failed.append(key); continue

            # แถวมีค่าอยู่บนบรรทัดเดียวกัน = ไม่แบ่ง tier; ถ้าเป็นหัวข้อเปล่า ให้ไปหาบรรทัดลูก "- วงเงิน..."
            line = lines[row_idx]
            amount_m = target.get("amount_m")
            if _data_words(line):
                tier_desc = "ไม่แบ่ง tier วงเงิน (อัตราเดียวทุกวงเงิน)"
            else:
                tiers = _collect_tiers(lines, row_idx, end)
                if not tiers:
                    _attempt_error(key, f"extract_rates [{key}]: แถว '{row_desc}' ไม่มีค่าอัตรา และไม่มีบรรทัดวงเงินย่อย "
                                   f"— ข้าม target นี้: {line['text'][:60]}")
                    failed.append(key); continue
                line, tier_desc = _pick_tier(tiers, amount_m)

            rate, conf = _cell_value(line, cols, col)
            if rate is None:
                _attempt_error(key, f"extract_rates [{key}]: ไม่มีค่าในคอลัมน์ {col} ({depositor_value}) ของแถวนี้ "
                               f"(อาจเป็น '-') — ข้าม target นี้: {line['text'][:60]}")
                failed.append(key); continue
            if conf < MIN_WORD_CONF:
                _attempt_error(key, f"extract_rates [{key}]: OCR อ่านค่า {rate} ด้วยความมั่นใจต่ำ ({conf:.0f}% < "
                               f"{MIN_WORD_CONF:.0f}%) — ไม่เชื่อถือ ข้าม target นี้")
                failed.append(key); continue
            if not (0.0 <= rate <= MAX_PLAUSIBLE_RATE):
                _attempt_error(key, f"extract_rates [{key}]: ค่า {rate} อยู่นอกช่วงที่เป็นไปได้ (0-{MAX_PLAUSIBLE_RATE}) "
                               f"— OCR น่าจะอ่านผิด ข้าม target นี้")
                failed.append(key); continue

            desc = f"{row_desc} · {tier_desc} · คอลัมน์ {col} ({depositor_value})"
            log.info(f"  {target.get('label', key)}: {rate:.2f}%  ← {desc} [OCR conf {conf:.0f}%]")

        elif mode in _maxscan.MODES:
            col = None
            if mode != "max_all":
                depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
                col = resolve_depositor(depositor_value)
                if col is None:
                    _attempt_error(key, f"extract_rates [{key}]: ไม่รู้จัก depositor '{depositor_value}' — ข้าม target นี้")
                    failed.append(key); continue

            row_idx, end, row_desc = _locate_row(lines, target, key)
            if row_idx is None:
                failed.append(key); continue

            tiers = _collect_max_tiers(lines, row_idx, end)
            value_of = _make_value_of(cols)
            rate, mdesc = _maxscan.select(mode, tiers, col, DEPOSITOR_COLUMNS, value_of)
            if rate is None:
                _attempt_error(key, f"extract_rates [{key}]: {mdesc} (ค่าที่อ่านได้รอบนี้ — ยังไม่ผ่านโหวต) — ข้าม target นี้")
                failed.append(key); continue

            desc = f"{row_desc} · {mdesc}"
            log.info(f"  {target.get('label', key)}: {rate:.2f}%  ← {desc}  (รอบนี้ — รอโหวตข้าม OCR variant)")

        else:
            _attempt_error(key, f"extract_rates [{key}]: ไม่รู้จัก mode '{mode}' — ข้าม target นี้")
            failed.append(key); continue

        result[key] = rate
        tiers_used[key] = desc

    return result, tiers_used, failed


def extract_rates(pdf_bytes: bytes, bank: dict) -> dict | None:
    """อ่านอัตราตาม rate_targets — รองรับทั้งแถวเงินฝากประจำ (tenor_months) และแถวชื่อผลิตภัณฑ์
    (row_keyword เช่น สะสมทรัพย์) และรองรับ tier วงเงิน (amount_m) กับทุกแถวเสมอ ไม่ว่าประกาศฉบับนั้น
    จะแบ่ง tier หรือไม่ก็ตาม (ดูหมายเหตุที่ _TIER_RULES) target โหมด max_tier/top_tier/max_all
    (①②③ "อัตราสูงสุด" ดู CLAUDE.md) ใช้เส้นทางแยกที่ต้องโหวตข้าม OCR variant ก่อนยอมรับค่า (ดูย่อหน้าถัดไป)

    ไล่ลอง OCR_VARIANTS ทีละชุด — variant แรกอ่านทุก target, ชุดถัดไป**เติมเฉพาะ target ที่ยังขาด**
    (ไม่เขียนทับค่าที่อ่านได้แล้ว) ไฟล์ปกติจะอ่านครบตั้งแต่ variant แรกและไม่แตะ variant อื่นเลย
    — เสียเวลา OCR เพิ่มเฉพาะไฟล์สแกนคุณภาพต่ำที่ variant แรกอ่านป้ายไม่ออกเท่านั้น
    ค่าที่ยังขาดหลังลองครบทุก variant จะถูกปล่อยว่างไว้ (ไม่เดา) — ดู rate_monitor.py ส่วนแจ้งเตือน

    **target โหมด max ต่างจาก cell**: ค่าสูงสุดอ่อนไหวต่อ OCR อ่าน "สูงเกินจริง" เป็นพิเศษ (ค่าที่อ่านผิด
    กลายเป็นคำตอบทันทีถ้าเชื่อ variant แรกที่อ่านได้เหมือน cell — พิสูจน์แล้วว่าเป็นเคสจริง ไม่ใช่ทฤษฎี ดู
    CLAUDE.md) จึงสะสม "โหวต" ต่อ key: ค่าที่ variant ต่าง ๆ อ่านได้ตรงกัน ≥ VOTE_MIN ครั้งจึงยอมรับ (ตัด
    ออกจาก remaining แล้วหยุดลองต่อสำหรับ key นั้น) ครบทุก variant แล้วยังไม่มีค่าใดถึง VOTE_MIN เสียง →
    ปล่อยว่างไว้ ไม่เดา พร้อม log.error แจกแจงผู้สมัครทั้งหมดที่เจอ (rate: จำนวนเสียง) — บรรทัดสรุปนี้พ่วง
    เหตุผลที่สะสมไว้ระหว่างไล่ variant ต่อท้ายด้วย (ดู _attempt_error/_buffered_reasons) เพราะ log.error
    ต่อ-variant ต่อ-target ระหว่างทางถูกลดเป็น log.debug ไปหมดแล้ว (ตัดเสียงรบกวน — ดู CLAUDE.md)"""
    targets = bank["rate_targets"]
    max_keys = {t["key"] for t in targets if t.get("mode", "cell") in _maxscan.MODES}
    result: dict = {}
    tiers_used: dict = {}
    remaining = {t["key"] for t in targets}
    # votes[key][rate] = (จำนวนเสียง, desc แรกที่ได้ค่านั้น) — เฉพาะ key ในกลุ่ม max_keys
    votes: dict[str, dict[float, tuple[int, str]]] = {}
    # tentative[key] = (rate, desc, variant idx) — ค่าสำรองที่อ่านได้เป็น 0.00 (ดู SUSPECT_RATE)
    tentative: dict[str, tuple[float, str, int]] = {}

    # เปิด buffer ครอบทั้งการไล่ variant และบรรทัดสรุปท้ายสุด (ต้องอ่าน _buffered_reasons ได้ก่อนปิด) —
    # debug_tiers() ไม่เรียกฟังก์ชันนี้เลยจึงไม่มีทางเปิด buffer โดยไม่ตั้งใจ (พฤติกรรม log เดิมทุกตัวอักษร)
    with _attempt_buffering():
        for i, variant in enumerate(OCR_VARIANTS):
            if not remaining:
                break
            lines = _page1_lines(pdf_bytes, variant)
            if lines is None:
                continue
            r, tu, _ = _extract_targets(lines, targets, keys=remaining)
            gained = set(r) & remaining
            lang, psm, dpi = variant[:3]
            tag = "" if i == 0 else f" (OCR variant สำรอง #{i}: {lang}/psm{psm}/{dpi}dpi)"

            cell_gained = gained - max_keys
            # ค่า 0.00 = "ค่าสำรอง" ไม่ตัดออกจาก remaining — ไล่ variant ที่เหลือต่อเผื่อมีตัวอ่านได้ค่าจริง
            # (ดูหมายเหตุเหนือ SUSPECT_RATE) เก็บเฉพาะครั้งแรกที่เจอ ตัวหลังไม่ทับ = ลำดับ variant ยังชี้ขาด
            # เหมือนเดิมถ้าสุดท้ายต้องใช้ค่าสำรองจริง ๆ
            suspect = {k for k in cell_gained if r[k] == SUSPECT_RATE}
            for k in suspect:
                tentative.setdefault(k, (r[k], tu[k], i))
            cell_gained -= suspect
            if cell_gained:
                log.info(f"bbl: กู้ค่าได้ {len(cell_gained)} target เพิ่ม{tag}: {', '.join(sorted(cell_gained))}")
            result.update({k: r[k] for k in cell_gained})
            tiers_used.update({k: tu[k] for k in cell_gained})
            remaining -= cell_gained

            # target โหมด max: สะสมโหวตแทนที่จะเชื่อ variant แรกที่อ่านได้ทันทีแบบ cell (ดู docstring)
            confirmed = set()
            for k in gained & max_keys:
                bucket = votes.setdefault(k, {})
                count, first_desc = bucket.get(r[k], (0, tu[k]))
                bucket[r[k]] = (count + 1, first_desc)
            for k in remaining & max_keys:
                for rate, (count, desc) in votes.get(k, {}).items():
                    if count >= VOTE_MIN:
                        result[k] = rate
                        tiers_used[k] = f"{desc} · ยืนยันตรงกัน {count} OCR variant"
                        confirmed.add(k)
                        break
            if confirmed:
                log.info(f"bbl: โหมดอัตราสูงสุดยืนยันค่าได้{tag}: {', '.join(sorted(confirmed))}")
            remaining -= confirmed

        # ครบทุก variant แล้ว — key ที่มีแต่ค่าสำรอง 0.00 ค่อยยอมรับตอนนี้ (ไม่มี variant ไหนอ่านได้ค่าอื่นเลย
        # = 0.00 น่าจะเป็นค่าจริงในประกาศ) ทำให้พฤติกรรมเดิมของไฟล์ที่ประกาศ 0.00 จริงไม่เปลี่ยนเลย
        fallback = (remaining - max_keys) & set(tentative)
        for k in sorted(fallback):
            rate, desc, vi = tentative[k]
            result[k] = rate
            tiers_used[k] = desc
            log.warning(f"extract_rates [{k}]: ทุก OCR variant อ่านได้แค่ {rate:.2f} — ใช้ค่านี้ "
                        f"(อ่านได้ครั้งแรกที่ variant #{vi}) แต่ค่า 0.00 มักเกิดจาก OCR อ่านตัวเลขหลุด "
                        f"ควรเทียบกับ PDF ด้วยตาก่อนเชื่อ")
        remaining -= fallback

        cell_remaining = remaining - max_keys
        if cell_remaining:
            # แต่ละ key ในบรรทัดนี้อาจมีเหตุผลคนละชุด — พ่วงแยกต่อ key ด้วย "[key] เหตุผล" กันปนกัน
            per_key = [f"[{k}] {_buffered_reasons(k)}" for k in sorted(cell_remaining) if _buffered_reasons(k)]
            extra = f" — เหตุผลระหว่างไล่ OCR variant: {'; '.join(per_key)}" if per_key else ""
            log.error(f"extract_rates: อ่านค่าไม่ได้แม้ลองครบ {len(OCR_VARIANTS)} OCR variant: "
                      f"{', '.join(sorted(cell_remaining))} — ปล่อยว่างไว้{extra}")

        for k in sorted(remaining & max_keys):
            bucket = votes.get(k, {})
            reasons = _buffered_reasons(k)
            extra = f" — เหตุผลระหว่างไล่ OCR variant: {reasons}" if reasons else ""
            if bucket:
                candidates = ", ".join(f"{rate:g} ({count} เสียง)" for rate, (count, _) in
                                        sorted(bucket.items(), key=lambda kv: -kv[1][0]))
                log.error(f"extract_rates [{k}]: ไม่มีค่าที่ยืนยันได้ครบ {VOTE_MIN} เสียง (ต้องมี OCR variant "
                          f"อ่านตรงกันอย่างน้อย {VOTE_MIN} ครั้ง) — ผู้สมัคร: {candidates} — ปล่อยว่างไว้{extra}")
            else:
                log.error(f"extract_rates [{k}]: ไม่มี OCR variant ใดอ่านค่าได้เลยแม้ครบ {len(OCR_VARIANTS)} "
                          f"variant — ปล่อยว่างไว้{extra}")

    if not result:
        log.error("extract_rates: อ่านค่าไม่ได้เลยสักตัว (ทุก target ล้มเหลว)")
        return None

    result["tiers_used"] = tiers_used
    return result


def _mode_value_for_variant(lines: list[dict], cols: list[float], target: dict, key: str, mode: str
                            ) -> tuple[int | None, int, str, list[tuple], tuple[float, str] | None]:
    """คำนวณผลลัพธ์ของ 1 mode (cell/max_tier/top_tier/max_all) จาก lines/cols ของ OCR variant เดียว
    — ใช้เฉพาะใน debug_tiers() (ไม่ใช้ใน extract_rates ซึ่งมี _extract_targets ของตัวเองอยู่แล้ว)
    คืน (row_idx, end, row_desc, tiers แบบ max, ผลของ mode นี้ [rate, desc] หรือ None)"""
    row_idx, end, row_desc = _locate_row(lines, target, key)
    if row_idx is None:
        return None, 0, "", [], None

    tiers = _collect_max_tiers(lines, row_idx, end)

    if mode == "cell":
        depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
        col = resolve_depositor(depositor_value)
        if col is None:
            return row_idx, end, row_desc, tiers, None
        line = lines[row_idx]
        amount_m = target.get("amount_m")
        if _data_words(line):
            cell_line, tier_desc = line, "ไม่แบ่ง tier วงเงิน (อัตราเดียวทุกวงเงิน)"
        else:
            cell_tiers = _collect_tiers(lines, row_idx, end)
            if not cell_tiers:
                return row_idx, end, row_desc, tiers, None
            cell_line, tier_desc = _pick_tier(cell_tiers, amount_m)
        rate, conf = _cell_value(cell_line, cols, col)
        if rate is None or conf < MIN_WORD_CONF or not (0.0 <= rate <= MAX_PLAUSIBLE_RATE):
            return row_idx, end, row_desc, tiers, None
        return row_idx, end, row_desc, tiers, (rate, f"{tier_desc} · คอลัมน์ {col} ({depositor_value})")

    # max_tier / top_tier / max_all
    col = None
    if mode != "max_all":
        col = resolve_depositor(target.get("depositor", DEFAULT_DEPOSITOR))
        if col is None:
            return row_idx, end, row_desc, tiers, None
    value_of = _make_value_of(cols)
    rate, desc = _maxscan.select(mode, tiers, col, DEPOSITOR_COLUMNS, value_of)
    return row_idx, end, row_desc, tiers, (rate, desc) if rate is not None else None


def debug_tiers(pdf_bytes: bytes, bank: dict) -> list[dict] | None:
    """ใช้กับ CLI `--show-tiers BBL` — คืนรูปแบบเดียวกับ bay/scb (คีย์ key/label/depositor/row_found/
    results/tiers) เพื่อใช้ `_print_tiers_report()` เดิมใน rate_monitor.py ได้โดยไม่ต้องแก้ฝั่งนั้น

    ต่างจากธนาคารอื่นตรงที่ต้องรันทุก OCR variant แล้วรายงาน **ค่าที่ผ่านโหวต** สำหรับโหมด ①②③ เท่านั้น
    (cell ใช้ variant แรกที่อ่านได้ เหมือน extract_rates จริง — ไม่มีกลไกโหวต) พร้อมจำนวนเสียงต่อค่าใน
    สตริง desc (เช่น "① สูงสุดทุกวงเงิน (...) [โหวต 2/3 variant · ผู้สมัคร: 0.75 (2 เสียง), 0.76 (1 เสียง)]")
    เพื่อให้ตรวจตาเห็นความไม่ตรงกันระหว่าง variant ก่อนติ๊กใช้จริง — log.info พิมพ์รายละเอียดผู้สมัครทุก
    target/mode ออกคอนโซลด้วยเสมอ (ไม่ใช่แค่ค่าที่ผ่านโหวต) เพราะ `_print_tiers_report()` เดิมพิมพ์แค่ "-"
    เมื่อไม่มีค่า ไม่พิมพ์เหตุผล ส่วน `tiers` (คอลัมน์ค่าดิบ) ใช้ของ variant แรกที่หาแถวเจอเท่านั้น"""
    report: list[dict] = []

    for target in bank["rate_targets"]:
        key = target["key"]
        depositor_value = target.get("depositor", DEFAULT_DEPOSITOR)
        item: dict = {"key": key, "label": target.get("label", key), "depositor": depositor_value}

        row_found: str | None = None
        tiers_display: list[tuple] = []
        tiers_cols: list[float] = []
        cell_result: tuple[float, str] | None = None
        # votes[mode][rate] = [จำนวนเสียง, desc แรก, [variant idx ที่เห็นด้วย]]
        votes: dict[str, dict[float, list]] = {m: {} for m in _maxscan.MODES}
        variants_tried = 0

        for vi, variant in enumerate(OCR_VARIANTS):
            lines = _page1_lines(pdf_bytes, variant)
            if lines is None:
                continue
            cols = _column_centers(lines)
            if len(cols) != EXPECTED_COLUMNS:
                continue

            row_idx, end, row_desc, tiers, cell_val = _mode_value_for_variant(lines, cols, target, key, "cell")
            if row_idx is None:
                continue
            variants_tried += 1
            if row_found is None:
                row_found = lines[row_idx]["text"]
                tiers_display, tiers_cols = tiers, cols
            if cell_result is None and cell_val is not None:
                cell_result = cell_val

            for mode in _maxscan.MODES:
                _, _, _, _, val = _mode_value_for_variant(lines, cols, target, key, mode)
                if val is None:
                    continue
                rate, desc = val
                bucket = votes[mode].setdefault(rate, [0, desc, []])
                bucket[0] += 1
                bucket[2].append(vi)

        item["row_found"] = row_found
        results: dict = {}
        if cell_result is not None:
            results["cell"] = cell_result

        for mode in _maxscan.MODES:
            bucket = votes[mode]
            if not bucket:
                continue
            candidates = ", ".join(
                f"{rate:g} ({info[0]} เสียง · variant#{','.join(map(str, info[2]))})"
                for rate, info in sorted(bucket.items(), key=lambda kv: -kv[1][0]))
            best_rate, (best_count, best_desc, best_variants) = max(bucket.items(), key=lambda kv: kv[1][0])
            if best_count >= VOTE_MIN:
                log.info(f"[{key}] {mode}: ยืนยัน {best_rate:g}% ({best_count}/{variants_tried} variant "
                         f"· variant#{','.join(map(str, best_variants))}) — ผู้สมัครทั้งหมด: {candidates}")
                results[mode] = (best_rate, f"{best_desc} [โหวต {best_count}/{variants_tried} variant "
                                            f"· ผู้สมัคร: {candidates}]")
            else:
                log.info(f"[{key}] {mode}: ไม่ผ่านโหวต (ต้องการ {VOTE_MIN}/{variants_tried} variant) "
                         f"— ผู้สมัครทั้งหมด: {candidates}")
                results[mode] = (None, f"ไม่ผ่านโหวต — ผู้สมัคร: {candidates}")
        item["results"] = results

        item["tiers"] = [
            {"desc": t[3],
             "col_values": {DEPOSITOR_COLUMNS[c][0]: (
                 lambda rate: "-" if rate is None else f"{rate:g}"
             )(_cell_value(t[4], tiers_cols, c)[0]) for c in DEPOSITOR_COLUMNS}}
            for t in tiers_display
        ]
        report.append(item)

    return report


# ─────────────────────────── Effective date (OCR หัวกระดาษ) ───────────────────────────
_DATE_RE = re.compile(r"(\d{1,2})\s+(\D{1,40}?)(\d{4})")
_MONTH_SK = {thai_skeleton(name): num for name, num in THAI_MONTHS.items()}


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _match_month(sk: str) -> int | None:
    """จับคู่ชื่อเดือนแบบทนพยัญชนะเพี้ยน 1 ตัว (พบจริง: OCR อ่าน "ธันวาคม" เป็น "ชันวาคม")
    ต้องมีผู้ชนะเดียวเท่านั้น — ถ้าก้ำกึ่งถือว่าอ่านไม่ได้ ดีกว่าเดาเดือนผิด"""
    if sk in _MONTH_SK:
        return _MONTH_SK[sk]
    if not sk:
        return None
    scored = [(_edit_distance(sk, m), num) for m, num in _MONTH_SK.items()]
    best = min(d for d, _ in scored)
    if best > 1:
        return None
    winners = {num for d, num in scored if d == best}
    return winners.pop() if len(winners) == 1 else None


def get_effective_date(pdf_bytes: bytes) -> str | None:
    """ดึงวันที่มีผลจากหัวกระดาษหน้า 1 ("มีผลบังคับใช้ตั้งแต่ วันที่ 18 มิถุนายน 2569 เป็นต้นไป") → YYYY-MM-DD
    OCR เฉพาะแถบบน 25% ของหน้า — เร็วกว่าและแม่นกว่า OCR ทั้งหน้า
    ระวัง: ท้ายหน้ามี "ประกาศ ณ วันที่ ..." ซึ่งเป็นคนละวัน จึงเลือกบรรทัดที่มี "มีผลบังคับใช้" ก่อนเสมอ

    ไล่ลอง OCR_VARIANTS เหมือน extract_rates — ไฟล์ปกติเจอวันที่ตั้งแต่ variant แรกและไม่แตะ variant อื่น
    (ไม่มี cache เหมือน _page1_lines เพราะ crop 25% บนคนละภาพกับตารางเต็มหน้า และถูกเรียกครั้งเดียวต่อไฟล์)"""
    for variant in OCR_VARIANTS:
        lang, psm, dpi = variant[:3]
        png = _render_page1_png(pdf_bytes, top_frac=0.25, dpi=dpi,
                                preprocess=variant[3] if len(variant) > 3 else None)
        if png is None:
            continue
        words = _ocr_words(png, lang=lang, psm=psm, dpi=dpi)
        if not words:
            continue

        lines = _group_lines(words)
        candidates = [l for l in lines if _SK_EFFECTIVE in thai_skeleton(l["text"])] or lines
        for line in candidates:
            for m in _DATE_RE.finditer(line["text"]):
                day_s, mid, year_s = m.groups()
                month = _match_month(thai_skeleton(mid))
                if not month:
                    continue
                try:
                    return f"{int(year_s) - 543:04d}-{month:02d}-{int(day_s):02d}"
                except ValueError:
                    continue

    log.error("bbl.get_effective_date: ไม่พบวันที่มีผลในหัวกระดาษ (OCR อ่านไม่ออก/รูปแบบเปลี่ยน) "
              f"แม้ลองครบ {len(OCR_VARIANTS)} OCR variant")
    return None


# ─────────────────────────── Listing / discovery ───────────────────────────
# หน้า View-Rates มีลิงก์ PDF ของ "ทุกประกาศย้อนหลัง" อยู่ใน HTML ชุดเดียว (ไม่มี AJAX/token แบบ KTB)
# และ **วันที่มีผลอยู่ในชื่อไฟล์** เช่น depositrates_18jun2026.pdf → ใช้เลือกไฟล์ล่าสุด/กรองรายปีได้เลย
_PDF_HREF_RE = re.compile(
    r'href="(/-/media/[^"]*?/deposit-interest-rates/\d{4}/depositrates_[^"]+?\.pdf)"', re.I)
_FNAME_DATE_RE = re.compile(r"depositrates_(\d{1,2})([a-z]{3})(\d{4})\.pdf$", re.I)
_ENG_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _new_session():
    from curl_cffi import requests as cffi_requests
    return cffi_requests.Session(impersonate="chrome")


def _sleep():
    time.sleep(REQUEST_DELAY_SEC + random.uniform(0, REQUEST_JITTER_SEC))


def _date_from_filename(path: str) -> str | None:
    m = _FNAME_DATE_RE.search(path)
    if not m:
        return None
    day_s, mon_s, year_s = m.groups()
    month = _ENG_MONTHS.get(mon_s.lower())
    if not month:
        return None
    try:
        return f"{int(year_s):04d}-{month:02d}-{int(day_s):02d}"
    except ValueError:
        return None


def _fetch_listing(session=None) -> list[tuple[str, str]] | None:
    """คืน [(วันที่จากชื่อไฟล์ YYYY-MM-DD, URL เต็ม)] ของทุกประกาศในหน้า View-Rates เรียงเก่า→ใหม่
    คืน None ถ้าโหลดหน้าไม่ได้หรือหน้าไม่มีลิงก์เลย (= เว็บเปลี่ยนรูปแบบ ไม่ใช่ 'ไม่มีอัปเดต')"""
    session = session or _new_session()
    try:
        r = session.get(RATES_PAGE_URL, timeout=45)
    except Exception as e:
        log.error(f"bbl: โหลดหน้าอัตราดอกเบี้ยไม่สำเร็จ: {e}")
        return None
    if r.status_code != 200:
        log.error(f"bbl: โหลดหน้าอัตราดอกเบี้ยไม่สำเร็จ (HTTP {r.status_code})")
        return None

    found: dict[str, str] = {}
    for m in _PDF_HREF_RE.finditer(r.text):
        path = m.group(1)
        date = _date_from_filename(path)
        if date:
            found.setdefault(date, SITE_BASE + quote(path, safe="/"))
    if not found:
        log.error("bbl: ไม่พบลิงก์ PDF ประกาศอัตราดอกเบี้ยในหน้าเว็บเลย — รูปแบบหน้าเว็บอาจเปลี่ยน")
        return None
    return sorted(found.items())


def resolve_latest_url(bank: dict) -> str | None:
    """เลือกประกาศที่วันที่ใหม่สุดจากหน้า View-Rates (BBL ไม่มี URL คงที่)
    คืน URL เดิมทุกรอบจนกว่าจะมีประกาศใหม่ — rate_monitor dedupe ด้วยวันที่มีผลจากเนื้อ PDF เองอยู่แล้ว"""
    code = bank.get("code", "BBL")
    links = _fetch_listing()
    if not links:
        return None
    date, url = links[-1]
    log.info(f"[{code}] resolve_latest_url: ประกาศล่าสุดตามชื่อไฟล์ {date}")
    return url


def discover_year(bank: dict, year: int | None = None) -> list[str]:
    """ดาวน์โหลดประกาศย้อนหลังทั้งปี (ค.ศ.) ที่ยังไม่มีในเครื่อง — คืนรายชื่อไฟล์ใหม่
    (rate_monitor จะเรียก backfill ต่อเองเพื่อ rebuild CSV)"""
    code = bank.get("code", "BBL")
    yr = year or datetime.now().year

    pdf_dir, _ = common.get_bank_paths(code)
    os.makedirs(pdf_dir, exist_ok=True)
    existing_dates = set()
    for f in os.listdir(pdf_dir):
        m = re.match(rf"{code.lower()}_deposit_(\d{{4}}-\d{{2}}-\d{{2}})\.pdf$", f)
        if m:
            existing_dates.add(m.group(1))

    session = _new_session()
    links = _fetch_listing(session)
    if not links:
        return []

    todo = [(d, u) for d, u in links if d.startswith(f"{yr}-") and d not in existing_dates]
    log.info(f"[{code}] discover_year: ปี {yr} มีประกาศบนเว็บ "
             f"{sum(1 for d, _ in links if d.startswith(f'{yr}-'))} ฉบับ "
             f"— ต้องดาวน์โหลดใหม่ {len(todo)} ฉบับ")

    saved: list[str] = []
    for file_date, url in todo:
        _sleep()
        try:
            resp = session.get(url, timeout=60, headers={"Referer": RATES_PAGE_URL})
        except Exception as e:
            log.warning(f"[{code}] discover_year: โหลด {file_date} ล้มเหลว: {e} — ข้าม")
            continue
        raw = resp.content
        if resp.status_code != 200 or not raw or raw[:4] != b"%PDF":
            log.warning(f"[{code}] discover_year: {file_date} ไม่ใช่ไฟล์ PDF "
                        f"(HTTP {resp.status_code}) — ข้าม")
            continue

        # ตั้งชื่อไฟล์ด้วยวันที่จาก "เนื้อหา" PDF เป็นหลัก (ตรงกับ flow ปกติของ run_bank)
        # ถ้า OCR อ่านหัวกระดาษไม่ออกจึงค่อยใช้วันที่จากชื่อไฟล์ต้นทางแทน
        eff_date = get_effective_date(raw)
        if eff_date is None:
            log.warning(f"[{code}] discover_year: OCR หาวันที่มีผลใน {file_date} ไม่เจอ "
                        f"— ใช้วันที่จากชื่อไฟล์ต้นทางแทน")
            eff_date = file_date
        elif eff_date != file_date:
            log.warning(f"[{code}] discover_year: วันที่ในเนื้อหา ({eff_date}) ไม่ตรงกับชื่อไฟล์ต้นทาง "
                        f"({file_date}) — ใช้วันที่ในเนื้อหา")
        # todo ถูกกรองด้วยชื่อไฟล์ (file_date) มาแล้วว่าอยู่ในปี yr แต่ eff_date ที่ใช้ตั้งชื่อจริงมาจาก
        # เนื้อหา ซึ่งอาจไม่ตรงปีกับชื่อไฟล์ต้นทาง (เคสข้างบน) — ต้องกรองซ้ำด้วย eff_date ตัวที่ใช้จริง
        if not common.is_date_in_year(eff_date, yr):
            log.info(f"[{code}] discover_year: {file_date} วันที่มีผลจริง ({eff_date}) ไม่ใช่ปี {yr} "
                     f"— ข้าม (ไม่นับเป็นไฟล์ใหม่)")
            continue
        if eff_date in existing_dates:
            continue

        fname = f"{code.lower()}_deposit_{eff_date}.pdf"
        with open(os.path.join(pdf_dir, fname), "wb") as f:
            f.write(raw)
        saved.append(fname)
        existing_dates.add(eff_date)
        log.info(f"[{code}] discover_year: พบและบันทึก {fname}")

    log.info(f"[{code}] discover_year: เสร็จสิ้น — พบไฟล์ใหม่ {len(saved)} ไฟล์: {', '.join(saved) or '-'}")
    return saved
