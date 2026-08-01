import pytest

from app.monitor import common


@pytest.mark.parametrize("url", [
    "https://scb.co.th/x.pdf",
    "http://example.com/a.pdf",
])
def test_validate_source_url_accepts_http_https(url):
    common.validate_source_url(url)   # ไม่ throw


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "-K/tmp/evil",
    "ftp://example.com/a.pdf",
    "",
    "   ",
    None,
])
def test_validate_source_url_rejects_everything_else(url):
    with pytest.raises(ValueError):
        common.validate_source_url(url)


def test_download_pdf_refuses_dangerous_url_without_spawning_curl(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("ไม่ควรยิง subprocess เลยถ้า URL ไม่ผ่าน validate_source_url")

    monkeypatch.setattr(common.subprocess, "run", _boom)
    assert common.download_pdf("-K/tmp/evil", "https://example.com", mode="curl") is None
    assert common.download_pdf("file:///etc/passwd", "https://example.com", mode="impersonate") is None


def test_config_rejects_bad_latest_pdf_url(admin_client):
    payload = {"banks": [{
        "code": "TEST", "name": "ทดสอบ", "enabled": False,
        "latest_pdf_url": "file:///etc/passwd",
        "prev_pdf_url": "", "referer": "https://example.com",
        "rate_targets": [],
    }]}
    r = admin_client.post("/api/config", json=payload)
    assert r.status_code == 400
    assert "latest_pdf_url" in r.json()["error"]


def test_config_accepts_valid_urls(admin_client):
    payload = {"banks": [{
        "code": "TEST", "name": "ทดสอบ", "enabled": False,
        "latest_pdf_url": "https://example.com/a.pdf",
        "prev_pdf_url": "", "referer": "https://example.com",
        "rate_targets": [],
    }]}
    r = admin_client.post("/api/config", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True
