def test_overview_public_no_login(client):
    r = client.get("/")
    assert r.status_code == 200


def test_config_page_redirects_to_login(client):
    r = client.get("/config", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_api_config_requires_login(client):
    r = client.get("/api/config")
    assert r.status_code == 401


def test_verify_otp_rejects_wrong_code_and_reuse(fastapi_app, monkeypatch):
    from app.web import auth

    # บังคับให้รหัสที่ generate เป็นค่าคงที่ ตรวจได้ว่าใช้ถูก/ผิดจริง
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 123456)
    auth.request_otp("test@example.com")

    assert auth.verify_otp("test@example.com", "000000") is False
    assert auth.verify_otp("test@example.com", "123456") is True
    # รหัสถูกใช้ไปแล้ว — ใช้ซ้ำครั้งที่สองต้องไม่ผ่าน
    assert auth.verify_otp("test@example.com", "123456") is False
