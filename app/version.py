#!/usr/bin/env python3
"""
version.py — เวอร์ชันของแอป + "วันที่แก้ไขล่าสุด" ของโค้ดชุดที่กำลังรันอยู่จริง

ใช้ตอบคำถามเดียว: **เครื่องนี้รันโค้ดชุดไหนอยู่** (หลัง deploy บน NAS แล้วสงสัยว่า git pull ติดจริงไหม)
โผล่ 3 ที่: footer ของทุกหน้าเว็บ · `GET /api/version` กับ `/api/health` (ยิงจากสคริปต์/ภายนอกได้) ·
บรรทัด log ตอนเว็บบูต

`VERSION` เป็นเลขที่ **ตั้งด้วยมือ** — bump ตอนออกเวอร์ชันใหม่ (semantic: major.minor.patch)
ส่วน commit/วันที่ หามาให้เองตามลำดับนี้ (ตัวแรกที่ได้ผลชนะ):

1. env `APP_COMMIT` / `APP_BUILD_DATE` — ค่าที่ bake เข้า image ตอน `docker build` (Dockerfile ARG→ENV,
   `scripts/update.sh` ส่งค่าจาก git ของ repo บน NAS ให้) **ทางนี้คือทางหลักของเครื่องจริง** เพราะ
   `.git/` ไม่ได้ถูก COPY เข้า image (อยู่ใน .dockerignore) ในคอนเทนเนอร์จึงไม่มี git ให้ถามอยู่แล้ว
2. `git log -1` ของ repo — ใช้ตอนรันจากซอร์สบนเครื่องพัฒนา (มี `.git/` และมีคำสั่ง git)
3. mtime ล่าสุดของไฟล์ใน `app/` — ทางสุดท้ายเมื่อไม่มีทั้งสองอย่าง (เช่น unzip ไฟล์มาวางเฉย ๆ)
   ไม่มี commit ให้อ้าง แต่ยัง**บอกวันที่แก้ไขล่าสุดได้ถูกต้อง** ซึ่งเป็นสิ่งที่ผู้ใช้ถามหาจริง ๆ

ผลลัพธ์ cache ไว้ทั้ง process (เรียกทุก request แต่ไม่ยิง git ซ้ำ) — ค่าพวกนี้เปลี่ยนได้ก็ต่อเมื่อ
โค้ดเปลี่ยน ซึ่งต้องรีสตาร์ทเว็บอยู่แล้ว
"""

import os
import subprocess
from datetime import datetime

# ── เลขเวอร์ชันของแอป — แก้ที่นี่ที่เดียวตอนออกเวอร์ชันใหม่ ──
# 1.0.0 = เวอร์ชันแรกที่เริ่มติดป้ายเวอร์ชัน (ส.ค. 2569) ระบบใช้งานจริงมาก่อนหน้านั้นแล้ว
# 1.0.1 = ปรับหน้าตา footer (ข้อความ "ปรับปรุงล่าสุด" + ป้ายเวอร์ชันเป็นสีเทา ฟอนต์ sans)
VERSION = "1.0.1"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)          # .../CheckRate

_cache: dict | None = None


def _git(*args: str) -> str | None:
    """รัน git ใน PROJECT_ROOT — คืน None ถ้าไม่มี git / ไม่ใช่ repo / ช้าเกิน 5 วิ

    `safe.directory` ตั้งไว้เหมือนใน scripts/update.sh: บน NAS ไฟล์ repo เป็นของผู้ใช้คนหนึ่ง
    แต่ process อาจรันด้วย uid อื่น (PUID/PGID) git จะปฏิเสธด้วย "dubious ownership"
    """
    try:
        p = subprocess.run(
            ["git", "-c", f"safe.directory={PROJECT_ROOT}", "-C", PROJECT_ROOT, *args],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (p.stdout or "").strip()
    return out if p.returncode == 0 and out else None


def _from_env() -> dict | None:
    """ค่าที่ bake เข้า image ตอน build — ต้องมี commit อย่างน้อย ไม่งั้นถือว่าไม่ได้ตั้ง"""
    commit = (os.environ.get("APP_COMMIT") or "").strip()
    if not commit:
        return None
    return {
        "commit": commit[:12],
        "date": (os.environ.get("APP_BUILD_DATE") or "").strip() or None,
        "dirty": False,
        "source": "build",
    }


def _from_git() -> dict | None:
    commit = _git("rev-parse", "--short=8", "HEAD")
    if not commit:
        return None
    return {
        "commit": commit,
        "date": _git("log", "-1", "--format=%cI"),
        # ไฟล์ที่แก้ค้างไว้ยังไม่ commit — เห็นบน footer ตอน dev ว่าที่รันอยู่ไม่ตรงกับ commit ไหนเป๊ะ ๆ
        "dirty": bool(_git("status", "--porcelain")),
        "source": "git",
    }


def _from_mtime() -> dict:
    """วันที่แก้ไขล่าสุดของซอร์สใน app/ — ทางสุดท้ายเมื่อไม่มีทั้ง env และ git"""
    newest = 0.0
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, f)))
            except OSError:
                continue
    date = datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else None
    return {"commit": "", "date": date, "dirty": False, "source": "mtime"}


def build_info(refresh: bool = False) -> dict:
    """{version, commit, date, dirty, source, label} — cache ทั้ง process (refresh=True เพื่อทดสอบ)

    `date` เป็น ISO string (หรือ None) ให้ template ส่งต่อเข้า filter `thai_datetime` ได้ตรง ๆ
    `label` = สตริงพร้อมแสดง/พร้อม log เช่น `v1.0.0 (a437a07)` — ที่เดียวที่ประกอบรูปแบบนี้
    """
    global _cache
    if _cache is None or refresh:
        info = _from_env() or _from_git() or _from_mtime()
        label = f"v{VERSION}"
        if info["commit"]:
            label += f" ({info['commit']})"
        if info["dirty"]:
            label += " +แก้ค้าง"
        _cache = {"version": VERSION, "label": label, **info}
    return _cache


if __name__ == "__main__":   # python -m app.version — ใช้ตรวจเร็ว ๆ ว่าเครื่องนี้รันโค้ดชุดไหน
    for k, v in build_info().items():
        print(f"{k:8} {v}")
