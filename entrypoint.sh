#!/bin/sh
# entrypoint.sh — เริ่ม supercronic (ตัวรัน crontab) เป็น background แล้วรัน uvicorn เป็น process หลัก
set -e

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

# container รันเป็น non-root แล้ว (ดู Dockerfile) — ถ้า HOST_DATA_DIR บน NAS เป็นของ uid อื่น
# mkdir -p ข้างบนจะผ่านเงียบ ๆ ถ้าโฟลเดอร์มีอยู่แล้ว (แค่ไม่มีสิทธิ์เขียน) แล้วแอปจะพังตอนเขียน
# CSV/config ครั้งแรกด้วย error ที่งงกว่านี้มาก — เช็คตรงนี้ก่อน บอกสาเหตุ+ทางแก้ชัด ๆ แทน
if [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] ❌ เขียน $DATA_DIR ไม่ได้ (คอนเทนเนอร์รันเป็น uid $(id -u) แต่โฟลเดอร์บน host เป็นของ uid อื่น)"
    echo "[entrypoint]    ตรวจสิทธิ์บน NAS: ls -n \"\$HOST_DATA_DIR\"  แล้วปรับให้ตรง เช่น: chown -R 1000:1000 \"\$HOST_DATA_DIR\""
    exit 1
fi

echo "[entrypoint] เริ่ม supercronic (crontab: /app/crontab)"
supercronic /app/crontab &

echo "[entrypoint] เริ่มเว็บที่ ${WEB_HOST:-0.0.0.0}:${WEB_PORT:-8080}"
exec uvicorn app.web.main:app --host "${WEB_HOST:-0.0.0.0}" --port "${WEB_PORT:-8080}"
