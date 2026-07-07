#!/bin/sh
# entrypoint.sh — เริ่ม supercronic (ตัวรัน crontab) เป็น background แล้วรัน uvicorn เป็น process หลัก
set -e

mkdir -p "${DATA_DIR:-/data}"

echo "[entrypoint] เริ่ม supercronic (crontab: /app/crontab)"
supercronic /app/crontab &

echo "[entrypoint] เริ่มเว็บที่ ${WEB_HOST:-0.0.0.0}:${WEB_PORT:-8080}"
exec uvicorn app.web.main:app --host "${WEB_HOST:-0.0.0.0}" --port "${WEB_PORT:-8080}"
