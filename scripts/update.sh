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
# commit ที่ deploy แล้วเว็บไม่ขึ้นจนต้องถอยกลับ — กันไม่ให้ task รายสัปดาห์เดินเข้าไปลองซ้ำทุกจันทร์
# (ขั้น 8 เขียน, ขั้น 2.5 อ่าน, ลบทิ้งเมื่อ deploy สำเร็จ) อยู่ใน .gitignore
FAILED_FILE="${PROJECT_DIR}/.deploy_failed"
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

# ตรวจว่าเขียนไฟล์ log ได้จริงก่อนใช้งาน — เจอจริง ส.ค. 2569 กับไฟล์อื่นในตระกูลเดียวกัน: ไฟล์ที่
# ถูกสร้างตอนรันเป็น root จะเป็นของ root แล้วรอบถัดไปที่รันด้วยผู้ใช้ปกติเขียนทับไม่ได้
# ถ้าไม่ดักตรงนี้ อาการจะเนียนมาก — ทั้ง `log()` (สถานะ pipeline เป็นของ tee), `>>"$LOG_FILE" 2>&1`
# ของ build/preflight ล้วนล้มเหลวเพราะ redirect ไม่ใช่เพราะคำสั่งจริงพัง แล้ว `set -e`/`|| die`
# จะรายงานผิดสาเหตุไปหมด (เช่น "build ไม่สำเร็จ" ทั้งที่ build ไม่เคยได้เริ่ม)
# **การเขียน log ไม่สำเร็จ ไม่ควรทำให้ deploy ล้ม** — เตือนแล้วไปต่อโดยทิ้ง log ของรอบนี้
if ! ( : >>"$LOG_FILE" ) 2>/dev/null; then
    echo "⚠️  เขียน ${LOG_FILE} ไม่ได้ (เจ้าของไฟล์คนละคนกับผู้ใช้ที่รันอยู่: uid=$(id -u))"
    echo "    รอบนี้จะไม่บันทึกลงไฟล์ — แก้ถาวรด้วย: sudo rm -f ${LOG_FILE}"
    LOG_FILE=/dev/null
fi

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

TARGET="$($GIT rev-parse "origin/${BRANCH}")"

# ── 2.5 ประตูก่อน merge: commit นี้เคยพังไหม / CI เขียวหรือยัง ──
# ทั้งสองด่านทำ **ก่อน merge โดยเจตนา** — ถ้า die หลัง merge working tree จะค้างอยู่ที่ commit ที่เรา
# เพิ่งปฏิเสธไปเอง ขณะที่คอนเทนเนอร์ยังเป็นของเก่า (git ไม่ตรงกับของที่รันอยู่ = สถานะที่อ่านยากที่สุด
# เวลามาไล่ทีหลัง) ปฏิเสธตั้งแต่ตรงนี้แล้วทุกอย่างยังอยู่ในสถานะเดิมครบ
if [ -f "$FAILED_FILE" ] && [ "$(cat "$FAILED_FILE" 2>/dev/null)" = "$TARGET" ]; then
    log "commit ${TARGET} เคย deploy แล้วเว็บไม่ขึ้น จึงถูกถอยกลับอัตโนมัติไปแล้วรอบหนึ่ง"
    log "    แก้ต้นเหตุแล้ว push commit ใหม่ได้ตามปกติ (commit ใหม่ไม่ติดล็อกนี้)"
    log "    ถ้าจะลอง commit เดิมซ้ำ ให้ลบไฟล์ทิ้งก่อน: rm ${FAILED_FILE}"
    die "ไม่ deploy commit ที่รู้อยู่แล้วว่าพัง"
fi

# ประตู CI — .github/workflows/ci.yml (pytest + docker build + smoke test) ต้องเขียวก่อนถึงยอม deploy
#
# **ต้องถามผลของ workflow ตัวนี้ตัวเดียว ห้ามใช้ endpoint /commits/<sha>/check-runs** — endpoint นั้น
# คืน check ของ *ทุกเจ้า* ที่ผูกกับ commit เดียวกัน ซึ่งบน repo นี้มีของ Dependabot ปนอยู่ด้วย
# (เจอจริงตอนทดสอบ: commit ที่ CI ของเราเขียวครบทั้งสอง job มี check ของ Dependabot ค้าง in_progress
# อยู่อีกสองตัว → ประตูจะตัดสินว่า "CI ยังรันไม่จบ" แล้วบล็อก deploy ทั้งที่ไม่เกี่ยวกันเลย และถ้า job
# ของ Dependabot จบด้วย failure ก็จะบล็อกด้วยเรื่องที่ไม่ใช่โค้ดของเรา)
# endpoint ข้างล่างกรองด้วยชื่อไฟล์ workflow ให้ในตัว และคืน status/conclusion ระดับ run ที่รวมผลของ
# ทุก job ไว้แล้ว — ตัดสินจากสองค่านี้ค่าเดียวจบ ไม่ต้องไล่ทีละ job เอง
#
# แยกผลด้วย grep/cut เพราะ DSM ไม่มี jq ให้ใช้ · repo เป็น public จึงยิงแบบไม่มี token ได้
# (โควตา 60 req/ชม./IP เหลือเฟือ) แต่ถ้าตั้ง GITHUB_TOKEN ใน .env ก็จะแนบให้ — จำเป็นเมื่อไหร่ก็ตาม
# ที่ repo ถูกเปลี่ยนเป็น private (และได้โควตา 5,000 req/ชม. แทน) สคริปต์จึงไม่ต้องแก้อีกตอนสลับ
CI_WORKFLOW="ci.yml"
GH_TOKEN=""      # ตั้งค่าว่างไว้ก่อนเสมอ — สคริปต์รันด้วย `set -u`
gh_api() {
    if [ -n "$GH_TOKEN" ]; then
        curl -fsS -H 'Accept: application/vnd.github+json' \
             -H "Authorization: Bearer ${GH_TOKEN}" "$1" 2>/dev/null || true
    else
        curl -fsS -H 'Accept: application/vnd.github+json' "$1" 2>/dev/null || true
    fi
}

CI_REPO="$($GIT config --get remote.origin.url 2>/dev/null \
    | sed -e 's#.*github\.com[:/]##' -e 's#\.git$##' || true)"

if [ "${SKIP_CI_CHECK:-0}" = "1" ]; then
    log "⏭  ข้ามการเช็ค CI ตามที่สั่ง (SKIP_CI_CHECK=1)"
elif [ -z "$CI_REPO" ]; then
    log "⚠️ อ่านชื่อ repo จาก remote origin ไม่ได้ — ข้ามการเช็ค CI"
else
    GH_TOKEN="$(env_val GITHUB_TOKEN)"
    CI_JSON="$(gh_api "https://api.github.com/repos/${CI_REPO}/actions/workflows/${CI_WORKFLOW}/runs?head_sha=${TARGET}&per_page=1")"

    # ฟิลด์ของ run อยู่ต้น JSON ก่อน object ซ้อนทั้งหมด (…head_sha, event, status, conclusion, …)
    # `grep -m1` จึงได้ค่าของ run เสมอ · `"conclusion": null` จะได้สตริงว่างจาก cut (ยังไม่มีผลสรุป)
    CI_STATUS="$(echo "$CI_JSON" | grep -m1 '"status":' | cut -d'"' -f4)"
    CI_CONCL="$(echo "$CI_JSON" | grep -m1 '"conclusion":' | cut -d'"' -f4)"

    # **ถามไม่ได้ = เตือนแล้วไปต่อ (fail-open)** หลักเดียวกับไฟล์ log ข้างบน: เน็ตล่ม/API rate limit
    # ไม่ควรทำให้ deploy ทั้งกระบวนหยุด · แต่ "ตอบมาว่ายังไม่เสร็จ/ไม่ผ่าน" ต้องหยุด (fail-closed)
    if [ -z "$CI_JSON" ]; then
        log "⚠️ ถามผล CI จาก GitHub ไม่ได้ (เน็ต / rate limit / repo เป็น private แต่ไม่ได้ตั้ง GITHUB_TOKEN)"
        log "    ไปต่อโดยไม่มีประตู — การเช็ค CI ไม่ควรเป็นเหตุให้ deploy ทั้งกระบวนหยุด"
    elif echo "$CI_JSON" | grep -qE '"total_count": *0[^0-9]'; then
        log "⚠️ ยังไม่มีผล CI ของ commit ${TARGET} — commit ที่เก่ากว่าตอนเพิ่ม workflow เป็นแบบนี้ทั้งหมด ไปต่อ"
    elif [ "$CI_STATUS" != "completed" ]; then
        log "CI ของ commit ${TARGET} ยังรันไม่จบ (status=${CI_STATUS:-ไม่ทราบ}) — ดูความคืบหน้าที่ https://github.com/${CI_REPO}/actions"
        die "รอ CI ให้เสร็จก่อนแล้วกดรันใหม่"
    else
        case "$CI_CONCL" in
            success|skipped|neutral)
                log "✅ CI ของ commit ${TARGET} เขียว (conclusion=${CI_CONCL})" ;;
            *)
                log "CI ของ commit ${TARGET} ไม่ผ่าน (conclusion=${CI_CONCL:-ไม่ทราบ}) — ดูรายละเอียดที่ https://github.com/${CI_REPO}/actions"
                log "    ถ้าจำเป็นต้อง deploy จริง ๆ: SKIP_CI_CHECK=1 sh scripts/update.sh"
                die "ไม่ deploy โค้ดที่ CI ไม่เขียว" ;;
        esac
    fi
fi

$GIT merge --ff-only "origin/${BRANCH}" >/dev/null 2>&1 \
    || die "merge แบบ fast-forward ไม่ได้ — โค้ดบน NAS แตกสายจาก origin/${BRANCH} แล้ว"

AFTER="$($GIT rev-parse HEAD)"

# **ห้ามใส่ทางลัด `ไม่มี commit ใหม่ → exit 0` กลับมา** — เดิมสคริปต์ออกทันทีถ้าคอนเทนเนอร์ยังรันอยู่
# ทำให้เคสนี้เงียบสนิท: คนที่ `git pull` ด้วยมือไปแล้วค่อยรันสคริปต์ จะได้ "ไม่มี commit ใหม่"
# ทั้งที่ compose file/Dockerfile เปลี่ยนไปแล้วและคอนเทนเนอร์ที่รันอยู่ยังเป็นของเก่า
# (เจอจริง ส.ค. 2569: healthcheck ที่เพิ่งเพิ่มไม่เคยถูกใช้เลย เพราะไม่มีใคร recreate ให้)
# ปล่อยให้ไหลลงไปทำ build/preflight/up -d ทุกครั้ง — ทั้งสามขั้นเป็น no-op ที่เร็วมากถ้าไม่มีอะไรเปลี่ยน
# (build ใช้ layer cache, `up -d` ไม่ recreate ถ้า config เดิม) แลกกับความแน่นอนว่าของที่รันอยู่
# ตรงกับไฟล์ใน repo เสมอ คุ้มกว่าประหยัดไม่กี่สิบวินาที
if [ "$BEFORE" = "$AFTER" ]; then
    log "ไม่มี commit ใหม่ — จะเช็คให้ว่าคอนเทนเนอร์ที่รันอยู่ตรงกับไฟล์ใน repo ไหม"
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
# ป้ายเวอร์ชันที่ bake เข้า image — `.git/` ไม่ได้อยู่ใน image (dockerignore) แอปจึงถามหา commit เองไม่ได้
# ต้องส่งจากตรงนี้เข้าไปทาง build args (docker-compose.yml → Dockerfile → env → app/version.py)
# ค่าที่ได้ไปโผล่ที่ footer ของทุกหน้า + /api/version + log บรรทัดแรกตอนเว็บบูต
APP_COMMIT="$($GIT rev-parse --short=8 HEAD)"
APP_BUILD_DATE="$($GIT log -1 --format=%cI HEAD)"
export APP_COMMIT APP_BUILD_DATE
log "จะติดป้ายเวอร์ชันให้ image: ${APP_COMMIT} (${APP_BUILD_DATE})"

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
# แยกเป็นฟังก์ชันเพราะขั้น 8 ต้องเรียกซ้ำหลังถอยกลับ — **ตรรกะข้างในเหมือนเดิมทุกบรรทัด**
# curl ต้องยิงที่พอร์ตฝั่ง **host** (HOST_WEB_PORT) ไม่ใช่ WEB_PORT ที่เป็นพอร์ตในคอนเทนเนอร์
# เช็ค RestartCount ควบคู่ไปด้วย — restart loop จะวนจน retry หมดโดย curl ไม่เคยสำเร็จ ถ้าไม่ดูตรงนี้
# จะแยกไม่ออกว่า "ยังบูตไม่เสร็จ" กับ "บูตแล้วตายซ้ำ ๆ" (เสียเวลาไปทั้งคืนเพราะเรื่องนี้มาแล้ว)
wait_healthy() {
    i=0
    while [ "$i" -lt "$HEALTH_RETRIES" ]; do
        if curl -fsS -o /dev/null "http://127.0.0.1:${HOST_WEB_PORT}/api/health"; then
            FMT='{{if .State.Health}}health={{.State.Health.Status}} {{end}}restarts={{.RestartCount}} user={{.Config.User}}'
            STATE="$(docker inspect --format "$FMT" "$CONTAINER" 2>/dev/null || echo '(อ่านไม่ได้)')"
            log "✅ เว็บตอบที่พอร์ต ${HOST_WEB_PORT} แล้ว"
            log "   สถานะคอนเทนเนอร์: ${STATE}"
            # ยืนยันว่าเว็บที่ตอบอยู่คือโค้ดชุดใหม่จริง ไม่ใช่คอนเทนเนอร์เก่าที่ไม่ได้ recreate —
            # เทียบ commit ที่เว็บรายงานกับ commit ที่เพิ่ง build ตรงนี้ที่เดียวจบ (เคสจริง ส.ค. 2569:
            # ของเก่ายังรันอยู่โดยไม่มีใครรู้เพราะ health check ผ่านเหมือนกันทุกประการ)
            # **ยังคงเป็นแค่ ⚠️ ไม่ใช่ die** — CI มี smoke test ที่ครอบเคสนี้ให้แล้ว และการ die ตรงนี้
            # จะไปสั่งถอยกลับในขั้น 8 ทั้งที่เว็บตอบเป็นปกติดี
            RUNNING_VER="$(curl -fsS "http://127.0.0.1:${HOST_WEB_PORT}/api/version" 2>/dev/null || true)"
            log "   เวอร์ชันที่เว็บรายงาน: ${RUNNING_VER:-(อ่านไม่ได้)}"
            case "$RUNNING_VER" in
                *"$APP_COMMIT"*) : ;;
                *) log "   ⚠️ commit ที่เว็บรายงานไม่ตรงกับ ${APP_COMMIT} ที่เพิ่ง build — คอนเทนเนอร์อาจไม่ได้ถูก recreate" ;;
            esac
            log "   (health=starting ได้ในนาทีแรก — start_period ของ healthcheck ตั้งไว้ 60 วิ)"
            return 0
        fi

        RESTARTS="$(docker inspect --format '{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo 0)"
        if [ "$RESTARTS" -gt 2 ]; then
            log "คอนเทนเนอร์ restart ไปแล้ว ${RESTARTS} รอบ = บูตแล้วตายซ้ำ ๆ ไม่ใช่แค่บูตช้า — เลิกรอ"
            return 1
        fi

        i=$((i + 1))
        sleep 2
    done
    return 1
}

if wait_healthy; then
    log "✅ อัปเดตเสร็จ"
    rm -f "$FAILED_FILE" 2>/dev/null || true          # deploy สำเร็จแล้ว ล็อกของรอบก่อนหมดหน้าที่
    docker image prune -f >/dev/null 2>&1 || true     # เก็บกวาด image เก่าที่ไม่มีใครอ้างถึง (ตัว :previous มี tag จึงรอด)
    exit 0
fi

# ── 8. เว็บไม่ขึ้น: ถอยกลับอัตโนมัติ ──
log "log ล่าสุดของคอนเทนเนอร์:"
docker logs --tail 30 "$CONTAINER" 2>&1 | sed 's/^/    /' | tee -a "$LOG_FILE"

# ถอยด้วย `git reset` + rebuild **ไม่ใช่** retag ${CONTAINER}:previous — ชื่อ image ที่ compose ใช้จริง
# ผูกกับชื่อ project การ retag ทับจึงเปราะ และยังทิ้งให้ repo ไม่ตรงกับของที่รันอยู่เหมือนเดิม
# ส่วน reset --hard ทำให้ทั้ง git และคอนเทนเนอร์กลับไปอยู่สถานะเดียวกันจริง ๆ และ build รอบนี้เร็ว
# เพราะ layer cache ของ commit เก่ายังอยู่ครบ · :previous ยัง tag ค้างไว้เป็นตาข่ายชั้นสุดท้ายเหมือนเดิม
if [ "$BEFORE" != "$AFTER" ] && [ "${AUTO_ROLLBACK:-1}" = "1" ]; then
    log "⏪ ถอยกลับไป commit ${BEFORE} อัตโนมัติ…"
    echo "$AFTER" >"$FAILED_FILE" 2>/dev/null \
        || log "    ⚠️ เขียน ${FAILED_FILE} ไม่ได้ — รอบหน้าจะไม่มีอะไรกันไม่ให้ลอง commit นี้ซ้ำ"

    if $GIT reset --hard "$BEFORE" >>"$LOG_FILE" 2>&1; then
        # ป้ายเวอร์ชันต้องคำนวณใหม่จาก commit เก่า ไม่งั้น image ที่ได้จะติดป้ายของ commit ที่เพิ่งถอยทิ้ง
        APP_COMMIT="$($GIT rev-parse --short=8 HEAD)"
        APP_BUILD_DATE="$($GIT log -1 --format=%cI HEAD)"
        export APP_COMMIT APP_BUILD_DATE

        if $COMPOSE up -d --build >>"$LOG_FILE" 2>&1 && wait_healthy; then
            log "✅ ถอยกลับสำเร็จ — เว็บกลับมาเป็น commit ${BEFORE} แล้ว"
            log "   commit ${AFTER} ถูกกันไว้ใน ${FAILED_FILE} จะไม่ถูก deploy ซ้ำจนกว่าจะลบไฟล์นั้นทิ้ง"
            log "   แก้ต้นเหตุแล้ว push commit ใหม่ได้ตามปกติ (commit ใหม่ไม่ติดล็อกนี้)"
            # **exit 1 ไม่ใช่ 0** — เว็บกลับมาแล้วก็จริง แต่ deploy รอบนี้ล้มเหลว ต้องให้ Task Scheduler
            # ส่งอีเมลแจ้ง ไม่งั้นการถอยกลับจะเงียบสนิทและไม่มีใครรู้ว่าของใหม่ยังไม่ได้ขึ้น
            exit 1
        fi
        log "❌ ถอยกลับแล้วเว็บยังไม่ขึ้น — ต้องกู้ด้วยมือ"
    else
        log "❌ git reset --hard ไม่สำเร็จ — ต้องกู้ด้วยมือ"
    fi
fi

log "ทางถอย (คัดลอกไปรันได้เลย):"
log "    cd ${PROJECT_DIR} && ${GIT} reset --hard ${BEFORE} && ${COMPOSE} up -d --build"
if [ -n "$PREV_IMAGE" ]; then
    log "    image ของเวอร์ชันเดิมยังอยู่ที่ ${PREV_IMAGE} (กู้ด้วยมือได้ ไม่ถูก prune ทิ้งเพราะมี tag)"
fi
die "คอนเทนเนอร์ start แล้วแต่เว็บไม่ตอบที่พอร์ต ${HOST_WEB_PORT} ภายใน $((HEALTH_RETRIES * 2)) วิ"
