from app.monitor import common


def _bank(label="<b>x</b>", name="<script>alert(1)</script>ธนาคาร"):
    return {"code": "TST", "name": name,
            "rate_targets": [{"key": "rate_3m_1m", "label": label}]}


def test_build_new_rates_email_escapes_label_and_name():
    bank = _bank()
    subject, body = common.build_new_rates_email(
        bank, "2026-01-01", "2025-12-01",
        rates={"rate_3m_1m": 1.0}, prev_rates={"rate_3m_1m": 0.9},
        warnings=["<img src=x onerror=alert(1)>"], pdf_fname="<x>.pdf",
    )
    assert "<b>x</b>" not in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body
    assert "<script>" not in body
    assert "<img src=x onerror=alert(1)>" not in body


def test_build_error_email_escapes_exception_message():
    bank = _bank()
    subject, body = common.build_error_email(
        bank, "download", "<script>alert(document.cookie)</script>", "2026-01-01T00:00:00",
    )
    assert "<script>alert(document.cookie)</script>" not in body
    assert "&lt;script&gt;" in body


def test_build_test_email_escapes_smtp_fields(monkeypatch):
    monkeypatch.setattr(common, "_active_smtp_config", lambda: {
        "provider": "gmail", "label": "gmail", "host": "<b>evil</b>", "port": 465,
        "user": "<i>x</i>@example.com", "password": "x", "sender": "x", "insecure": False,
    })
    monkeypatch.setattr(common, "get_recipients", lambda: ["<u>y</u>@example.com"])
    subject, body = common.build_test_email()
    assert "<b>evil</b>" not in body
    assert "<i>x</i>" not in body
    assert "<u>y</u>" not in body
