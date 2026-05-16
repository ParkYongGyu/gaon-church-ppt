#!/usr/bin/env python3
"""Drive 폴더 진단: driveId 존재 여부로 Shared Drive 여부 판별."""
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1UpMqB6gIFZqBmxGfQRQBJSibAmUn0FlV"

sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
if not sa_json:
    sys.exit("GOOGLE_SERVICE_ACCOUNT_JSON 미설정")

info = json.loads(sa_json)
print(f"Service Account email: {info.get('client_email')}")

creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
service = build("drive", "v3", credentials=creds)

try:
    meta = service.files().get(
        fileId=FOLDER_ID,
        fields="id,name,mimeType,driveId,parents,owners,shared,capabilities",
        supportsAllDrives=True,
    ).execute()
    print("--- Folder metadata ---")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    if meta.get("driveId"):
        print(f"\n결론: Shared Drive 내부 폴더 (driveId={meta['driveId']})")
    else:
        print("\n결론: My Drive 폴더 (Shared Drive 아님) — Service Account 업로드 불가")
except Exception as e:
    print(f"폴더 조회 실패: {e}")

print("\n--- Service Account가 접근 가능한 Shared Drives ---")
try:
    drives = service.drives().list(fields="drives(id,name)").execute()
    if drives.get("drives"):
        for d in drives["drives"]:
            print(f"  - {d['name']}: {d['id']}")
    else:
        print("  (없음 — SA가 어떤 Shared Drive에도 멤버로 추가되지 않음)")
except Exception as e:
    print(f"  조회 실패: {e}")
