#!/bin/bash
#
# 가온교회 주일예배 슬라이드 자동 생성 + Google Drive 업로드
#
# 매주 토요일 20:00 crontab으로 실행:
#   0 20 * * 6 /Users/yonggyup/Develop/gp1/gaon-church-ppt/scripts/weekly_routine.sh >> /tmp/gaon-routine.log 2>&1
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

export GMAIL_SENDER="${GMAIL_SENDER:-gikimiad@gmail.com}"

echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') 가온교회 Routine 시작"
echo "=========================================="

# 1. Vercel API에서 예배 정보 가져오기
echo "[1/3] 예배 정보 가져오기..."
python3 scripts/fetch_worship.py
if [ $? -ne 0 ]; then
    echo "FAIL: 예배 정보를 가져올 수 없습니다."
    exit 1
fi

# 2. 슬라이드 생성
echo "[2/3] 슬라이드 생성..."
python3 scripts/generate_ppt.py
if [ $? -ne 0 ]; then
    echo "FAIL: 슬라이드 생성 실패."
    exit 1
fi

# 출력 파일명 계산
DATE_STR=$(head -1 input/next_sunday.txt | sed 's/날짜 : //')
YY=$(echo "$DATE_STR" | cut -d- -f1 | tail -c3)
MM=$(printf "%02d" "$(echo "$DATE_STR" | cut -d- -f2)")
DD=$(printf "%02d" "$(echo "$DATE_STR" | cut -d- -f3)")
OUTPUT="output/${YY}_${MM}_${DD}.pptx"

if [ ! -f "$OUTPUT" ]; then
    echo "FAIL: 출력 파일 없음: $OUTPUT"
    exit 1
fi

# 3. Google Drive 업로드 + 이메일
echo "[3/3] Google Drive 업로드..."
python3 scripts/upload_and_notify.py "$OUTPUT"

echo ""
echo "$(date '+%Y-%m-%d %H:%M:%S') Routine 완료: $OUTPUT"
