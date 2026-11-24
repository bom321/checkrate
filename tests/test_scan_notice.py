"""เตือนคุณภาพสแกนของ BBL (bbl.scan_notice) — ตรวจจาก bit depth/ความกว้างของภาพหน้า 1"""
import io

from PIL import Image

from app.monitor import banks
from app.monitor.banks import bbl


def _pdf(mode: str, size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, "white" if mode != "1" else 1).save(buf, format="PDF", resolution=200)
    return buf.getvalue()


def test_one_bit_scan_warns():
    msg = bbl.scan_notice(_pdf("1", (2344, 1654)))
    assert msg and "1 บิต" in msg and "เทียบ" in msg


def test_eight_bit_scan_is_silent():
    assert bbl.scan_notice(_pdf("RGB", (2340, 1654))) is None


def test_low_resolution_warns_even_if_8bit():
    msg = bbl.scan_notice(_pdf("RGB", (1000, 700)))
    assert msg and "1000" in msg and "1 บิต" not in msg


def test_unreadable_or_imageless_pdf_is_silent():
    assert bbl.scan_notice(b"not a pdf") is None


def test_dispatch_is_noop_for_banks_without_hook_and_swallows_errors(monkeypatch):
    assert banks.scan_notice(b"x", {"code": "ZZZ", "parser": "no-such-parser"}) is None

    def boom(_):
        raise RuntimeError("x")
    monkeypatch.setattr(bbl, "scan_notice", boom)
    assert banks.scan_notice(b"x", {"code": "BBL", "parser": bbl.PARSER_IDS[0]}) is None
