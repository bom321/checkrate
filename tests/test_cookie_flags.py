"""
test_cookie_flags.py — SEC-08

COOKIE_SECURE/SESSION_MAX_AGE_DAYS ถูก bake เข้า SessionMiddleware ตอน import app.web.main ครั้งเดียว
(ผ่าน middleware ที่ session-scoped fixture `fastapi_app` สร้างไว้แล้ว) เปลี่ยน env ทีหลังในเทสต์นี้จึง
ไม่มีผลกับ instance นั้น — ทดสอบเฉพาะ main._cookie_kwargs() ซึ่งเป็นฟังก์ชันบริสุทธิ์ที่แยกออกมาเพื่อสิ่งนี้
โดยเฉพาะ (ตั้งใจไม่ import app.web.main ซ้ำด้วยการเล่น sys.modules — เคยลองแล้วมันไปเปลี่ยน module instance
ที่ fixture อื่นทั้งไฟล์อ้างอิงอยู่ ทำให้เทสต์ไฟล์อื่นพังข้ามไฟล์)
"""


def test_cookie_kwargs_default_no_secure_seven_days(fastapi_app):
    from app.web.main import _cookie_kwargs
    kw = _cookie_kwargs({})
    assert kw["https_only"] is False
    assert kw["max_age"] == 7 * 24 * 3600
    assert kw["same_site"] == "lax"


def test_cookie_kwargs_secure_enabled(fastapi_app):
    from app.web.main import _cookie_kwargs
    kw = _cookie_kwargs({"COOKIE_SECURE": "1"})
    assert kw["https_only"] is True


def test_cookie_kwargs_custom_max_age(fastapi_app):
    from app.web.main import _cookie_kwargs
    kw = _cookie_kwargs({"SESSION_MAX_AGE_DAYS": "3"})
    assert kw["max_age"] == 3 * 24 * 3600


def test_real_app_set_cookie_has_httponly_samesite_no_secure(client, monkeypatch):
    """login ผ่าน flow จริงของ app instance เดียวที่ทั้ง test session ใช้ร่วมกัน (สร้างโดยไม่ตั้ง
    COOKIE_SECURE — ดู conftest.py) แล้วอ่าน Set-Cookie response header ตรง ๆ (ไม่ใช่ cookie jar
    ของ TestClient ซึ่งไม่เก็บ flag HttpOnly/Secure ไว้)"""
    from app.web import auth
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 222222)
    auth.request_otp("test@example.com")
    r = client.post("/login/verify", data={"email": "test@example.com", "code": "222222", "next": "/"},
                     follow_redirects=False)
    assert r.status_code == 303
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()
    assert f"max-age={7 * 24 * 3600}" in set_cookie.lower()
