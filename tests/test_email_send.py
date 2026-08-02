"""test_email_send.py — โครง MIME / ไฟล์แนบ / To vs BCC ของ common.send_email()

**ห้ามส่งอีเมลจริงเด็ดขาด** — ทุกเคสสวม smtplib.SMTP_SSL/SMTP ด้วยตัวปลอมที่แค่เก็บ msg ไว้ให้ตรวจ
(ถ้าโค้ดหลุดไปเรียก smtplib ตัวจริงเมื่อไหร่ test จะพังทันทีเพราะ host ปลอมต่อไม่ติด)
"""
import pytest

from app.monitor import common


class _FakeSMTP:
    """ตัวปลอมของ smtplib.SMTP_SSL — เก็บ msg/from_addr/to_addrs ของการส่งครั้งล่าสุดไว้ที่คลาส"""
    sent: list = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        pass

    def send_message(self, msg, from_addr=None, to_addrs=None):
        type(self).sent.append({"msg": msg, "from_addr": from_addr, "to_addrs": to_addrs})


@pytest.fixture
def smtp(monkeypatch):
    """ตั้ง SMTP config ปลอมให้ครบ (ไม่งั้น send_email คืน False ตั้งแต่ยังไม่ประกอบข้อความ)
    แล้วสวม smtplib ทั้ง SMTP_SSL และ SMTP กันหลุดไปต่อเน็ตจริงทุกทาง"""
    _FakeSMTP.sent = []
    monkeypatch.setattr(common, "_active_smtp_config", lambda: {
        "provider": "gmail", "label": "gmail", "host": "smtp.example.com", "port": 465,
        "user": "bot@example.com", "password": "x", "sender": "bot@example.com",
        "insecure": False, "ca_file": None,
    })
    monkeypatch.setattr(common, "get_recipients", lambda: ["a@example.com", "b@example.com"])
    monkeypatch.setattr(common.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(common.smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


# ─────────────────────────── (ก) โครง MIME ───────────────────────────
def test_no_attachment_keeps_alternative_structure(smtp):
    """ไม่มีไฟล์แนบ = โครงเดิมเป๊ะ (multipart/alternative ชั้นเดียว) — OTP/error/test ต้องไม่ regress"""
    assert common.send_email("หัวข้อ", "<p>เนื้อความ</p>") is True
    msg = smtp.sent[0]["msg"]
    assert msg.get_content_type() == "multipart/alternative"
    parts = msg.get_payload()
    assert len(parts) == 1
    assert parts[0].get_content_type() == "text/html"


def test_attachment_wraps_in_mixed(smtp):
    """มีไฟล์แนบ = multipart/mixed ครอบ alternative (เนื้อความ) + ไฟล์แนบ"""
    assert common.send_email("หัวข้อ", "<p>เนื้อความ</p>",
                             attachments=[("scb_deposit_2026-01-01.pdf", b"%PDF-1.4 fake")]) is True
    msg = smtp.sent[0]["msg"]
    assert msg.get_content_type() == "multipart/mixed"
    parts = msg.get_payload()
    assert len(parts) == 2
    assert parts[0].get_content_type() == "multipart/alternative"
    assert parts[0].get_payload()[0].get_content_type() == "text/html"

    att = parts[1]
    assert att.get_content_type() == "application/pdf"
    assert att.get_filename() == "scb_deposit_2026-01-01.pdf"
    assert att.get_payload(decode=True) == b"%PDF-1.4 fake"


# ─────────────────────────── (ข) To vs BCC ───────────────────────────
def test_broadcast_hides_recipients_in_to_header(smtp):
    """broadcast (ไม่ระบุ to) → หัว To: ต้องไม่มีอีเมลผู้รับคนไหนเลย และต้องไม่มีหัว Bcc:
    แต่ envelope (to_addrs) ยังต้องครบทุกคน ไม่งั้นอีเมลไม่ถึงใครเลย"""
    common.send_email("หัวข้อ", "<p>x</p>")
    rec = smtp.sent[0]
    to_header = rec["msg"]["To"]
    assert "a@example.com" not in to_header
    assert "b@example.com" not in to_header
    assert "bot@example.com" in to_header      # จ่าหน้าถึงตัวระบบเอง
    assert rec["msg"]["Bcc"] is None           # ห้ามใส่หัว Bcc ลงในตัวข้อความ
    assert rec["to_addrs"] == ["a@example.com", "b@example.com"]


def test_explicit_to_keeps_recipient_in_to_header(smtp):
    """ระบุ to เอง (เคสจริง: OTP login) → To: ต้องเป็นคนนั้นเหมือนเดิม ไม่ซ่อนเป็น BCC"""
    common.send_email("รหัสเข้าสู่ระบบ", "<p>123456</p>", to=["user@example.com"])
    rec = smtp.sent[0]
    assert rec["msg"]["To"] == "user@example.com"
    assert rec["to_addrs"] == ["user@example.com"]


# ─────────────────────────── (ค) เพดานขนาดไฟล์แนบ ───────────────────────────
def test_oversize_attachment_is_dropped_but_email_still_sent(smtp, monkeypatch, caplog):
    """ไฟล์เกินเพดาน → ไม่แนบ แต่ยังส่งอีเมลสำเร็จ (โครงกลับไปเป็น alternative เดิม) + มี log เตือน"""
    monkeypatch.setattr(common, "EMAIL_ATTACH_MAX_MB", 0.001)  # 1 KB
    with caplog.at_level("WARNING"):
        assert common.send_email("หัวข้อ", "<p>x</p>",
                                 attachments=[("bbl_deposit_2026-06-18.pdf", b"x" * 5000)]) is True
    msg = smtp.sent[0]["msg"]
    assert msg.get_content_type() == "multipart/alternative"
    assert len(msg.get_payload()) == 1
    assert "bbl_deposit_2026-06-18.pdf" in caplog.text
    assert "EMAIL_ATTACH_MAX_MB" in caplog.text


def test_attachment_fits_boundary(monkeypatch):
    """เท่าเพดานพอดี = แนบได้ (เกินจริงเท่านั้นถึงตัดทิ้ง)"""
    monkeypatch.setattr(common, "EMAIL_ATTACH_MAX_MB", 1)
    assert common.attachment_fits("a.pdf", 1024 * 1024) is True
    assert common.attachment_fits("a.pdf", 1024 * 1024 + 1) is False


# ─────────────────────────── เนื้อความต้องตรงกับความจริงเรื่องไฟล์แนบ ───────────────────────────
def _bank():
    return {"code": "SCB", "name": "ธนาคารไทยพาณิชย์",
            "rate_targets": [{"key": "rate_12m", "label": "ประจำ 12 เดือน"}]}


@pytest.mark.parametrize("attached, must_have, must_not_have", [
    (True, "แนบไฟล์ประกาศฉบับเต็มมาด้วยแล้ว", "ไม่ได้แนบไฟล์ประกาศ"),
    (False, "ไม่ได้แนบไฟล์ประกาศมาด้วย", "แนบไฟล์ประกาศฉบับเต็มมาด้วยแล้ว"),
])
def test_new_rates_email_attachment_wording(attached, must_have, must_not_have):
    subject, body = common.build_new_rates_email(
        _bank(), "2026-01-15", "2025-12-01",
        rates={"rate_12m": 1.5}, prev_rates={"rate_12m": 1.25}, warnings=[],
        pdf_fname="scb_deposit_2026-01-15.pdf", attached=attached,
    )
    assert must_have in body
    assert must_not_have not in body


def test_new_rates_subject_keeps_bank_code_and_iso_date():
    """หัวข้อต้องมีรหัสธนาคารในวงเล็บเหลี่ยม + วันที่ ISO — ผู้ใช้ตั้ง filter จากตรงนี้"""
    subject, _ = common.build_new_rates_email(
        _bank(), "2026-01-15", None, rates={}, prev_rates=None, warnings=[],
        pdf_fname="x.pdf",
    )
    assert subject.startswith("[SCB]")
    assert "2026-01-15" in subject


def test_new_rates_email_shows_thai_date_and_warnings():
    _, body = common.build_new_rates_email(
        _bank(), "2026-01-15", "2025-12-01",
        rates={"rate_12m": 1.5}, prev_rates={"rate_12m": 1.25},
        warnings=["ประจำ 12 เดือน: เปลี่ยนแปลง +0.60% (เกินกว่า ±0.5%)"],
        pdf_fname="x.pdf",
    )
    assert "15 มกราคม 2569" in body          # วันที่ในเนื้อความเป็นไทยเต็มรูปแบบ
    assert "ข้อควรระวัง" in body
    assert "เกินกว่า ±0.5%" in body
    assert "ระบบติดตามอัตราดอกเบี้ยเงินฝาก (CheckRate)" in body


def test_thai_date_passthrough_on_bad_input():
    """วันที่รูปแบบแปลก ๆ ต้องไม่ทำให้ builder ล้ม — คืนค่าเดิมกลับไป ไม่ตัดข้อมูลทิ้ง"""
    assert common._thai_date("ไม่ใช่วันที่") == "ไม่ใช่วันที่"
    assert common._thai_date(None) == "None"
    assert common._thai_datetime("2026-06-18T09:00:12") == "18 มิถุนายน 2569 เวลา 09:00:12 น."
    assert common._thai_datetime("เมื่อวานนี้") == "เมื่อวานนี้"


def test_error_and_test_email_keep_all_fields():
    """อีเมล error/test เปลี่ยนแค่โทนภาษา ข้อมูลต้องครบเท่าเดิม"""
    subject, body = common.build_error_email(
        _bank(), "download", "PDF download failed", "2026-06-18T09:00:12")
    assert subject.startswith("[SCB ERROR]")
    assert "download" in body and "PDF download failed" in body
    assert "18 มิถุนายน 2569 เวลา 09:00:12 น." in body
    assert common.LOG_PATH in body
