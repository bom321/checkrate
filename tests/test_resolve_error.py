"""test_resolve_error.py — resolver ที่หาลิงก์ประกาศไม่เจอต้อง raise common.ResolveError ไม่ใช่คืน None

คืน None = run_bank() ถือเป็น no_update เงียบ ๆ เมื่อมีประวัติแล้ว (เคสจริง BBL ต.ค. 2569: เว็บเปลี่ยน
ทั้งวันไม่มีอีเมลเลย) — ไม่ยิงเน็ตจริง สวมฟังก์ชันโหลดหน้าของแต่ละธนาคารด้วยตัวปลอม
"""
import pytest

from app.monitor import common
from app.monitor.banks import bay, bbl, ktb


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code, self.text = status_code, text


def test_bbl_no_links_raises(monkeypatch):
    monkeypatch.setattr(bbl, "_fetch_listing", lambda session=None: None)
    with pytest.raises(common.ResolveError):
        bbl.resolve_latest_url({"code": "BBL"})


def test_bay_no_links_raises(monkeypatch):
    monkeypatch.setattr(bay, "_fetch_deposit_page_links", lambda *a, **k: [])
    with pytest.raises(common.ResolveError):
        bay.resolve_latest_url({"code": "BAY"})


@pytest.mark.parametrize("get_page", [
    lambda s, c: (_ for _ in ()).throw(ConnectionError("timeout")),   # โหลดหน้าไม่ได้
    lambda s, c: _Resp(503),                                          # HTTP ไม่ใช่ 200
    lambda s, c: _Resp(200, "<html>ไม่มีลิงก์ PDF</html>"),             # หน้าเว็บเปลี่ยน
])
def test_ktb_failures_raise(monkeypatch, get_page):
    monkeypatch.setattr(ktb, "_new_session", lambda: None)
    monkeypatch.setattr(ktb, "_get_rates_page", get_page)
    with pytest.raises(common.ResolveError):
        ktb.resolve_latest_url({"code": "KTB"})


def test_bbl_listing_reads_new_site_links(monkeypatch):
    """เว็บใหม่ (AEM, ต.ค. 2569): /content/dam/... คั่น `-` · ย้อนหลังอยู่ใน fragment แยก — และยังรับแบบเดิม"""
    pages = {
        bbl.RATES_PAGE_URL: '<a href="/content/dam/bangkokbank/x/deposit-interest-rates/2026/'
                            'depositrates-15oct2026.pdf">ปัจจุบัน</a>',
        bbl.HISTORY_FRAGMENT_URL: '<a href="/content/dam/bangkokbank/x/deposit-interest-rates/2026/'
                                  'depositrates-3sep2026.pdf">ย้อนหลัง</a>'
                                  '<a href="/-/media/x/deposit-interest-rates/2025/'
                                  'depositrates_18jun2025.pdf">เดิม</a>',
    }

    class _Session:
        def get(self, url, timeout=None):
            return _Resp(200, pages[url])

    links = bbl._fetch_listing(_Session())
    assert [d for d, _ in links] == ["2025-06-18", "2026-09-03", "2026-10-15"]
    assert links[-1][1].endswith("/2026/depositrates-15oct2026.pdf")
