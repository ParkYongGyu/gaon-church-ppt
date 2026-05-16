#!/usr/bin/env python3
"""
PPT를 Google Drive에 업로드하고 이메일로 링크를 전송합니다.

인증 방식 (우선순위 순):
  1. Service Account (CI/자동화 권장 — 토큰 만료 없음)
     - GOOGLE_SERVICE_ACCOUNT_JSON 환경변수 또는 .secrets/service_account.json
  2. OAuth2 User Credentials (로컬 수동 실행용)
     - .secrets/google_credentials.json + .secrets/google_token.json

환경변수 (이메일 전송용, 선택):
  GMAIL_SENDER       — 발신 Gmail 주소
  GMAIL_APP_PASSWORD  — Gmail 앱 비밀번호
"""

import json
import os
import sys
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = PROJECT_ROOT / ".secrets" / "google_token.json"
CREDS_PATH = PROJECT_ROOT / ".secrets" / "google_credentials.json"
SA_PATH = PROJECT_ROOT / ".secrets" / "service_account.json"

DRIVE_FOLDER_NAME = "가온교회 주일예배"
DRIVE_FOLDER_ID = os.environ.get(
    "GAON_DRIVE_FOLDER_ID", "1UpMqB6gIFZqBmxGfQRQBJSibAmUn0FlV"
)
DEFAULT_RECIPIENT = "gikimiad@gmail.com"
PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


def _get_service_account_creds():
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    if SA_PATH.exists():
        return service_account.Credentials.from_service_account_file(
            str(SA_PATH), scopes=SCOPES
        )
    return None


def _get_oauth_creds():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                sys.exit(
                    "인증 정보가 없습니다.\n"
                    "Service Account: GOOGLE_SERVICE_ACCOUNT_JSON 환경변수 "
                    "또는 .secrets/service_account.json\n"
                    "OAuth2: .secrets/google_credentials.json 필요"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def get_drive_service():
    creds = _get_service_account_creds()
    if creds:
        print("Service Account 인증 사용")
    else:
        creds = _get_oauth_creds()
        print("OAuth2 사용자 인증 사용")
    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service) -> str:
    if DRIVE_FOLDER_ID:
        return DRIVE_FOLDER_ID

    results = (
        service.files()
        .list(
            q=f"name='{DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces="drive",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]

    folder = (
        service.files()
        .create(
            body={
                "name": DRIVE_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
            },
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return folder["id"]


def upload_to_drive(service, file_path: Path) -> str:
    folder_id = get_or_create_folder(service)
    media = MediaFileUpload(str(file_path), mimetype=PPTX_MIME, resumable=True)

    file_metadata = {
        "name": file_path.name,
        "parents": [folder_id],
    }

    existing = (
        service.files()
        .list(
            q=f"name='{file_path.name}' and '{folder_id}' in parents and trashed=false",
            spaces="drive",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )

    if existing:
        file = (
            service.files()
            .update(
                fileId=existing[0]["id"],
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    else:
        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    return file["webViewLink"]


def parse_recipients_from_input() -> list[str]:
    input_path = PROJECT_ROOT / "input" / "next_sunday.txt"
    if not input_path.exists():
        return [DEFAULT_RECIPIENT]
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("수신자") and ":" in line:
            raw = line.split(":", 1)[1].strip()
            if raw:
                return [r.strip() for r in raw.split(",") if r.strip()]
    return [DEFAULT_RECIPIENT]


def send_email(link: str, filename: str, recipients: list[str] | None = None):
    if not recipients:
        recipients = [DEFAULT_RECIPIENT]

    sender = os.environ.get("GMAIL_SENDER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not sender or not password:
        print(f"  링크: {link}")
        print(f"  수신자: {', '.join(recipients)}")
        print(
            "  (이메일 전송을 위해 GMAIL_SENDER, GMAIL_APP_PASSWORD를 설정하세요)"
        )
        return False

    body = (
        f"이번 주일예배 슬라이드가 준비되었습니다.\n\n"
        f"다운로드: {link}\n\n"
        f"파일명: {filename}"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"가온교회 주일예배 슬라이드 - {filename}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    return True


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python3 scripts/upload_and_notify.py <pptx파일>")

    file_path = Path(sys.argv[1]).resolve()
    if not file_path.exists():
        sys.exit(f"파일이 없습니다: {file_path}")

    print(f"Google Drive 업로드 중: {file_path.name}")
    service = get_drive_service()
    link = upload_to_drive(service, file_path)
    print(f"업로드 완료: {link}")

    recipients = parse_recipients_from_input()
    if send_email(link, file_path.name, recipients):
        print(f"이메일 전송 완료: {', '.join(recipients)}")

    print(f"DRIVE_LINK={link}")


if __name__ == "__main__":
    main()
