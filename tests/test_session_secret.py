import logging


def test_session_secret_warns_when_env_not_set(fastapi_app, monkeypatch, caplog):
    from app.web import auth
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with caplog.at_level(logging.WARNING, logger=auth.common.log.name):
        auth.session_secret()
    assert any("SESSION_SECRET" in r.message for r in caplog.records)


def test_session_secret_silent_when_env_set(fastapi_app, monkeypatch, caplog):
    from app.web import auth
    monkeypatch.setenv("SESSION_SECRET", "explicit-secret")
    with caplog.at_level(logging.WARNING, logger=auth.common.log.name):
        secret = auth.session_secret()
    assert secret == "explicit-secret"
    assert not any("SESSION_SECRET" in r.message for r in caplog.records)
