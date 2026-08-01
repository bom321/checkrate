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
