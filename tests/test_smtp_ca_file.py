import datetime
import ssl

from app.monitor import common


def test_active_smtp_config_reads_ca_file(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "mailplus")
    monkeypatch.setenv("SMTP2_CA_FILE", "/tmp/does-not-need-to-exist-for-this-check.pem")
    monkeypatch.setattr(common, "load_settings", lambda: {})
    cfg = common._active_smtp_config()
    assert cfg["ca_file"] == "/tmp/does-not-need-to-exist-for-this-check.pem"


def test_active_smtp_config_ca_file_defaults_to_none(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "mailplus")
    monkeypatch.delenv("SMTP2_CA_FILE", raising=False)
    monkeypatch.setattr(common, "load_settings", lambda: {})
    cfg = common._active_smtp_config()
    assert cfg["ca_file"] is None


def _write_self_signed_cert(path):
    """สร้าง self-signed cert จริง (ด้วย cryptography ที่ curl_cffi พึ่งอยู่แล้ว) เพื่อให้
    ssl.create_default_context(cafile=...) parse ผ่านจริง ๆ ไม่ใช่แค่ string ปลอม"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca.local")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def test_send_email_uses_ca_file_context_when_set(monkeypatch, tmp_path):
    fake_ca = tmp_path / "ca.pem"
    _write_self_signed_cert(fake_ca)

    monkeypatch.setattr(common, "_active_smtp_config", lambda: {
        "provider": "mailplus", "label": "mailplus", "host": "mail.example.com", "port": 465,
        "user": "u", "password": "p", "sender": "u", "insecure": True, "ca_file": str(fake_ca),
    })
    monkeypatch.setattr(common, "get_recipients", lambda: ["x@example.com"])

    captured = {}

    class _FakeSMTPSSL:
        def __init__(self, host, port, timeout, context):
            captured["context"] = context

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a, **k):
            pass

        def send_message(self, *a, **k):
            pass

    monkeypatch.setattr(common.smtplib, "SMTP_SSL", _FakeSMTPSSL)

    assert common.send_email("subject", "<p>x</p>") is True
    ctx = captured["context"]
    # ต้อง verify จริง (ไม่ใช่ CERT_NONE แบบ SMTP2_INSECURE) แม้ insecure=True ก็ตาม เพราะ
    # ca_file มาก่อนตามลำดับความสำคัญ CA_FILE > INSECURE > default
    assert ctx.verify_mode != ssl.CERT_NONE
    assert ctx.check_hostname is True
