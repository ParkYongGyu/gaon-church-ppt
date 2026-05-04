#!/usr/bin/env python3
"""
Vercel에 배포된 웹 폼에서 예배 정보를 가져와 input/next_sunday.txt로 저장.

다가오는 일요일(오늘이 일요일이면 오늘) 날짜를 기준으로 조회합니다.

사용법:
  python3 scripts/fetch_worship.py          # 다가오는 일요일
  python3 scripts/fetch_worship.py 2026-5-3 # 특정 날짜

환경변수:
  GAON_API_URL   — Vercel 배포 URL (예: https://gaon-church.vercel.app)
  GAON_API_KEY   — API 인증 키 (Vercel 환경변수 ROUTINE_API_KEY와 동일)
"""

import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "input" / "next_sunday.txt"


def next_sunday() -> str:
    today = date.today()
    days_ahead = 6 - today.weekday()  # weekday: Mon=0 ... Sun=6
    if days_ahead < 0:
        days_ahead += 7
    if days_ahead == 0:
        days_ahead = 0  # 오늘이 일요일이면 오늘
    target = today + timedelta(days=days_ahead)
    return f"{target.year}-{target.month}-{target.day}"


def main():
    api_url = os.environ.get(
        "GAON_API_URL", "https://web-beta-neon-29.vercel.app"
    ).rstrip("/")
    api_key = os.environ.get("GAON_API_KEY", "")

    target_date = sys.argv[1] if len(sys.argv) > 1 else next_sunday()

    url = f"{api_url}/api/worship?date={target_date}&format=txt"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"{target_date} 데이터가 없습니다.")
        sys.exit(f"API 오류: {e.code} {e.reason}")

    if body == "null" or not body.strip():
        sys.exit(f"{target_date} 데이터가 아직 입력되지 않았습니다.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(body, encoding="utf-8")
    print(f"저장 완료 ({target_date}): {OUTPUT_PATH}")

    sermon_url = f"{api_url}/api/worship?date={target_date}&format=sermon-pptx"
    sermon_path = PROJECT_ROOT / "input" / "sermon.pptx"
    try:
        sermon_req = urllib.request.Request(sermon_url, headers=headers)
        with urllib.request.urlopen(sermon_req) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "presentation" in ct:
                sermon_path.write_bytes(resp.read())
                print(f"설교 PPT 저장: {sermon_path}")
            else:
                sermon_path.unlink(missing_ok=True)
    except Exception:
        sermon_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
