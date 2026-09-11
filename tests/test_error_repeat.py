"""
test_error_repeat.py — นับ error ซ้ำ + หยุดส่งอีเมลหลัง N ครั้ง + ไฟล์เดิมไม่ใช่ error + แถบสถานะบนเว็บ
(สเปก: docs/superpowers/specs/2026-09-11-error-email-repeat-design.md)

ฝั่ง monitor: common.OUTPUT_DIR ถูกอ่านตอน import — ทุกเทสต์ที่แตะไฟล์ result ต้อง monkeypatch
OUTPUT_DIR ไปที่ tmp_path ก่อน ไม่งั้นจะเขียนทับ data จริง
"""
import json
import os

import pytest


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    from app.monitor import common
    monkeypatch.setattr(common, "OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _read(out_dir, code="TST"):
    with open(os.path.join(out_dir, f"{code.lower()}_result.json"), encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────── read_result / record_error ───────────────────────────
def test_read_result_none_when_missing(out_dir):
    from app.monitor import common
    assert common.read_result("TST") is None


def test_read_result_none_when_corrupt(out_dir):
    from app.monitor import common
    (out_dir / "tst_result.json").write_text("{not json", encoding="utf-8")
    assert common.read_result("TST") is None


def test_record_error_first_time(out_dir):
    from app.monitor import common
    res = common.record_error("TST", "download", "PDF download failed")
    assert res["type"] == "error"
    assert res["step"] == "download"
    assert res["repeat_count"] == 1
    assert res["first_seen"] == res["timestamp"]
    assert _read(out_dir)["repeat_count"] == 1


def test_record_error_same_issue_increments_and_keeps_first_seen(out_dir):
    from app.monitor import common
    first = common.record_error("TST", "download", "PDF download failed")
    second = common.record_error("TST", "download", "PDF download failed")
    assert second["repeat_count"] == 2
    assert second["first_seen"] == first["first_seen"]


def test_record_error_different_step_resets(out_dir):
    from app.monitor import common
    common.record_error("TST", "download", "PDF download failed")
    res = common.record_error("TST", "date_extraction", "ไม่สามารถดึงวันที่มีผลจาก PDF ได้")
    assert res["repeat_count"] == 1


def test_record_error_different_message_resets(out_dir):
    from app.monitor import common
    common.record_error("TST", "download", "PDF download failed")
    res = common.record_error("TST", "download", "PDF download failed (timeout)")
    assert res["repeat_count"] == 1


def test_record_error_after_success_resets(out_dir):
    from app.monitor import common
    common.record_error("TST", "download", "PDF download failed")
    common.write_result("no_update", bank="TST", effective_date="2026-09-01")
    res = common.record_error("TST", "download", "PDF download failed")
    assert res["repeat_count"] == 1


def test_record_error_legacy_result_without_new_keys_counts_from_one(out_dir):
    """result.json จากโค้ดรุ่นก่อน (ไม่มี repeat_count/first_seen) ถือว่าเคยเจอ 1 ครั้งแล้ว"""
    from app.monitor import common
    (out_dir / "tst_result.json").write_text(json.dumps({
        "type": "error", "timestamp": "2026-09-05T09:00:07", "bank": "TST",
        "step": "download", "message": "PDF download failed",
    }), encoding="utf-8")
    res = common.record_error("TST", "download", "PDF download failed")
    assert res["repeat_count"] == 2
    assert res["first_seen"] == "2026-09-05T09:00:07"


def test_record_error_keeps_extra_kwargs(out_dir):
    from app.monitor import common
    res = common.record_error("TST", "rate_extraction", "x", effective_date="2026-09-05")
    assert res["effective_date"] == "2026-09-05"


def test_mark_error_email_sent(out_dir):
    from app.monitor import common
    common.record_error("TST", "download", "PDF download failed")
    common.mark_error_email_sent("TST", True)
    assert _read(out_dir)["email_sent"] is True
    # ไม่ใช่ error → ไม่แตะไฟล์
    common.write_result("no_update", bank="TST", effective_date="2026-09-01")
    common.mark_error_email_sent("TST", True)
    assert "email_sent" not in _read(out_dir)


# ─────────────────────────── error_email_max_repeats ───────────────────────────
def test_max_repeats_default_is_two(monkeypatch):
    from app.monitor import common
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    assert common.error_email_max_repeats() == 2


def test_max_repeats_reads_env(monkeypatch):
    from app.monitor import common
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "5")
    assert common.error_email_max_repeats() == 5


def test_max_repeats_zero_means_unlimited(monkeypatch):
    from app.monitor import common
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "0")
    assert common.error_email_max_repeats() == 0


def test_max_repeats_invalid_falls_back_to_default(monkeypatch):
    from app.monitor import common
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "abc")
    assert common.error_email_max_repeats() == 2
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "-3")
    assert common.error_email_max_repeats() == 2


def test_should_email_error():
    from app.monitor import common
    assert common.should_email_error(1, 2) is True
    assert common.should_email_error(2, 2) is True
    assert common.should_email_error(3, 2) is False
    assert common.should_email_error(99, 0) is True


# ─────────────────────────── build_error_email ───────────────────────────
def _bank():
    return {"code": "TST", "name": "ธนาคารทดสอบ", "rate_targets": []}


REPEAT_TXT = "ติดต่อกันเป็นครั้งที่"
PAUSE_TXT = "จะไม่ส่งอีเมลเรื่องนี้ซ้ำอีก"


def test_error_email_first_time_has_no_repeat_text():
    from app.monitor import common
    subject, body = common.build_error_email(_bank(), "download", "PDF download failed",
                                             "2026-09-11T09:00:00")
    assert subject.startswith("[TST ERROR]")
    assert REPEAT_TXT not in body
    assert PAUSE_TXT not in body


def test_error_email_last_repeat_warns_about_pause():
    from app.monitor import common
    subject, body = common.build_error_email(_bank(), "download", "PDF download failed",
                                             "2026-09-11T09:00:00", repeat_count=2,
                                             first_seen="2026-09-10T09:00:00", max_repeats=2)
    assert subject.startswith("[TST ERROR]")
    assert "ติดต่อกันเป็นครั้งที่ 2" in body
    assert "10 กันยายน 2569" in body
    assert PAUSE_TXT in body


def test_error_email_middle_repeat_has_count_but_no_pause():
    from app.monitor import common
    _, body = common.build_error_email(_bank(), "download", "PDF download failed",
                                       "2026-09-11T09:00:00", repeat_count=2,
                                       first_seen="2026-09-10T09:00:00", max_repeats=5)
    assert "ติดต่อกันเป็นครั้งที่ 2" in body
    assert PAUSE_TXT not in body


def test_error_email_unlimited_never_warns_about_pause():
    from app.monitor import common
    _, body = common.build_error_email(_bank(), "download", "PDF download failed",
                                       "2026-09-11T09:00:00", repeat_count=7,
                                       first_seen="2026-09-05T09:00:00", max_repeats=0)
    assert "ติดต่อกันเป็นครั้งที่ 7" in body
    assert PAUSE_TXT not in body


def test_error_email_escapes_first_seen():
    from app.monitor import common
    _, body = common.build_error_email(_bank(), "download", "x", "2026-09-11T09:00:00",
                                       repeat_count=2, first_seen="<b>evil</b>", max_repeats=2)
    assert "<b>evil</b>" not in body


# ─────────────────────────── _find_saved_pdf_by_hash ───────────────────────────
def test_find_saved_pdf_by_hash_matches_any_file(tmp_path):
    from app.monitor import rate_monitor
    (tmp_path / "tst_deposit_2026-08-01.pdf").write_bytes(b"%PDF-old")
    (tmp_path / "tst_deposit_2026-09-05.pdf").write_bytes(b"%PDF-new")
    assert rate_monitor._find_saved_pdf_by_hash(str(tmp_path), "TST", b"%PDF-new") \
        == "tst_deposit_2026-09-05.pdf"
    # ตรงกับไฟล์เก่าที่ไม่ใช่ล่าสุดก็ต้องเจอ (ความหมาย = "ไฟล์นี้มีในระบบแล้ว")
    assert rate_monitor._find_saved_pdf_by_hash(str(tmp_path), "TST", b"%PDF-old") \
        == "tst_deposit_2026-08-01.pdf"


def test_find_saved_pdf_by_hash_one_byte_differs(tmp_path):
    from app.monitor import rate_monitor
    (tmp_path / "tst_deposit_2026-09-05.pdf").write_bytes(b"%PDF-new")
    assert rate_monitor._find_saved_pdf_by_hash(str(tmp_path), "TST", b"%PDF-neW") is None


def test_find_saved_pdf_by_hash_ignores_other_banks_and_non_pdf(tmp_path):
    from app.monitor import rate_monitor
    (tmp_path / "bay_deposit_2026-09-05.pdf").write_bytes(b"%PDF-x")
    (tmp_path / "tst_deposit_2026-09-05.txt").write_bytes(b"%PDF-x")
    assert rate_monitor._find_saved_pdf_by_hash(str(tmp_path), "TST", b"%PDF-x") is None


def test_find_saved_pdf_by_hash_missing_dir(tmp_path):
    from app.monitor import rate_monitor
    assert rate_monitor._find_saved_pdf_by_hash(str(tmp_path / "nope"), "TST", b"x") is None


# ─────────────────────────── run_bank: A (ไฟล์เดิม) + B (นับซ้ำ/หยุดเมล) ───────────────────────────
@pytest.fixture
def bank_env(out_dir, monkeypatch):
    """DATA_DIR ชั่วคราว + ธนาคาร TST ที่ resolve/download สำเร็จเสมอ แต่อ่านวันที่ไม่ได้
    (เลียนแบบ BAY) — ตัดอีเมลจริงออก นับการเรียกแทน"""
    from app.monitor import rate_monitor, banks, common
    pdf_dir = out_dir / "pdfs" / "TST"
    pdf_dir.mkdir(parents=True)
    csv_path = out_dir / "tst_deposit_rate.csv"
    csv_path.write_text("effective_date,rate_3m_1m,change_rate_3m_1m\n2026-09-05,1.00,0.00\n",
                        encoding="utf-8")
    bank = {"code": "TST", "name": "ธนาคารทดสอบ", "enabled": True, "parser": "scb",
            "referer": "", "latest_pdf_url": "https://example.test/x.pdf", "prev_pdf_url": "",
            "rate_targets": [{"key": "rate_3m_1m", "label": "ประจำ 3 เดือน"}]}
    sent = []
    monkeypatch.setattr(rate_monitor, "get_bank_paths", lambda code: (str(pdf_dir), str(csv_path)))
    monkeypatch.setattr(rate_monitor, "initialize_if_needed", lambda *a, **k: None)
    monkeypatch.setattr(banks, "resolve_latest_url", lambda b: b["latest_pdf_url"])
    monkeypatch.setattr(rate_monitor, "download_pdf", lambda *a, **k: b"%PDF-served")
    monkeypatch.setattr(banks, "effective_date", lambda pdf_bytes, b: None)
    monkeypatch.setattr(rate_monitor, "send_email", lambda *a, **k: sent.append(a) or True)
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    return {"bank": bank, "pdf_dir": pdf_dir, "sent": sent, "out": out_dir}


def test_run_bank_same_file_is_no_update(bank_env):
    from app.monitor import rate_monitor
    (bank_env["pdf_dir"] / "tst_deposit_2026-09-05.pdf").write_bytes(b"%PDF-served")
    rate_monitor.run_bank(bank_env["bank"])
    res = _read(bank_env["out"])
    assert res["type"] == "no_update"
    assert res["effective_date"] == "2026-09-05"
    assert res["matched_pdf"] == "tst_deposit_2026-09-05.pdf"
    assert bank_env["sent"] == []


def test_run_bank_unknown_file_emails_twice_then_stops(bank_env):
    from app.monitor import rate_monitor
    (bank_env["pdf_dir"] / "tst_deposit_2026-09-05.pdf").write_bytes(b"%PDF-other")
    for _ in range(3):
        rate_monitor.run_bank(bank_env["bank"])
    res = _read(bank_env["out"])
    assert res["type"] == "error"
    assert res["step"] == "date_extraction"
    assert res["repeat_count"] == 3
    assert res["email_sent"] is False
    assert len(bank_env["sent"]) == 2
    # ฉบับที่ 2 ต้องเตือนว่าจะเงียบ ฉบับแรกไม่ต้อง
    assert PAUSE_TXT not in bank_env["sent"][0][1]
    assert PAUSE_TXT in bank_env["sent"][1][1]


def test_run_bank_success_resets_counter(bank_env, monkeypatch):
    from app.monitor import rate_monitor, banks
    (bank_env["pdf_dir"] / "tst_deposit_2026-09-05.pdf").write_bytes(b"%PDF-other")
    rate_monitor.run_bank(bank_env["bank"])
    rate_monitor.run_bank(bank_env["bank"])
    assert _read(bank_env["out"])["repeat_count"] == 2
    # รอบนี้อ่านวันที่ได้และตรงกับ CSV → no_update → ตัวนับหาย
    monkeypatch.setattr(banks, "effective_date", lambda pdf_bytes, b: "2026-09-05")
    rate_monitor.run_bank(bank_env["bank"])
    assert _read(bank_env["out"])["type"] == "no_update"
    monkeypatch.setattr(banks, "effective_date", lambda pdf_bytes, b: None)
    rate_monitor.run_bank(bank_env["bank"])
    assert _read(bank_env["out"])["repeat_count"] == 1
    assert len(bank_env["sent"]) == 3


def test_run_bank_unlimited_env_emails_every_time(bank_env, monkeypatch):
    from app.monitor import rate_monitor
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "0")
    for _ in range(4):
        rate_monitor.run_bank(bank_env["bank"])
    assert len(bank_env["sent"]) == 4
    assert _read(bank_env["out"])["email_sent"] is True


# ─────────────────────────── data_access.error_status ───────────────────────────
def _write_result(data_dir, code, data):
    with open(os.path.join(data_dir, f"{code.lower()}_result.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def test_error_status_none_when_not_error(fastapi_app, data_dir):
    from app.web import data_access as da
    _write_result(data_dir, "ES1", {"type": "no_update", "timestamp": "2026-09-11T09:00:00"})
    assert da.error_status("ES1") is None
    assert da.error_status("ES-none") is None


def test_error_status_days_and_pause(fastapi_app, data_dir, monkeypatch):
    from app.web import data_access as da
    from datetime import date
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    _write_result(data_dir, "ES2", {
        "type": "error", "timestamp": "2026-09-12T09:00:00", "step": "date_extraction",
        "message": "ไม่สามารถดึงวันที่มีผลจาก PDF ได้", "first_seen": "2026-09-05T09:00:07",
        "repeat_count": 7, "email_sent": False,
    })
    st = da.error_status("ES2")
    assert st["days"] == 7
    assert st["repeat_count"] == 7
    assert st["emails_paused"] is True
    assert st["step_label"] == "อ่านวันที่มีผลจาก PDF"
    assert st["message"] == "ไม่สามารถดึงวันที่มีผลจาก PDF ได้"
    assert st["first_seen"] == "2026-09-05T09:00:07"


def test_error_status_calendar_days_not_24h(fastapi_app, data_dir, monkeypatch):
    from app.web import data_access as da
    from datetime import date
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    _write_result(data_dir, "ES3", {"type": "error", "timestamp": "2026-09-12T08:00:00",
                                    "step": "download", "message": "x",
                                    "first_seen": "2026-09-11T23:30:00", "repeat_count": 2})
    assert da.error_status("ES3")["days"] == 1


def test_error_status_not_paused_below_max(fastapi_app, data_dir, monkeypatch):
    from app.web import data_access as da
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    _write_result(data_dir, "ES4", {"type": "error", "timestamp": "2026-09-12T09:00:00",
                                    "step": "download", "message": "x",
                                    "first_seen": "2026-09-12T09:00:00", "repeat_count": 1})
    assert da.error_status("ES4")["emails_paused"] is False


def test_error_status_unlimited_env_never_paused(fastapi_app, data_dir, monkeypatch):
    from app.web import data_access as da
    monkeypatch.setenv("ERROR_EMAIL_MAX_REPEATS", "0")
    _write_result(data_dir, "ES5", {"type": "error", "timestamp": "2026-09-12T09:00:00",
                                    "step": "download", "message": "x",
                                    "first_seen": "2026-09-01T09:00:00", "repeat_count": 50})
    assert da.error_status("ES5")["emails_paused"] is False


def test_error_status_legacy_result(fastapi_app, data_dir, monkeypatch):
    """result จากโค้ดรุ่นก่อน: ไม่มี first_seen/repeat_count → ใช้ timestamp, นับ 1"""
    from app.web import data_access as da
    from datetime import date
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    _write_result(data_dir, "ES6", {"type": "error", "timestamp": "2026-09-10T09:00:00",
                                    "step": "weird_step", "message": "x"})
    st = da.error_status("ES6")
    assert st["days"] == 2
    assert st["repeat_count"] == 1
    assert st["first_seen"] == "2026-09-10T09:00:00"
    assert st["step_label"] == "weird_step"


def test_error_status_bad_first_seen_gives_zero_days(fastapi_app, data_dir):
    from app.web import data_access as da
    _write_result(data_dir, "ES7", {"type": "error", "timestamp": "garbage", "step": "download",
                                    "message": "x", "first_seen": "garbage", "repeat_count": "??"})
    st = da.error_status("ES7")
    assert st["days"] == 0
    assert st["repeat_count"] == 1


# ─────────────────────────── หน้าเว็บ ───────────────────────────
@pytest.fixture
def web_bank(fastapi_app, data_dir):
    """ธนาคาร WEB ที่มี CSV 1 แถว ให้หน้า / และ /bank/WEB render ได้"""
    from app.web import data_access as da
    banks = da.load_banks()
    if not any(b["code"] == "WEB" for b in banks):
        banks.append({"code": "WEB", "name": "ธนาคารเว็บทดสอบ", "enabled": True, "parser": "scb",
                      "referer": "", "latest_pdf_url": "", "prev_pdf_url": "",
                      "rate_targets": [{"key": "rate_3m_1m", "label": "ประจำ 3 เดือน"}]})
        da.save_banks(banks)
    with open(os.path.join(data_dir, "web_deposit_rate.csv"), "w", encoding="utf-8") as f:
        f.write("effective_date,rate_3m_1m,change_rate_3m_1m\n2026-09-05,1.00,0.00\n")
    return "WEB"


def _error_result(days_ago_first_seen="2026-09-05T09:00:07", repeat_count=7, step="date_extraction"):
    return {"type": "error", "timestamp": "2026-09-12T09:00:00", "step": step,
            "message": "ไม่สามารถดึงวันที่มีผลจาก PDF ได้ <secret>", "first_seen": days_ago_first_seen,
            "repeat_count": repeat_count, "email_sent": False}


def test_bank_page_shows_error_bar_public(client, web_bank, data_dir, monkeypatch):
    from app.web import data_access as da
    from datetime import date
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    _write_result(data_dir, web_bank, _error_result())
    r = client.get(f"/bank/{web_bank}?month=2026-09")
    assert r.status_code == 200
    assert "ตรวจสอบประกาศไม่สำเร็จติดต่อกัน 7 วัน" in r.text
    assert "อ่านวันที่มีผลจาก PDF" in r.text
    assert "หยุดส่งอีเมลแจ้งแล้ว" in r.text
    # message เต็มเป็นของ admin เท่านั้น
    assert "&lt;secret&gt;" not in r.text and "<secret>" not in r.text
    assert 'id="error-upload-link"' not in r.text


def test_bank_page_error_bar_admin_sees_message_and_upload_link(admin_client, web_bank, data_dir):
    _write_result(data_dir, web_bank, _error_result())
    r = admin_client.get(f"/bank/{web_bank}?month=2026-09")
    assert r.status_code == 200
    assert "&lt;secret&gt;" in r.text          # escape แล้ว ไม่หลุดเป็น HTML
    assert "<secret>" not in r.text
    assert 'id="error-upload-link"' in r.text


def test_bank_page_error_bar_today_and_not_paused(client, web_bank, data_dir, monkeypatch):
    from app.web import data_access as da
    from datetime import date
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    monkeypatch.delenv("ERROR_EMAIL_MAX_REPEATS", raising=False)
    _write_result(data_dir, web_bank, _error_result("2026-09-12T09:00:00", repeat_count=1,
                                                    step="download"))
    r = client.get(f"/bank/{web_bank}?month=2026-09")
    assert "ตรวจสอบประกาศไม่สำเร็จ (วันนี้)" in r.text
    assert "หยุดส่งอีเมลแจ้งแล้ว" not in r.text


def test_bank_page_no_error_bar_when_ok(client, web_bank, data_dir):
    _write_result(data_dir, web_bank, {"type": "no_update", "timestamp": "2026-09-12T09:00:00",
                                       "effective_date": "2026-09-05"})
    r = client.get(f"/bank/{web_bank}?month=2026-09")
    assert "ตรวจสอบประกาศไม่สำเร็จ" not in r.text


def test_overview_card_shows_error_badge(client, web_bank, data_dir, monkeypatch):
    from app.web import data_access as da
    from datetime import date
    monkeypatch.setattr(da, "_today", lambda: date(2026, 9, 12))
    _write_result(data_dir, web_bank, _error_result())
    r = client.get("/?month=2026-09")
    assert r.status_code == 200
    assert "ตรวจสอบล้มเหลว 7 วัน" in r.text
    _write_result(data_dir, web_bank, _error_result("2026-09-12T09:00:00", repeat_count=1))
    r = client.get("/?month=2026-09")
    assert "ตรวจสอบล้มเหลว วันนี้" in r.text
