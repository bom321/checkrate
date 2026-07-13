#!/usr/bin/env python3
"""
fetch_logos.py — ดึงโลโก้ธนาคารจาก logo.dev มาเก็บเป็นไฟล์ใน static/img/logos/

เป็น dev tool รันมือครั้งเดียว (ไม่ใช่ส่วนหนึ่งของ monitor/เว็บ) — เว็บอ่านแต่ไฟล์ PNG ที่ได้
จึงยังทำงานได้ในที่ที่ไม่มีเน็ต เหมือน Chart.js/ฟอนต์ที่ self-host ไว้

    export LOGODEV_TOKEN=pk_xxxx          # publishable token จาก logo.dev
    python tools/fetch_logos.py           # ทุกธนาคาร
    python tools/fetch_logos.py SCB KTB   # เฉพาะบางธนาคาร

ธนาคารไหนไม่มีไฟล์โลโก้ เว็บจะ fallback ไปแสดงตัวอักษรย่อ (monogram) ให้เอง — หน้าไม่พัง
"""

import os
import sys
import urllib.error
import urllib.request

# โดเมนสำหรับให้ logo.dev หาโลโก้ (คีย์ = code ใน banks_config.json)
DOMAINS = {
    "SCB":   "scb.co.th",
    "KBANK": "kasikornbank.com",
    "KTB":   "krungthai.com",
    "BBL":   "bangkokbank.com",
    "BAY":   "krungsri.com",
}

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "web", "static", "img", "logos")


def fetch(code: str, token: str) -> bool:
    domain = DOMAINS[code]
    url = (f"https://img.logo.dev/{domain}"
           f"?token={token}&size=128&format=png&retina=true")
    dest = os.path.join(OUT_DIR, f"{code.lower()}.png")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        print(f"  {code:6s} ✗ HTTP {e.code} ({domain}) — ข้าม")
        return False
    except Exception as e:
        print(f"  {code:6s} ✗ {e} — ข้าม")
        return False

    if not data.startswith(b"\x89PNG"):
        print(f"  {code:6s} ✗ ไม่ใช่ไฟล์ PNG ({len(data)} ไบต์) — ข้าม")
        return False

    with open(dest, "wb") as f:
        f.write(data)
    print(f"  {code:6s} ✓ {domain} → {os.path.relpath(dest)} ({len(data)/1024:.1f} KB)")
    return True


def main() -> int:
    token = os.environ.get("LOGODEV_TOKEN", "").strip()
    if not token:
        print("ไม่พบ LOGODEV_TOKEN ใน env — ใส่ LOGODEV_TOKEN=pk_... ไว้ใน .env แล้วโหลดก่อนรัน")
        return 1

    codes = [c.upper() for c in sys.argv[1:]] or list(DOMAINS)
    unknown = [c for c in codes if c not in DOMAINS]
    if unknown:
        print(f"ไม่รู้จักธนาคาร: {', '.join(unknown)} — เพิ่มโดเมนใน DOMAINS ก่อน")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"ดึงโลโก้ {len(codes)} ธนาคารจาก logo.dev")
    ok = sum(fetch(c, token) for c in codes)
    print(f"สำเร็จ {ok}/{len(codes)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
