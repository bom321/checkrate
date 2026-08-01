import os

import pytest


@pytest.fixture
def bank_with_pdf(fastapi_app, data_dir):
    """สร้างธนาคารทดสอบ 1 ตัว + ไฟล์ PDF ปลอมให้ /pdf/{code}/{filename} มีของจริงให้เสิร์ฟ"""
    from app.web import data_access as da

    da.save_banks([{"code": "SCB", "name": "ไทยพาณิชย์", "enabled": True, "rate_targets": []}])
    pdf_dir = os.path.join(data_dir, "pdfs", "SCB")
    os.makedirs(pdf_dir, exist_ok=True)
    fname = "scb_deposit_2026-01-01.pdf"
    with open(os.path.join(pdf_dir, fname), "wb") as f:
        f.write(b"%PDF-1.4 fake")
    return fname


def test_pdf_traversal_via_code_is_rejected(client, bank_with_pdf, data_dir):
    # เคสจริงของช่องโหว่: code=".." ทำให้ pdf_dir กลายเป็น DATA_DIR เอง — วางไฟล์ปลอมไว้ตรงนั้น
    # (นอกโฟลเดอร์ pdfs/{CODE} ปกติ) แล้วยืนยันว่าเข้าไม่ถึงผ่าน /pdf/../secret.pdf
    #
    # ใช้ %2e%2e (percent-encoded) แทน ".." ตรง ๆ เพราะ httpx (ที่ TestClient ใช้ข้างใน) resolve
    # dot-segment ของ URL ให้เองตอนสร้าง request ทำให้ ".." ตรง ๆ ไม่มีทางไปถึงแอปเลย (ทดสอบแล้ว
    # scope['path'] กลายเป็น '/secret.pdf' ไปเลย ก่อนแม้แต่จะแมตช์ route) — เคสจริงบนอินเทอร์เน็ต
    # เป็นไปได้ผ่าน request ที่ไม่ได้ normalize เอง (raw socket, curl --path-as-is) ค่า %2e%2e
    # จำลองสถานการณ์นั้น: ผ่าน httpx มาได้เป็น literal ไม่ถูก normalize แล้วแอปฝั่ง server
    # (Starlette) percent-decode คืนเป็น ".." ตอน routing เหมือนเคสจริง — ยืนยันแล้วว่าโค้ดเดิม
    # (ก่อนแก้ SEC-02) รั่วจริงด้วยรีเควสต์แบบนี้ (คืนไฟล์ secret.pdf, HTTP 200)
    with open(os.path.join(data_dir, "secret.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 secret")

    r = client.get("/pdf/%2e%2e/secret.pdf")
    assert r.status_code == 404


def test_pdf_unknown_bank_code_is_rejected(client, bank_with_pdf):
    r = client.get(f"/pdf/NOSUCHBANK/{bank_with_pdf}")
    assert r.status_code == 404


def test_pdf_valid_bank_serves_file(client, bank_with_pdf):
    r = client.get(f"/pdf/SCB/{bank_with_pdf}")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
