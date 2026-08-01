import pytest


@pytest.fixture
def real_ip(fastapi_app, monkeypatch):
    from app.web import main
    monkeypatch.setattr(main, "_TRUST_PROXY", True)
    return main


def _req(xff=None, direct_ip="10.0.0.1"):
    class _Client:
        host = direct_ip

    class _Req:
        client = _Client()
        headers = {"x-forwarded-for": xff} if xff else {}

    return _Req()


def test_client_ip_trust_proxy_off_uses_socket_peer(fastapi_app, monkeypatch):
    from app.web import main
    monkeypatch.setattr(main, "_TRUST_PROXY", False)
    req = _req(xff="1.2.3.4, 10.0.0.9")
    assert main._client_ip(req) == "10.0.0.1"


def test_client_ip_default_hops_takes_rightmost(real_ip):
    # hops=1 (ค่าเริ่มต้น) = เชื่อ proxy ตัวเดียวที่ต่อกับเราโดยตรง — ตัวขวาสุดคือค่าที่มันเห็นจริง
    req = _req(xff="attacker-forged, 203.0.113.9")
    assert real_ip._client_ip(req) == "203.0.113.9"


def test_client_ip_two_hops(real_ip, monkeypatch):
    monkeypatch.setattr(real_ip, "TRUSTED_PROXY_HOPS", 2)
    req = _req(xff="attacker-forged, 203.0.113.9, 198.51.100.5")
    assert real_ip._client_ip(req) == "203.0.113.9"


def test_client_ip_short_list_falls_back_fail_closed(real_ip, monkeypatch):
    monkeypatch.setattr(real_ip, "TRUSTED_PROXY_HOPS", 3)
    req = _req(xff="203.0.113.9", direct_ip="10.0.0.1")
    assert real_ip._client_ip(req) == "10.0.0.1"
