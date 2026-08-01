def test_newbank_request_rejects_javascript_uri(client):
    r = client.post("/api/request", json={
        "type": "newbank", "email": "user@example.com",
        "bank_name": "ธนาคารทดสอบ", "link": "javascript:alert(1)",
    })
    assert r.status_code == 400


def test_newbank_request_accepts_https_link(client):
    r = client.post("/api/request", json={
        "type": "newbank", "email": "user@example.com",
        "bank_name": "ธนาคารทดสอบ", "link": "https://example.com/a.pdf",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
