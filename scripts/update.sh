#!/bin/sh
# update.sh — อัปเดต CheckRate บน Synology:
#   git pull → build (ยังไม่แตะคอนเทนเนอร์ที่รันอยู่) → preflight → restart → เช็คว่าเว็บขึ้นจริง
#
# ลำดับนี้ตั้งใจให้ "ของที่รันอยู่ตอนนี้" รอดไว้ให้นานที่สุด — บทเรียนจาก ส.ค. 2569 ที่ deploy แล้ว
# คอนเทนเนอร์เขียน /data ไม่ได้ (Synology ACL) กลายเป็น restart loop และเว็บดับยาวหลายชั่วโมง
# preflight จะทดสอบสิทธิ์เขียนด้วย uid/gid จริงก่อน แล้ว die ทิ้งตั้งแต่ตอนที่ของเดิมยังรันอยู่
# ก่อน build จะ tag image เดิมไว้เป็น <container>:previous ให้มีทางถอยกลับได้ทันที
#
# ออกแบบให้รันจาก DSM Task Scheduler (User-defined script, รันเป็น root, ไม่มี tty):
#   sh /volume1/bom321/Work/deposit-rate/docker/checkrate/scripts/update.sh
# รันมือผ่าน SSH ก็ได้เหมือนกัน — ผลลัพธ์ออกทั้ง stdout และไฟล์ log
#
# เงื่อนไข: โค้ดบน NAS ต้องเป็น git clone (ไม่ใช่ไฟล์ที่ copy ผ่าน File Station)
#           และต้องติดตั้ง Git Server package จาก Package Center ให้มีคำสั่ง git
#
# ข้อมูลจริง (CSV/PDF/config) อยู่ที่ HOST_DATA_DIR นอกโฟลเดอร์โปรเจกต์ — สคริปต์นี้ไม่แตะเลย
set -eu

# Task Scheduler ให้ PATH มาแคบมาก — เติม path ของ docker/git บน DSM เอง
PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PATH

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Task Scheduler รันเป็น root แต่ไฟล์ repo เป็นของ user บน NAS — git จะปฏิเสธด้วย "dubious ownership"
# ตั้ง safe.directory เฉพาะคำสั่งในสคริปต์นี้ผ่าน -c (ไม่เขียนลง ~/.gitconfig ของ root ให้เป็นสถานะค้าง)
GIT="git -c safe.directory=${PROJECT_DIR}"
LOG_FILE="${PROJECT_DIR}/update.log"
BRANCH="${BRANCH:-main}"
CONTAINER="checkrate"
HEALTH_RETRIES=45          # เช็ค health ทุก 2 วิ รวมสูงสุด ~90 วิ (image build เสร็จแล้ว แค่รอ uvicorn ขึ้น)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "❌ ล้มเหลว: $*"
    exit 1
}

cd "$PROJECT_DIR"

log "───────────────────────────────────────────"
log "เริ่มอัปเดต CheckRate ที่ ${PROJECT_DIR}"

# ── 1. ตรวจของที่ต้องมีก่อน ──
command -v git >/dev/null 2>&1 || die "ไม่พบคำสั่ง git (ติดตั้ง Git Server จาก Package Center)"
command -v docker >/dev/null 2>&1 || die "ไม่พบคำสั่ง docker"
[ -d .git ] || die "โฟลเดอร์นี้ไม่ใช่ git repo — สคริปต์นี้อัปเดตด้วย git pull เท่านั้น"
[ -f .env ] || die "ไม่พบไฟล์ .env (คัดลอกจาก .env.example แล้วใส่ค่าจริงก่อน)"

# docker-compose v1 (แยก binary) หรือ v2 (plugin ของ docker) แล้วแต่รุ่น DSM
if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
elif docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    die "ไม่พบทั้ง docker-compose และ docker compose"
fi

# อ่านค่าจาก .env — ไม่ source ทั้งไฟล์ (ค่าที่มีช่องว่าง/เครื่องหมายพิเศษจะทำ shell พังหรือรันคำสั่งได้)
# สถานะของ pipeline คือของ tr ตัวท้าย (สำเร็จเสมอแม้ grep ไม่เจอ) จึงไม่ชน `set -e`
env_val() {
    grep -E "^${1}=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'" | tr -d '[:space:]'
}

# ค่า default ทั้งหมดตรงนี้ **ต้องตรงกับ docker-compose.yml** — ถ้าแก้ที่นั่นต้องแก้ที่นี่ด้วย
PUID="$(env_val PUID)";                 PUID="${PUID:-1000}"
PGID="$(env_val PGID)";                 PGID="${PGID:-1000}"
WEB_PORT="$(env_val WEB_PORT)";         WEB_PORT="${WEB_PORT:-8080}"
HOST_WEB_PORT="$(env_val HOST_WEB_PORT)"
# พอร์ตฝั่ง host = ตัวที่ curl/เบราว์เซอร์ใช้ — default ต้องเป็น 8080 **ตรง ๆ ห้าม fallback ไป $WEB_PORT**
# เพราะ docker-compose.yml เขียนไว้แบบนั้น (compose v1 ไม่รองรับ default ซ้อน) ถ้าตรงนี้ไม่ตรงกับ compose
# จะได้เคส "เว็บขึ้นจริงแต่ health check ยิงผิดพอร์ต" ซึ่งอ่าน log แล้วแยกจากของพังไม่ออก
HOST_WEB_PORT="${HOST_WEB_PORT:-8080}"
HOST_DATA_DIR="$(env_val HOST_DATA_DIR)"

# ── 2. ดึงโค้ดใหม่ ──
BEFORE="$($GIT rev-parse HEAD)"
log "commit ปัจจุบัน: $($GIT log -1 --format='%h %s' HEAD)"

# สคริปต์นี้ออกแบบให้รันเป็น root จาก DSM Task Scheduler — ไฟล์ที่ git สร้างใหม่ (packfile ตอน
# fetch/repack) บนโฟลเดอร์แชร์ที่เปิด Synology ACL จะได้ POSIX mode 000 ทำให้รอบถัดไปที่รัน git
# ด้วยผู้ใช้ปกติพังทั้ง repo ด้วย "packfile ... index unavailable" + reflog/blob เสียเป็นร้อยบรรทัด
# (เจอจริง ส.ค. 2569 — เสียเวลาไล่หาว่า repo เสียทั้งที่ไฟล์อยู่ครบ แค่อ่านไม่ได้)
# core.sharedRepository สั่งให้ git ตั้ง mode เองโดยไม่สนใจ umask ของ root — ตั้งทุกรอบเพราะ idempotent
$GIT config core.sharedRepository 0644 2>/dev/null || true

$GIT fetch --quiet origin "$BRANCH" || die "git fetch ไม่สำเร็จ (เช็คเน็ต/สิทธิ์ของ remote)"

# ตามเก็บไฟล์ที่ถูกสร้างไว้ก่อนหน้าที่จะตั้ง core.sharedRepository (และตัวที่ git ไม่ได้จัดการให้)
if [ "$(id -u)" = "0" ]; then
    chmod -R a+rX .git 2>/dev/null || true
fi

# กันเคสมีคนแก้ไฟล์บน NAS ค้างไว้ — merge จะพังกลางทางแล้ว repo ค้างสถานะแปลก ๆ
if ! $GIT diff --quiet || ! $GIT diff --cached --quiet; then
    die "มีไฟล์ที่ถูกแก้ค้างไว้บน NAS (git status ไม่สะอาด) — เก็บกวาดก่อนแล้วค่อยรันใหม่"
fi

$GIT merge --ff-only "origin/${BRANCH}" >/dev/null 2>&1 \
    || die "merge แบบ fast-forward ไม่ได้ — โค้ดบน NAS แตกสายจาก origin/${BRANCH} แล้ว"

AFTER="$($GIT rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
    log "ไม่มี commit ใหม่ — ข้ามการ build"
    # ยังเช็คต่อว่าคอนเทนเนอร์รันอยู่จริงไหม (อาจดับไปเองระหว่างนี้)
    if [ -n "$(docker ps -q -f "name=^${CONTAINER}$")" ]; then
        log "✅ คอนเทนเนอร์ ${CONTAINER} ยังรันอยู่ปกติ"
        exit 0
    fi
    log "⚠️ ไม่มี commit ใหม่ แต่คอนเทนเนอร์ไม่ได้รันอยู่ — จะสั่ง start ให้"
else
    log "อัปเดตเป็น: $($GIT log -1 --format='%h %s' HEAD)"
    log "ไฟล์ที่เปลี่ยน:"
    $GIT diff --name-only "$BEFORE" "$AFTER" | sed 's/^/    /' | tee -a "$LOG_FILE"
fi

# ── 3. tag image เดิมไว้เป็นทางถอย ──
# ทำก่อน build เสมอ — image ที่รันอยู่ตอนนี้คือตัวเดียวที่พิสูจน์แล้วว่าใช้ได้จริงบนเครื่องนี้
# (มี tag ค้างไว้ = `docker image prune -f` ตอนท้ายจะไม่ลบทิ้ง)
PREV_IMAGE=""
CUR_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null || true)"
if [ -n "$CUR_IMAGE_ID" ]; then
    if docker tag "$CUR_IMAGE_ID" "${CONTAINER}:previous" 2>/dev/null; then
        PREV_IMAGE="${CONTAINER}:previous"
        log "tag image เดิมไว้เป็น ${PREV_IMAGE} แล้ว (ทางถอยถ้าตัวใหม่พัง)"
    fi
fi

# ── 4. build (ยังไม่แตะคอนเทนเนอร์ที่รันอยู่) ──
log "กำลัง build image (อาจใช้เวลาหลายนาทีถ้า Dockerfile เปลี่ยน)…"
$COMPOSE build >>"$LOG_FILE" 2>&1 || die "build ไม่สำเร็จ (ดูรายละเอียดใน ${LOG_FILE}) — ของเดิมยังรันอยู่ ไม่ได้แตะ"

# ── 5. preflight: ทดสอบสิทธิ์เขียน HOST_DATA_DIR ด้วย uid/gid ที่จะใช้จริง ──
# ตรงนี้คือด่านที่กันเคส ส.ค. 2569 ซ้ำ: คอนเทนเนอร์รัน non-root แล้วเขียน /data ไม่ได้เพราะ Synology ACL
# → entrypoint.sh exit 1 → restart loop → เว็บดับ ทดสอบก่อนที่นี่แล้วหยุดทิ้ง **ตอนที่ของเดิมยังรันอยู่**
NEW_IMAGE="$($COMPOSE images -q "$CONTAINER" 2>/dev/null | head -1 || true)"
[ -n "$NEW_IMAGE" ] || NEW_IMAGE="$CUR_IMAGE_ID"     # compose v1 เก่าไม่มี `images -q` — ถอยไปใช้ตัวเดิม

if [ -z "$NEW_IMAGE" ] || [ -z "$HOST_DATA_DIR" ]; then
    log "⚠️ ข้าม preflight (หา image หรือ HOST_DATA_DIR ไม่ได้) — deploy ครั้งแรกก็เป็นแบบนี้ได้ ถือว่าปกติ"
else
    log "preflight: ทดสอบเขียน ${HOST_DATA_DIR} ด้วย uid=${PUID} gid=${PGID}…"
    if docker run --rm --user "${PUID}:${PGID}" -v "${HOST_DATA_DIR}:/data" \
            --entrypoint /bin/sh "$NEW_IMAGE" \
            -c 'touch /data/.deploy_wtest && rm -f /data/.deploy_wtest' >>"$LOG_FILE" 2>&1; then
        log "✅ preflight ผ่าน"
    else
        log "เจ้าของโฟลเดอร์ข้อมูลตอนนี้:"
        ls -nd "$HOST_DATA_DIR" 2>&1 | sed 's/^/    /' | tee -a "$LOG_FILE"
        log "    (มี + ท้าย mode = โฟลเดอร์เปิด Synology ACL ซึ่งทับ POSIX bits — chown ไม่ช่วย)"
        log "    ดู ACL จริง: sudo synoacltool -get \"${HOST_DATA_DIR}\""
        log "    ทางแก้: รัน  id <ชื่อผู้ใช้ DSM>  แล้วตั้ง PUID/PGID ใน .env ให้ตรง"
        die "uid ${PUID}:${PGID} เขียน ${HOST_DATA_DIR} ไม่ได้ — ไม่ deploy ต่อ (คอนเทนเนอร์เดิมยังรันอยู่ตามปกติ)"
    fi
fi

# ── 6. restart ──
log "กำลัง restart คอนเทนเนอร์…"
$COMPOSE up -d >>"$LOG_FILE" 2>&1 || die "docker-compose up -d ไม่สำเร็จ (ดูรายละเอียดใน ${LOG_FILE})"

# ── 7. ยืนยันว่าเว็บขึ้นจริง ไม่ใช่แค่คอนเทนเนอร์ start แล้ว crash ──
# curl ต้องยิงที่พอร์ตฝั่ง **host** (HOST_WEB_PORT) ไม่ใช่ WEB_PORT ที่เป็นพอร์ตในคอนเทนเนอร์
# เช็ค RestartCount ควบคู่ไปด้วย — restart loop จะวนจน retry หมดโดย curl ไม่เคยสำเร็จ ถ้าไม่ดูตรงนี้
# จะแยกไม่ออกว่า "ยังบูตไม่เสร็จ" กับ "บูตแล้วตายซ้ำ ๆ" (เสียเวลาไปทั้งคืนเพราะเรื่องนี้มาแล้ว)
i=0
while [ "$i" -lt "$HEALTH_RETRIES" ]; do
    if curl -fsS -o /dev/null "http://127.0.0.1:${HOST_WEB_PORT}/api/health"; then
        FMT='{{if .State.Health}}health={{.State.Health.Status}} {{end}}restarts={{.RestartCount}} user={{.Config.User}}'
        STATE="$(docker inspect --format "$FMT" "$CONTAINER" 2>/dev/null || echo '(อ่านไม่ได้)')"
        log "✅ อัปเดตเสร็จ — เว็บตอบที่พอร์ต ${HOST_WEB_PORT} แล้ว"
        log "   สถานะคอนเทนเนอร์: ${STATE}"
        log "   (health=starting ได้ในนาทีแรก — start_period ของ healthcheck ตั้งไว้ 60 วิ)"
        docker image prune -f >/dev/null 2>&1 || true   # เก็บกวาด image เก่าที่ไม่มีใครอ้างถึง (ตัว :previous มี tag จึงรอด)
        exit 0
    fi

    RESTARTS="$(docker inspect --format '{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo 0)"
    if [ "$RESTARTS" -gt 2 ]; then
        log "คอนเทนเนอร์ restart ไปแล้ว ${RESTARTS} รอบ = บูตแล้วตายซ้ำ ๆ ไม่ใช่แค่บูตช้า — เลิกรอ"
        break
    fi

    i=$((i + 1))
    sleep 2
done

log "log ล่าสุดของคอนเทนเนอร์:"
docker logs --tail 30 "$CONTAINER" 2>&1 | sed 's/^/    /' | tee -a "$LOG_FILE"
log "ทางถอย (คัดลอกไปรันได้เลย):"
log "    cd ${PROJECT_DIR} && ${GIT} reset --hard ${BEFORE} && ${COMPOSE} up -d --build"
if [ -n "$PREV_IMAGE" ]; then
    log "    image ของเวอร์ชันเดิมยังอยู่ที่ ${PREV_IMAGE} (กู้ด้วยมือได้ ไม่ถูก prune ทิ้งเพราะมี tag)"
fi
die "คอนเทนเนอร์ start แล้วแต่เว็บไม่ตอบที่พอร์ต ${HOST_WEB_PORT} ภายใน $((HEALTH_RETRIES * 2)) วิ"
