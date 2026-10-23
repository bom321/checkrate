#!/bin/sh
# prod-log.sh — อ่าน log/ผลลัพธ์ของ production (NAS) แบบ **อ่านอย่างเดียว** ผ่าน ssh
#
# มีไว้ให้ Claude Code อ่าน production ได้เองโดยอนุญาตแค่สคริปต์นี้ (Bash(scripts/prod-log.sh:*))
# แทนการอนุญาต `ssh nas` ทั้งก้อน ที่ครอบคำสั่งเขียน/ลบ/รีสตาร์ทได้ด้วย — จึงห้ามเพิ่มคำสั่งย่อยที่แก้ไขอะไร
# บน NAS และอาร์กิวเมนต์ทุกตัวต้องผ่าน regex ก่อนต่อเข้าคำสั่งฝั่ง remote (กัน shell injection ผ่าน ssh)
#
# ssh ผ่าน Cloudflare Access — session หมดอายุเมื่อไหร่จะเปิดเบราว์เซอร์ให้ยืนยันตัวตนก่อน
#
# ใช้:
#   scripts/prod-log.sh log [CODE|ALL] [N]          log ไฟล์ปัจจุบัน N บรรทัดล่าสุด (ไม่รวม DEBUG, ค่าเริ่มต้น 100)
#   scripts/prod-log.sh oldlog YYYY-MM-DD [CODE|ALL] [N]   log ไฟล์ที่หมุนแล้ว (ดูชื่อจาก backups)
#   scripts/prod-log.sh result CODE                 <code>_result.json
#   scripts/prod-log.sh csv CODE [N]                CSV header + N แถวล่าสุด (ค่าเริ่มต้น 10)
#   scripts/prod-log.sh pdfs CODE [N]               ไฟล์ PDF ล่าสุด N ไฟล์ (ค่าเริ่มต้น 10)
#   scripts/prod-log.sh backups                     รายชื่อไฟล์ log ที่หมุนแล้ว + ขนาด
set -eu

HOST="${PROD_SSH_HOST:-nas}"
DATA_DIR="${PROD_DATA_DIR:-/volume1/bom321/Work/deposit-rate/docker/checkrate/data}"
MAX_LINES=5000

die() { echo "prod-log: $*" >&2; exit 2; }

usage() {
    sed -n '/^# ใช้:/,/^set -eu/p' "$0" | sed '$d; s/^# \{0,1\}//'
    exit 2
}

code_arg() {   # รหัสธนาคาร → ตัวพิมพ์ใหญ่ (ALL = ทุกธนาคาร)
    c=$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')
    printf '%s' "$c" | grep -Eq '^[A-Z]{2,10}$' || die "รหัสธนาคารไม่ถูกต้อง: $1"
    printf '%s' "$c"
}

lines_arg() {  # จำนวนบรรทัด 1..MAX_LINES
    printf '%s' "$1" | grep -Eq '^[0-9]{1,5}$' || die "จำนวนบรรทัดต้องเป็นตัวเลข: $1"
    [ "$1" -ge 1 ] && [ "$1" -le "$MAX_LINES" ] || die "จำนวนบรรทัดต้องอยู่ระหว่าง 1-$MAX_LINES"
    printf '%s' "$1"
}

remote() { exec ssh -o ConnectTimeout=20 "$HOST" "$1"; }

# log file + filter → คำสั่ง remote (กรอง DEBUG ทิ้ง · [CODE] ตรงตามที่ data_access.tail_log ใช้)
log_cmd() {
    file="$1"; code="$2"; n="$3"
    if [ "$code" = "ALL" ]; then
        printf "grep -v '| DEBUG ' '%s' | tail -n %s" "$file" "$n"
    else
        printf "grep -v '| DEBUG ' '%s' | grep -F '[%s]' | tail -n %s" "$file" "$code" "$n"
    fi
}

[ $# -ge 1 ] || usage
cmd="$1"; shift

case "$cmd" in
    log)
        code=$(code_arg "${1:-ALL}"); n=$(lines_arg "${2:-100}")
        remote "$(log_cmd "$DATA_DIR/rate_monitor.log" "$code" "$n")"
        ;;
    oldlog)
        [ $# -ge 1 ] || die "ต้องระบุวันที่ (YYYY-MM-DD) — ดูจาก: prod-log.sh backups"
        printf '%s' "$1" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' || die "วันที่ไม่ถูกต้อง: $1"
        code=$(code_arg "${2:-ALL}"); n=$(lines_arg "${3:-100}")
        remote "$(log_cmd "$DATA_DIR/rate_monitor.log.$1" "$code" "$n")"
        ;;
    result)
        [ $# -ge 1 ] || die "ต้องระบุรหัสธนาคาร"
        lc=$(code_arg "$1" | tr '[:upper:]' '[:lower:]')
        remote "cat '$DATA_DIR/${lc}_result.json'"
        ;;
    csv)
        [ $# -ge 1 ] || die "ต้องระบุรหัสธนาคาร"
        lc=$(code_arg "$1" | tr '[:upper:]' '[:lower:]'); n=$(lines_arg "${2:-10}")
        f="$DATA_DIR/${lc}_deposit_rate.csv"
        remote "head -n 1 '$f'; tail -n +2 '$f' | tail -n $n"
        ;;
    pdfs)
        [ $# -ge 1 ] || die "ต้องระบุรหัสธนาคาร"
        code=$(code_arg "$1"); n=$(lines_arg "${2:-10}")
        remote "ls -l '$DATA_DIR/pdfs/$code' | tail -n $n"
        ;;
    backups)
        remote "ls -l '$DATA_DIR'/rate_monitor.log*"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        die "ไม่รู้จักคำสั่ง: $cmd (ดู: prod-log.sh help)"
        ;;
esac
