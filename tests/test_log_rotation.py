"""test_log_rotation.py — common._WeeklyLogHandler หมุนไฟล์ log รายสัปดาห์ (จันทร์-อาทิตย์) + ลบตามอายุ

ไม่แตะไฟล์ log จริง — ทุกเคสใช้ tmp_path และสวม common.datetime ให้ "วันนี้" คงที่
"""
from datetime import datetime as _real_datetime

import pytest

from app.monitor import common


def _freeze(monkeypatch, today: str):
    class _Fixed(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return _real_datetime.strptime(today, "%Y-%m-%d").replace(hour=9)
    monkeypatch.setattr(common, "datetime", _Fixed)


@pytest.fixture
def handler(tmp_path, monkeypatch):
    path = tmp_path / "rate_monitor.log"
    monkeypatch.setattr(common, "LOG_PATH", str(path))
    h = common._WeeklyLogHandler(str(path), encoding="utf-8")
    yield h, path
    h.close()


def _write(path, days):
    path.write_text("".join(f"{d} 09:00:00 | INFO    | บรรทัด {d}\n" for d in days), encoding="utf-8")


def test_same_week_does_not_rotate(handler, monkeypatch):
    """จันทร์-พุธของสัปดาห์เดียวกัน = ไฟล์เดียว ไม่หมุน (เดิมรายวันจะหมุนทุกวัน)"""
    h, path = handler
    _freeze(monkeypatch, "2026-10-21")                      # พุธ
    _write(path, ["2026-10-19", "2026-10-20"])              # จันทร์, อังคาร
    h._rotate_if_new_week()
    assert common.log_backup_paths() == []
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_new_week_moves_previous_week_out(handler, monkeypatch):
    """ขึ้นสัปดาห์ใหม่ → ของสัปดาห์ก่อนย้ายไป `.YYYY-MM-DD` (วันสุดท้ายในนั้น) ของสัปดาห์นี้อยู่ไฟล์หลัก"""
    h, path = handler
    _freeze(monkeypatch, "2026-10-26")                      # จันทร์
    _write(path, ["2026-10-20", "2026-10-25", "2026-10-26"])
    h._rotate_if_new_week()
    backups = common.log_backup_paths()
    assert [b.rsplit(".", 1)[-1] for b in backups] == ["2026-10-25"]
    assert "2026-10-20" in open(backups[0], encoding="utf-8").read()
    assert path.read_text(encoding="utf-8").startswith("2026-10-26")


def test_old_backups_deleted_by_age_not_count(handler, monkeypatch, tmp_path):
    """ลบตามอายุ LOG_RETENTION_DAYS — ไฟล์รายวันเดิมจำนวนมากที่ยังไม่ครบอายุต้องอยู่ครบ"""
    h, path = handler
    _freeze(monkeypatch, "2026-10-26")
    for d in ["2026-07-01", "2026-08-01"] + [f"2026-10-{i:02d}" for i in range(1, 19)]:
        (tmp_path / f"rate_monitor.log.{d}").write_text("x\n", encoding="utf-8")
    _write(path, ["2026-10-20", "2026-10-26"])
    h._rotate_if_new_week()
    days = {b.rsplit(".", 1)[-1] for b in common.log_backup_paths()}
    assert "2026-07-01" not in days                         # เกิน 90 วัน
    assert "2026-08-01" in days                             # ยังไม่ครบ 90 วัน
    assert len(days) == 1 + 18 + 1                          # 08-01 + รายวัน ต.ค. 18 ไฟล์ + ที่เพิ่งหมุน
