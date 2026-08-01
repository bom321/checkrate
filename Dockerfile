# CheckRate — Deposit Rate Monitor + Dashboard
# Base: python:3.13-slim, ทำงานบน Synology DS916+ (Intel x86_64)

FROM python:3.14-slim

# curl: จำเป็นสำหรับ download_pdf() ใน app/monitor/common.py
# tzdata: ตั้ง timezone Asia/Bangkok
# tesseract-ocr + tesseract-ocr-tha: PDF ประกาศของ BBL เป็นภาพสแกน (ไม่มี text layer)
#   banks/bbl.py จึงต้อง OCR ภาษาไทย — ถ้าไม่มี package นี้ BBL จะอ่านอัตราไม่ได้ (ธนาคารอื่นไม่กระทบ)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tzdata \
        tesseract-ocr \
        tesseract-ocr-tha \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Bangkok \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

# supercronic — cron ที่ทำงานใน foreground/container ได้ดีกว่า cron ปกติ
# (บันทึกไว้ตรงนี้ ถ้าจะอัปเดตเวอร์ชันในอนาคตให้แก้ URL + SHA1SUM ตาม release ใหม่)
ARG SUPERCRONIC_VERSION=v0.2.29
ARG SUPERCRONIC=supercronic-linux-amd64
ARG SUPERCRONIC_SHA1SUM=cd48d45c4b10f3f0bfdd3a57d054cd05ac96812b
RUN curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${SUPERCRONIC}" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "${SUPERCRONIC}" \
    && mv "${SUPERCRONIC}" /usr/local/bin/supercronic

WORKDIR /app

# requirements.txt คอมไพล์มาจาก requirements.in ด้วย pip-tools (pin เวอร์ชันเป๊ะ + hash ของทุกไฟล์
# ที่ยอมให้ติดตั้ง) — --require-hashes บังคับให้ pip ปฏิเสธ wheel/sdist ที่ hash ไม่ตรง กัน dependency
# ถูกแทนที่ (supply chain) เงียบ ๆ แก้ dependency ต้องแก้ requirements.in แล้วรัน
# `pip-compile requirements.in --generate-hashes --no-strip-extras --output-file=requirements.txt` ใหม่
# ห้ามแก้ requirements.txt ตรง ๆ (เป็นไฟล์ที่ pip-compile generate ให้)
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY app/ ./app/
COPY crontab ./crontab
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# รันเป็น non-root — เดิมไม่มี USER เลย บั๊กเขียนไฟล์ผิดพลาดใด ๆ จะเขียนทะลุถึง volume จริงบน NAS
# ด้วยสิทธิ์ root uid 1000 = uid ของผู้ใช้แรกที่สร้างบน Synology DSM ตามปกติ — **ต้องตรวจ uid จริงของ
# HOST_DATA_DIR ก่อน deploy จริงเสมอ** ด้วย `ls -n "$HOST_DATA_DIR"` ถ้าไม่ตรง container จะเขียน /data
# ไม่ได้และแอปพังตอนบูต (entrypoint.sh เช็คสิทธิ์เขียน + แจ้งเตือนสาเหตุไว้ให้แล้ว ไม่ crash เงียบ ๆ)
RUN useradd -u 1000 -m app && chown -R app:app /app
USER app

EXPOSE 8080
VOLUME ["/data"]

ENTRYPOINT ["/app/entrypoint.sh"]
