"""
test_version.py — ป้ายเวอร์ชัน (app/version.py) ที่ใช้ตอบว่า "เครื่องนี้รันโค้ดชุดไหนอยู่"

จุดที่ต้องไม่พังคือลำดับการหาค่า: env ที่ bake ตอน build ต้องชนะ git เสมอ เพราะในคอนเทนเนอร์จริง
ไม่มี `.git/` ให้ถาม (อยู่ใน .dockerignore) — ถ้าลำดับสลับ คนดู footer จะเห็น commit ของเครื่องที่ build
แทนที่จะเป็นของโค้ดใน image (หรือไม่เห็นอะไรเลย)
"""
import pytest

from app import version


@pytest.fixture(autouse=True)
def clear_cache():
    version.build_info(refresh=True)
    yield
    version._cache = None


def test_env_ชนะ_git(monkeypatch):
    monkeypatch.setenv("APP_COMMIT", "deadbeef1234567")
    monkeypatch.setenv("APP_BUILD_DATE", "2026-08-02T09:15:00+07:00")
    info = version.build_info(refresh=True)
    assert info["source"] == "build"
    assert info["commit"] == "deadbeef1234"          # ตัดเหลือ 12 ตัว
    assert info["date"] == "2026-08-02T09:15:00+07:00"
    assert info["label"] == f"v{version.VERSION} (deadbeef1234)"


def test_ไม่มี_env_ถอยไปใช้_git_หรือ_mtime(monkeypatch):
    monkeypatch.delenv("APP_COMMIT", raising=False)
    monkeypatch.delenv("APP_BUILD_DATE", raising=False)
    info = version.build_info(refresh=True)
    assert info["source"] in ("git", "mtime")
    assert info["version"] == version.VERSION
    assert info["date"]                              # ต้องบอกวันที่แก้ไขล่าสุดได้เสมอ


def test_mtime_เป็นทางสุดท้ายเมื่อ_git_ใช้ไม่ได้(monkeypatch):
    monkeypatch.delenv("APP_COMMIT", raising=False)
    monkeypatch.setattr(version, "_git", lambda *a: None)
    info = version.build_info(refresh=True)
    assert info["source"] == "mtime"
    assert info["commit"] == ""
    assert info["label"] == f"v{version.VERSION}"


def test_api_version_และ_health(client):
    v = client.get("/api/version").json()
    assert v["version"] == version.VERSION
    assert set(v) >= {"version", "commit", "date", "dirty", "source", "label"}

    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["version"] == version.VERSION


def test_footer_แสดงเวอร์ชันในทุกหน้า(client):
    for path in ("/", "/login"):
        html = client.get(path).text
        assert f"v{version.VERSION}" in html
        # ข้อความในป้ายเปลี่ยนเป็น "ปรับปรุงล่าสุด" ตั้งแต่คอมมิต 0cf3831 (base.html) — test ตกค้างอยู่
        assert "ปรับปรุงล่าสุด" in html
