import pytest


@pytest.fixture
def seeded_bank(admin_client):
    from app.web import data_access as da
    da.save_banks([{"code": "SCB", "name": "ไทยพาณิชย์", "enabled": True, "rate_targets": []}])
    return "SCB"


@pytest.fixture
def fake_start_job(monkeypatch):
    from app.web import main
    calls = []

    def _fake(args, kind, only):
        calls.append({"args": args, "kind": kind, "only": only})
        return True

    monkeypatch.setattr(main, "_start_job", _fake)
    return calls


def test_api_run_rejects_unknown_only(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/run", json={"only": "NOSUCHBANK"})
    assert r.status_code == 400
    assert fake_start_job == []


def test_api_run_rejects_non_str_non_list_only(admin_client, seeded_bank, fake_start_job):
    # เดิม ",".join(123) จะโยน TypeError ออกมาเป็น 500 — ตอนนี้ต้องเป็น 400 ที่ตั้งใจแทน
    r = admin_client.post("/api/run", json={"only": 123})
    assert r.status_code == 400
    assert fake_start_job == []


def test_api_run_accepts_known_only(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/run", json={"only": "scb"})   # lower-case ก็ต้อง match ได้
    assert r.status_code == 200
    assert fake_start_job[0]["args"] == ["--only", "SCB"]
    assert fake_start_job[0]["only"] == ["SCB"]


def test_api_run_no_only_runs_everything(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/run", json={})
    assert r.status_code == 200
    assert fake_start_job[0]["args"] == []
    assert fake_start_job[0]["only"] is None


def test_api_backfill_rejects_unknown_only(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/backfill", json={"only": "NOPE", "year": 2025})
    assert r.status_code == 400
    assert fake_start_job == []


def test_api_backfill_accepts_known_only_with_year(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/backfill", json={"only": ["SCB"], "year": 2025})
    assert r.status_code == 200
    assert fake_start_job[0]["args"] == ["--backfill", "--only", "SCB", "--year", "2025"]


def test_api_discover_year_rejects_unknown_only(admin_client, seeded_bank, fake_start_job):
    r = admin_client.post("/api/discover-year", json={"only": "NOPE"})
    assert r.status_code == 400
    assert fake_start_job == []
