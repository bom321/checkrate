#!/bin/sh
# entrypoint.sh — เริ่ม supercronic (ตัวรัน crontab) เป็น background แล้วรัน uvicorn เป็น process หลัก
set -e

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

# container รันเป็น non-root แล้ว (ดู Dockerfile) — ถ้า HOST_DATA_DIR บน NAS เป็นของ uid อื่น
# mkdir -p ข้างบนจะผ่านเงียบ ๆ ถ้าโฟลเดอร์มีอยู่แล้ว (แค่ไม่มีสิทธิ์เขียน) แล้วแอปจะพังตอนเขียน
# CSV/config ครั้งแรกด้วย error ที่งงกว่านี้มาก — เช็คตรงนี้ก่อน บอกสาเหตุ+ทางแก้ชัด ๆ แทน
#
# **ห้ามกลับไปแนะนำ `chown -R 1000:1000` เป็นทางแก้แรก** — บนโฟลเดอร์แชร์ Synology ที่เปิด ACL
# (`ls` ขึ้น `+` ท้าย mode) ตัวที่บังคับใช้จริงคือ ACL ไม่ใช่ POSIX bits ที่ `ls` โชว์ เคสจริง ส.ค. 2569
# โฟลเดอร์เป็น `drwxrwxrwx+ 1000 1000` ครบทุกอย่างแล้วแต่ uid 1000 ยังเขียนไม่ได้ เพราะ ACL มีแต่ entry
# ของผู้ใช้ DSM (uid เริ่มที่ 1024) — chown ไป 2 รอบก็ไม่ช่วย ทางที่ได้ผลคือกลับกัน: รันคอนเทนเนอร์
# ด้วย uid/gid ของผู้ใช้ DSM ผ่าน PUID/PGID
if [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] ❌ เขียน $DATA_DIR ไม่ได้ — คอนเทนเนอร์รันเป็น uid=$(id -u) gid=$(id -g)"
    echo "[entrypoint]    เจ้าของ $DATA_DIR ที่เห็นจากในคอนเทนเนอร์: $(stat -c '%u:%g mode=%a' "$DATA_DIR" 2>/dev/null)"
    echo "[entrypoint]    บน Synology ที่โฟลเดอร์เปิด ACL ไว้: chown ไม่ช่วย เพราะ ACL ให้สิทธิ์เป็นราย 'ผู้ใช้ DSM'"
    echo "[entrypoint]    ทางแก้: บน NAS รัน  id <ชื่อผู้ใช้ DSM>  แล้วตั้ง PUID/PGID ใน .env ให้ตรงกับที่ได้"
    echo "[entrypoint]    ตรวจ ACL จริง: sudo synoacltool -get \"\$HOST_DATA_DIR\""
    exit 1
fi

# (ไม่ต้องเช็ค SESSION_SECRET ที่นี่ — auth.py เตือนให้แล้วตอน import พร้อมรายละเอียดครบกว่า
#  ใส่ซ้ำตรงนี้ได้แค่ log ซ้ำสองบรรทัด)

echo "[entrypoint] เริ่ม supercronic (crontab: /app/crontab)"
supercronic /app/crontab &

echo "[entrypoint] เริ่มเว็บที่ ${WEB_HOST:-0.0.0.0}:${WEB_PORT:-8080}"
exec uvicorn app.web.main:app --host "${WEB_HOST:-0.0.0.0}" --port "${WEB_PORT:-8080}"
