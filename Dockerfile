# CheckRate — Deposit Rate Monitor + Dashboard
# Base: python:3.13-slim, ทำงานบน Synology DS916+ (Intel x86_64)

FROM python:3.13-slim

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

# **ห้ามเปลี่ยนกลับไปเป็น `chmod +x` เฉย ๆ** — โฟลเดอร์แชร์บน Synology ที่ใช้ Synology ACL มักมี POSIX
# mode เป็น 000 (สิทธิ์จริงอยู่ใน ACL ซึ่ง build context ของ docker ไม่เอาไปด้วย) ไฟล์ที่ COPY เข้ามาจึง
# กลายเป็นอ่านไม่ได้ทั้งชุด สมัยที่คอนเทนเนอร์ยังรันเป็น root ไม่มีใครเห็นปัญหา (root อ่านไฟล์ mode 000 ได้)
# พอเปลี่ยนเป็น USER app + cap_drop ALL (ไม่มี DAC_OVERRIDE) คอนเทนเนอร์พังตอนบูตด้วย
# "/bin/sh: 0: cannot open /app/entrypoint.sh: Permission denied" — exec ผ่าน (มีบิต x จาก chmod +x)
# แต่ sh อ่านไฟล์ไม่ได้ ต้องตั้ง mode แบบสัมบูรณ์ให้อ่านได้ทั้ง tree ไม่ใช่แค่ entrypoint.sh
# (a+rX = ไฟล์อ่านได้ทุกคน, โฟลเดอร์เข้าได้ทุกคน, ไม่ไปแจก x ให้ไฟล์ธรรมดา)
RUN chmod -R a+rX /app && chmod 0755 /app/entrypoint.sh

# รันเป็น non-root — เดิมไม่มี USER เลย บั๊กเขียนไฟล์ผิดพลาดใด ๆ จะเขียนทะลุถึง volume จริงบน NAS
# ด้วยสิทธิ์ root uid 1000 = uid ของผู้ใช้แรกที่สร้างบน Synology DSM ตามปกติ — **ต้องตรวจ uid จริงของ
# HOST_DATA_DIR ก่อน deploy จริงเสมอ** ด้วย `ls -n "$HOST_DATA_DIR"` ถ้าไม่ตรง container จะเขียน /data
# ไม่ได้และแอปพังตอนบูต (entrypoint.sh เช็คสิทธิ์เขียน + แจ้งเตือนสาเหตุไว้ให้แล้ว ไม่ crash เงียบ ๆ)
RUN useradd -u 1000 -m app && chown -R app:app /app
USER app

EXPOSE 8080
VOLUME ["/data"]

ENTRYPOINT ["/app/entrypoint.sh"]
