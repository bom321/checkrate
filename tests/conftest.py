"""
conftest.py — ตาข่ายรองรับสำหรับ test ฝั่งเว็บ

common.OUTPUT_DIR (และ path อื่น ๆ ที่ผูกกับมัน เช่น auth._SESSION_SECRET_FILE) อ่านค่าจาก env
DATA_DIR **ตอน import โมดูล** ไม่ใช่ตอนเรียกใช้ฟังก์ชัน — ต้องตั้ง env ให้ครบก่อน import
app.web.main เป็นครั้งแรกเสมอ ไม่งั้น test จะไปอ่าน/เขียนทับ data จริงใน ./data
"""
import os
import sys

import pytest


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    return str(tmp_path_factory.mktemp("checkrate_data"))


@pytest.fixture(scope="session")
def fastapi_app(data_dir):
    os.environ["DATA_DIR"] = data_dir
    os.environ["ADMIN_EMAILS"] = "test@example.com"
    os.environ["SESSION_SECRET"] = "testsecret"

    # กัน module เก่าที่อาจถูก import มาก่อน (เช่นจาก conftest อื่น) ค้าง OUTPUT_DIR ผิดที่
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]

    from app.web.main import app
    return app


@pytest.fixture
def client(fastapi_app):
    from fastapi.testclient import TestClient
    return TestClient(fastapi_app)


@pytest.fixture
def admin_client(client, monkeypatch):
    """client ที่ login แล้ว — เดินผ่าน flow OTP จริง (request_otp/login/verify) ไม่ได้ mint cookie เอง
    บังคับรหัสให้เป็นค่าคงที่ผ่าน monkeypatch เพราะ request_otp generate รหัสสุ่มแล้วส่งอีเมลจริง
    (ซึ่ง test env ไม่มี SMTP config — send_email แค่ log error แล้ว return False เฉย ๆ ไม่ throw)"""
    from app.web import auth
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: 654321)
    auth.request_otp("test@example.com")
    r = client.post("/login/verify", data={"email": "test@example.com", "code": "654321", "next": "/"},
                     follow_redirects=False)
    assert r.status_code == 303
    return client
