def test_security_headers_present_on_public_page(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "same-origin"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_security_headers_present_on_api_response(client):
    r = client.get("/api/config")   # 401 (ไม่ login) แต่ header ต้องยังติดอยู่
    assert r.status_code == 401
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers
