# คู่มือ Deploy CheckRate บน Synology DS916+

ระบบนี้ประกอบด้วย 2 ส่วนที่รันในคอนเทนเนอร์เดียวกัน:
- **Monitor** (`app/monitor/rate_monitor.py`) — ดาวน์โหลด PDF ประกาศดอกเบี้ย → extract → อัปเดต CSV → ส่งอีเมล (SMTP)
- **เว็บ Dashboard** (`app/web`, FastAPI) — ดูภาพรวม/รายละเอียด/จัดการ config/log ผ่านเบราว์เซอร์

---

## ขั้นตอนที่ 1 — สร้าง Gmail App Password (ถ้าใช้ Gmail ส่งอีเมล)

1. เปิดใช้งาน **2-Step Verification** ในบัญชี Google ก่อน (จำเป็น ถ้ายังไม่เปิดจะสร้าง App Password ไม่ได้)
2. ไปที่ https://myaccount.google.com/apppasswords แล้วสร้างรหัสผ่านแอปใหม่ (ตั้งชื่อเช่น "CheckRate")
3. คัดลอกรหัส 16 หลักที่ได้ (รูปแบบ `xxxx xxxx xxxx xxxx`) — จะใช้เป็นค่า `SMTP_PASSWORD`

> ถ้าใช้ผู้ให้บริการอีเมลอื่น (เช่น Outlook/Office365) ให้ปรับ `SMTP_HOST`/`SMTP_PORT` ตามผู้ให้บริการนั้น — ไม่จำเป็นต้องเป็น Gmail

### ทางเลือก — ใช้ Synology MailPlus เป็นช่องทางสำรอง

ถ้ามี MailPlus Server รันอยู่บน NAS ตัวเดียวกัน (หรือเครื่องอื่นในเครือข่าย) ตั้งเป็นชุด SMTP สำรองได้
โดยไม่ต้องเลิกใช้ Gmail — ใส่ค่าใน `.env` ชุด `SMTP2_*` (host/port/user/password ของกล่อง MailPlus เอง
ไม่ใช่ของปลายทางที่ MailPlus รีเลย์ไปอีกที เช่น Brevo) แล้วสลับไปใช้จากหน้า `/email` → "ช่องทางส่งอีเมล (SMTP)"
เลือก "MailPlus (Synology)" — สลับกลับมา Gmail ได้ทุกเมื่อโดยไม่ต้องแก้ env

**ใบรับรอง TLS**: ถ้ากล่อง MailPlus ใช้ใบรับรอง self-signed หรือ hostname ไม่ตรงกับที่ต่อ (เช่น ต่อผ่าน LAN IP)
จะเจอ `SSLCertVerificationError` ตอนกดปุ่มทดสอบ — แก้โดยตั้ง `SMTP2_INSECURE=1` ใน `.env` (ลอง `0` ก่อนเสมอ
ถ้าใบรับรองถูกต้องอยู่แล้วไม่ต้องตั้ง)

---

## ขั้นตอนที่ 2 — เตรียมข้อมูลบน NAS

1. สร้างโฟลเดอร์เก็บข้อมูล — ที่ใช้จริงตอนนี้คือ `data/` **ในโฟลเดอร์โปรเจกต์เอง**:
   `/volume1/bom321/Work/deposit-rate/docker/checkrate/data/`
   (ตำแหน่งปรับได้ — จะตั้งค่าจริงใน `.env` ด้วย `HOST_DATA_DIR` ในขั้นตอนถัดไป · วางไว้ในโปรเจกต์ได้
   อย่างปลอดภัยเพราะ `data/` ติดทั้ง `.gitignore` (git pull ไม่แตะ) และ `.dockerignore` (ไม่เข้า build context))
2. คัดลอกไฟล์ข้อมูลเดิมจาก Mac (โฟลเดอร์ `data/` ในโปรเจกต์นี้ ซึ่ง seed มาจาก
   `/Users/bom321/Desktop/Learn Claude/Deposit Rate/SCB/` แล้ว) เข้าไปในโฟลเดอร์นั้น:
   - `banks_config.json`
   - `settings.json`
   - `scb_deposit_rate.csv` (และ CSV อื่น ๆ ถ้ามี)
   - โฟลเดอร์ `pdfs/SCB/` (และของธนาคารอื่นถ้ามี)
   - (ไม่บังคับ) log เดิม → เปลี่ยนชื่อเป็น `rate_monitor.log`
3. โครงสร้างที่ควรได้บน NAS:
   ```
   /volume1/bom321/Work/deposit-rate/docker/checkrate/data/
   ├── banks_config.json
   ├── settings.json
   ├── scb_deposit_rate.csv
   └── pdfs/SCB/*.pdf
   ```
4. **คอนเทนเนอร์รันเป็น non-root** — ต้องให้ uid ที่คอนเทนเนอร์ใช้เขียนโฟลเดอร์นี้ได้จริง ไม่งั้น
   คอนเทนเนอร์จะพังตอนบูต (ดู `entrypoint.sh` — แจ้ง error ชัดเจนถ้าเขียนไม่ได้ ไม่ crash เงียบ ๆ)
   ดูเจ้าของโฟลเดอร์ก่อนเสมอ:
   ```
   cd /volume1/bom321/Work/deposit-rate/docker/checkrate
   ls -nd data      # ดูคอลัมน์ uid/gid (ตัวเลข ไม่ใช่ชื่อ) และดูว่ามี + ท้าย mode ไหม
   ```

   **ถ้ามี `+` ท้าย mode (เช่น `drwxrwxrwx+`) → โฟลเดอร์เปิด Synology ACL — ข้ามไปทำข้อ (ก) เลย**
   ACL บังคับใช้ทับ POSIX bits (bits ที่ `ls` โชว์เป็นแค่ค่าประมาณ) และให้สิทธิ์เป็นราย "ผู้ใช้ DSM"
   ซึ่ง uid เริ่มที่ 1024 — uid 1000 ไม่ใช่ผู้ใช้ที่ DSM รู้จัก **`chown` จึงไม่ช่วยเลย**
   (เจอจริง ส.ค. 2569: โฟลเดอร์เป็น `drwxrwxrwx+ 1000 1000` ครบทุกอย่างแล้ว แต่ uid 1000 ยังเขียนไม่ได้
   `chown` ไป 2 รอบก็เหมือนเดิม — เว็บดับข้ามคืนเพราะไล่ผิดทางอยู่ที่ POSIX bits)

   **(ก) โฟลเดอร์เปิด ACL — ตั้ง `PUID`/`PGID`** ให้คอนเทนเนอร์รันด้วย uid/gid ของผู้ใช้ DSM
   ที่ ACL รู้จักแทน (ดู `user:` ใน `docker-compose.yml`):
   ```
   id bom321                       # เช่นได้ uid=1027(bom321) gid=100(users)
   sudo synoacltool -get data      # ดู ACL จริงว่ามี entry ของใครบ้าง
   ```
   แล้วใส่ค่าที่ได้ลงใน `.env`:
   ```
   PUID=1027
   PGID=100
   ```

   **(ข) โฟลเดอร์ไม่มี ACL (POSIX ล้วน)** — `chown` ให้ตรงกับ uid ที่จะใช้รันได้ตามปกติ:
   ```
   sudo chown -R 1000:1000 data
   ```

   ตรวจว่าได้ผลจริงก่อน start (ไม่ต้อง rebuild — ไฟล์ใน image เปิด `a+rX` ไว้แล้ว):
   ```
   docker run --rm --user "$(id -u):$(id -g)" -v "$HOST_DATA_DIR:/data" \
       --entrypoint /bin/sh checkrate-checkrate -c 'touch /data/.wtest && echo WRITE_OK'
   ```
   (`scripts/update.sh` รันการทดสอบนี้ให้เองทุกครั้งก่อน deploy — ดูหัวข้อ "อัปเดตเวอร์ชันใหม่")

   อาการเมื่อลืมทำ: คอนเทนเนอร์ restart วนแล้ว `docker logs checkrate` ขึ้น
   `[entrypoint] ❌ เขียน /data ไม่ได้ ...`

---

## ขั้นตอนที่ 3 — Copy โปรเจกต์ขึ้น NAS และตั้งค่า `.env`

1. คัดลอกโฟลเดอร์โปรเจกต์นี้ทั้งหมด (`CheckRate/`) ขึ้น NAS ไปที่ `/volume1/bom321/Work/deposit-rate/docker/checkrate/`
   (ผ่าน File Station, `scp`, หรือ Git — **ไม่ต้อง** copy โฟลเดอร์ `data/` ที่ใช้ dev บน Mac ขึ้นไปด้วยก็ได้
   เพราะข้อมูลจริงจะอยู่ที่ `HOST_DATA_DIR` ตามขั้นตอนที่ 2)
2. สร้างไฟล์ `.env` จาก `.env.example`:
   ```
   cp .env.example .env
   ```
3. แก้ `.env` ใส่ค่าจริง:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=465
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx      # App Password จากขั้นตอนที่ 1
   EMAIL_FROM=your_email@gmail.com
   EMAIL_TO=bom321@hotmail.com            # ผู้รับเริ่มต้น (แก้ภายหลังผ่านหน้าเว็บได้)
   # ต้องตรงกับโฟลเดอร์ที่สร้างในขั้นตอนที่ 2 (path เต็มของโฟลเดอร์ข้อมูล ไม่ใช่โฟลเดอร์โปรเจกต์)
   HOST_DATA_DIR=/volume1/bom321/Work/deposit-rate/docker/checkrate/data
   WEB_PORT=8080
   ADMIN_EMAILS=bom321@hotmail.com        # อีเมลที่มีสิทธิ์เข้า /config, /email, /logs และกดปุ่มรันตรวจสอบ
   ```
   **ห้าม commit ไฟล์ `.env` เข้า git** (มี `.gitignore` กันไว้ให้แล้ว)

---

## ขั้นตอนที่ 4 — Build & Run

### วิธี A: ผ่าน Container Manager (GUI)
1. เปิด **Container Manager** → แท็บ **Project** → **Create**
2. เลือกโฟลเดอร์โปรเจกต์ (`/volume1/bom321/Work/deposit-rate/docker/checkrate/`) ที่มี `docker-compose.yml` อยู่
3. กด **Build** แล้ว **Run** — DSM จะอ่าน `docker-compose.yml` และ `.env` ในโฟลเดอร์เดียวกันให้อัตโนมัติ

### วิธี B: ผ่าน SSH
```bash
cd /volume1/bom321/Work/deposit-rate/docker/checkrate
docker-compose up -d --build
```

ตรวจสอบว่าคอนเทนเนอร์รันอยู่:
```bash
docker ps        # ต้องขึ้น (healthy) ภายใน ~90 วิ — ไม่ใช่แค่ Up
docker logs -f checkrate
```

> **`Up` เฉย ๆ ยังไม่พอ** — คอนเทนเนอร์ที่ restart วนอยู่ก็ขึ้น `Up` ได้เหมือนกัน (เจอจริง ส.ค. 2569:
> restart ไป 26 รอบโดย `docker ps` ดูปกติทุกอย่าง) เช็คให้ชัดด้วย:
> ```bash
> docker inspect checkrate --format '{{.State.Health.Status}} restarts={{.RestartCount}} user={{.Config.User}}'
> # ที่ถูกต้อง: healthy restarts=0 user=<PUID>:<PGID>
> ```

---

## ขั้นตอนที่ 5 — เข้าเว็บ

เปิดเบราว์เซอร์ไปที่ `http://<NAS-IP>:8080` (พอร์ตฝั่ง host ปรับได้ผ่าน `HOST_WEB_PORT` ใน `.env` —
`WEB_PORT` คือพอร์ตข้างในคอนเทนเนอร์ ปกติไม่ต้องแตะ)

- **ภาพรวม** / **รายละเอียดธนาคาร** — เปิดดูได้ทุกคนโดยไม่ต้อง login
- **จัดการอัตรา**, **Log & รัน** และปุ่มรันตรวจสอบ — ต้อง login ก่อน (ปุ่ม "เข้าสู่ระบบ" มุมขวาบน)
  กรอกอีเมลที่อยู่ใน `ADMIN_EMAILS` → รับรหัส OTP 6 หลักทางอีเมล (หมดอายุ 5 นาที) → กรอกรหัสเพื่อเข้าสู่ระบบ
  session ค้างไว้ 7 วัน (ปรับได้ด้วย `SESSION_MAX_AGE_DAYS` ใน `.env`), ออกจากระบบได้ที่ปุ่ม "ออกจากระบบ"

---

## ขั้นตอนที่ 6 — ตั้งเวลารันอัตโนมัติ

มี 2 ทางเลือก:

### (ก) supercronic ในคอนเทนเนอร์ — ค่าเริ่มต้นของระบบนี้
คอนเทนเนอร์รัน `supercronic` อ่านตาราง `crontab` ในโปรเจกต์อัตโนมัติเมื่อ start (ดูไฟล์ `crontab`)
ค่าเริ่มต้น: รันทุกวันเวลา 09:00 (Asia/Bangkok)

**ข้อดี:** self-contained, ไม่ต้องพึ่ง DSM, ทำงานได้แม้ย้ายไปรันเครื่องอื่น
**ข้อเสีย:** แก้เวลาต้องแก้ไฟล์ `crontab` แล้ว rebuild/restart คอนเทนเนอร์:
```bash
# แก้ไฟล์ crontab แล้ว
docker-compose up -d --build
```

### (ข) DSM Task Scheduler เรียก `docker exec`
ปิด/ลบบรรทัดใน `crontab` ไม่ให้ supercronic รันซ้ำ แล้วตั้งใน DSM แทน:

1. **Control Panel** → **Task Scheduler** → **Create** → **Scheduled Task** → **User-defined script**
2. ตั้งเวลาตามต้องการ (เช่น ทุกวัน 09:00)
3. ใส่ script:
   ```bash
   docker exec checkrate python -m app.monitor.rate_monitor
   ```

**ข้อดี:** จัดการเวลาผ่าน UI ของ DSM ได้ง่าย ไม่ต้อง rebuild image
**ข้อเสีย:** ผูกกับ DSM Task Scheduler โดยเฉพาะ, ต้องจำไว้ปิด cron ในคอนเทนเนอร์ไม่ให้ทำงานซ้อนกัน

---

## อัปเดตเวอร์ชันใหม่ — `scripts/update.sh`

เมื่อโค้ดบน GitHub มี commit ใหม่ ใช้สคริปต์นี้อัปเดตให้จบในคำสั่งเดียว — **ใช้ได้เฉพาะกรณีที่โค้ดบน NAS
เป็น git clone** ไม่ใช่ไฟล์ที่ copy ผ่าน File Station:

ลำดับที่สคริปต์ทำ (ตั้งใจให้ "ของที่รันอยู่" รอดไว้ให้นานที่สุด):

| ขั้น | ทำอะไร | ถ้าพังตรงนี้ |
|---|---|---|
| 1 | `git pull --ff-only` | หยุด — ไม่แตะคอนเทนเนอร์ |
| 2 | tag image เดิมเป็น `checkrate:previous` | — (ทางถอย) |
| 3 | `build` **อย่างเดียว** ยังไม่ recreate | หยุด — ของเดิมยังรันอยู่ |
| 4 | **preflight**: ทดสอบเขียน `HOST_DATA_DIR` ด้วย `PUID:PGID` จริง | หยุด + บอกวิธีดู ACL — ของเดิมยังรันอยู่ |
| 5 | `up -d` แล้วรอเว็บตอบที่ `/api/health` (สูงสุด 90 วิ) | dump `docker logs` + บอกคำสั่ง rollback |

ขั้นที่ 4 คือด่านที่เพิ่มมาหลังเหตุการณ์ ส.ค. 2569 — deploy แล้วคอนเทนเนอร์เขียน `/data` ไม่ได้เพราะ
Synology ACL กลายเป็น restart loop และเว็บดับยาว ตอนนี้เคสเดียวกันจะถูกจับตั้งแต่ก่อนแตะของที่รันอยู่

```bash
# ครั้งแรก (ถ้ายังไม่ได้ clone) — ติดตั้ง Git Server จาก Package Center ก่อนให้มีคำสั่ง git
cd /volume1/bom321/Work/deposit-rate/docker
git clone https://github.com/bom321/checkrate.git checkrate
cd checkrate && cp .env.example .env    # แล้วแก้ .env ตามขั้นตอนที่ 3
```

### ตั้งใน DSM Task Scheduler
**Control Panel** → **Task Scheduler** → **Create** → **Scheduled Task** → **User-defined script**
(User: `root`) แล้วใส่:
```bash
sh /volume1/bom321/Work/deposit-rate/docker/checkrate/scripts/update.sh
```
ตั้งเวลาตามต้องการ หรือปล่อยเป็น task ที่กด **Run** เอาเองเมื่อจะอัปเดต

สคริปต์ปลอดภัยเมื่อรันซ้ำ: ถ้าไม่มี commit ใหม่จะ**ข้ามการ build** (แต่ยังเช็คให้ว่าคอนเทนเนอร์ยังรันอยู่
ถ้าดับจะ start ให้) ผลลัพธ์ออกทั้ง stdout (Task Scheduler ส่งอีเมลให้ได้ถ้าเปิด "Send run details by email")
และไฟล์ `update.log` ในโฟลเดอร์โปรเจกต์

**พฤติกรรมที่ควรรู้:**
- ข้อมูลจริง (CSV/PDF/config ใน `HOST_DATA_DIR`) อยู่ในโฟลเดอร์ `data/` ของโปรเจกต์ แต่ `git pull`
  ไม่แตะเพราะ `data/` อยู่ใน `.gitignore` (และไม่มีไฟล์ไหนใน `data/` ถูก track ไว้เลย)
- ถ้ามีไฟล์ที่ถูกแก้ค้างไว้บน NAS (`git status` ไม่สะอาด) หรือโค้ดแตกสายจาก `origin/main` สคริปต์จะ
  **หยุดพร้อมบอกเหตุผล ไม่ทับของเดิม** ต้องเข้าไปเก็บกวาดเองก่อน — รวมถึงไฟล์อย่าง
  `docker-compose.override.yml` ที่เคยสร้างไว้แก้ปัญหาเฉพาะหน้า ต้องลบทิ้งเมื่อทางแก้เข้า git แล้ว
- ถ้าเว็บไม่ตอบใน 90 วิ จะ dump `docker logs` 30 บรรทัดล่าสุด + พิมพ์คำสั่ง rollback ให้ แล้ว exit code 1
  (สคริปต์เลิกรอทันทีถ้าเห็นว่า `RestartCount` เกิน 2 = บูตแล้วตายซ้ำ ๆ ไม่ใช่แค่บูตช้า)
- image ของเวอร์ชันก่อนหน้าถูก tag ไว้เป็น `checkrate:previous` และ **ไม่ถูก `docker image prune` ลบทิ้ง**
- เปลี่ยน branch ได้ด้วย env: `BRANCH=dev sh scripts/update.sh`
- `scripts/` อยู่ใน git แล้ว (ตั้งแต่ ส.ค. 2569) — แก้บน Mac แล้ว `git pull` บน NAS ได้ของใหม่เลย
  ไม่ต้อง copy มือเหมือนเดิม

---

## ขั้นตอนที่ 7 — ทดสอบ

1. เข้าเว็บ → หน้า **ตั้งค่าอีเมล** → กด **"✉️ ทดสอบส่งอีเมล"** เพื่อยืนยันว่าตั้งค่า SMTP ถูกต้อง
2. กด **"▶ รันตรวจสอบทันที (ทุกธนาคาร)"** เพื่อทดสอบ pipeline แบบเต็ม
3. ดูผลใน Log console และหน้าภาพรวม (ควรเห็นวันที่/อัตราล่าสุดอัปเดต)

---

## แก้ปัญหาที่เคยเจอจริง

### เว็บเข้าไม่ได้ — แยกอาการก่อน

| อาการจาก `curl` | แปลว่า | ไปดูที่ |
|---|---|---|
| `Connection refused` | ไม่มีใคร publish พอร์ตนี้เลย | `docker ps` คอนเทนเนอร์ตายสนิท / `HOST_WEB_PORT` ผิด |
| `Connection reset by peer` | docker-proxy รับสายแล้ว **แต่ข้างในคอนเทนเนอร์ไม่มีใครฟัง** | `docker logs checkrate` — คอนเทนเนอร์ตายหรือ `WEB_PORT` ไม่ตรงกับฝั่งขวาของ `ports:` |
| `405` จาก `curl -I` | **ปกติ ไม่ใช่ปัญหา** | `-I` ส่ง HEAD แต่ route รับแค่ GET — ดูหัว `server: uvicorn` ก็พอ (= แอปตอบเอง ไม่ใช่ docker-proxy) |

### คอนเทนเนอร์ restart วน

```bash
docker logs checkrate | tail -30
docker inspect checkrate --format '{{.State.Health.Status}} restarts={{.RestartCount}}'
```
- `[entrypoint] ❌ เขียน /data ไม่ได้` → เรื่องสิทธิ์ ดูขั้นตอนที่ 2 ข้อ 4 (ACL → ตั้ง `PUID`/`PGID`)
- **การ "กลับไปรันเป็น root" ไม่ช่วย** — `cap_drop: ALL` ตัด `DAC_OVERRIDE` ทิ้ง uid 0 ที่ไม่มี
  capability นี้ก็เขียนโฟลเดอร์ของ uid อื่นไม่ได้เหมือนกัน (และ `entrypoint.sh` ใช้แค่ `mkdir -p`/`test -w`
  ไม่มีคำสั่งไหนต้องใช้ capability เลย) แก้ที่ `PUID`/`PGID` หรือสิทธิ์ฝั่ง host เท่านั้น
- **อย่าลืมอ่าน log ให้จบ** — error อาจเปลี่ยนไปแล้วระหว่างที่ไล่แก้ (เจอจริง: ยังไล่ตาม
  "เปิดไฟล์ไม่ได้" อยู่ทั้งที่ error กลายเป็น "เขียน /data ไม่ได้" ไปแล้ว เสียเวลาไปหนึ่งรอบเต็ม)

### `git pull` บน NAS พังด้วย `packfile ... index unavailable`

`.idx` ของ packfile หาย อ่าน commit เก่าไม่ได้ — ซ่อมก่อนแล้วค่อย pull:
```bash
cd /volume1/bom321/Work/deposit-rate/docker/checkrate
git config --global --add safe.directory "$PWD"    # ตั้งครั้งเดียว ไม่ต้อง -c ทุกคำสั่ง
ls -la .git/objects/pack/
git index-pack .git/objects/pack/pack-<hash>.pack
git fsck
```
ถ้าซ่อมไม่ขึ้น: `git clone` ใหม่ลงโฟลเดอร์ข้าง ๆ แล้วย้าย `.env` + `data/` ไปใส่ (ทั้งสองอย่างไม่ได้อยู่ใน git)

---

## หมายเหตุสำคัญ

- **ไม่มีการ hardcode path หรือรหัสผ่าน** — ทุกอย่างอ่านจาก environment variable (`.env`) และ `DATA_DIR`
- Path บน Mac เดิม (`/Users/bom321/...`) **ไม่ถูกใช้ในระบบนี้เลย** — เปลี่ยนเป็น `DATA_DIR=/data` (ใน container)
  ที่ map มาจาก `HOST_DATA_DIR` บน NAS ตามที่ตั้งใน `.env`
- ผู้รับอีเมลที่แก้ผ่านหน้าเว็บจะถูกเก็บใน `settings.json` (ใน `HOST_DATA_DIR`) และ override ค่า `EMAIL_TO` ใน `.env`
- เพิ่มธนาคารใหม่ในอนาคต: เพิ่มไฟล์ตัวอ่าน PDF ที่ `app/monitor/banks/<code>.py` แล้วลงทะเบียนใน
  `app/monitor/banks/__init__.py` — ไม่ต้องแก้โค้ดส่วนอื่น
- รายชื่อผู้ดูแล (`ADMIN_EMAILS`) ตั้งใน `.env` เท่านั้น — ไม่มีทางแก้จากหน้าเว็บ (กันไม่ให้ยกระดับสิทธิ์ตัวเองผ่าน API)
  ต้องแก้ `.env` แล้ว restart container ถ้าจะเพิ่ม/ลดผู้ดูแล
- session cookie เซ็นด้วย secret ที่ generate เก็บไว้ที่ `{HOST_DATA_DIR}/.session_secret` ให้อัตโนมัติ (คงอยู่ข้าม restart)
  **แนะนำให้ตั้ง `SESSION_SECRET` ใน `.env` เองแทน** — `{HOST_DATA_DIR}` มักเข้าถึงได้ผ่าน SMB/File Station
  บนบัญชี DSM อื่น ใครอ่านไฟล์ `.session_secret` ได้ก็ปลอม session cookie เป็น admin ได้ทันทีโดยไม่ต้อง
  ผ่าน OTP เลย — ถ้าไม่ได้ตั้ง env จะมี log warning เตือนตอนคอนเทนเนอร์บูตทุกครั้ง อย่าง `HOST_DATA_DIR`
  เองก็ไม่ควรแชร์ผ่าน SMB ให้ทุกคนเข้าถึงได้ตามหลักการเดียวกัน
  เว็บนี้ไม่มี HTTPS ในสแตกนี้ (ไม่มี reverse proxy) — ถ้าเปิดใช้งานนอก LAN ที่เชื่อถือได้ ควรเพิ่ม HTTPS/reverse proxy เอง
  **ถ้าเปิดผ่าน reverse proxy หรือ Cloudflare Tunnel ที่มี HTTPS จริงแล้ว ต้องตั้ง `COOKIE_SECURE=1`
  ใน `.env` เสมอ** ไม่งั้น session cookie จะไม่มี flag `Secure` (วิ่ง plaintext ได้ถ้ามีใครดักที่ต้นทาง
  ก่อนถึง proxy) — ค่าเริ่มต้น `COOKIE_SECURE=0` เจตนาให้ใช้งานบน LAN ธรรมดาได้โดยไม่ต้องตั้งอะไรเพิ่ม
  (ตั้ง `1` ทั้งที่ยังไม่มี HTTPS จริง จะทำให้ login ไม่ได้เลยเพราะเบราว์เซอร์ไม่ส่ง cookie ที่มี flag
  `Secure` ผ่าน HTTP)
