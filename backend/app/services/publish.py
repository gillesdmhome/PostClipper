from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.config import settings


def create_export_bundle(
    job_id: str,
    candidate_id: str,
    video_path: str,
    metadata: dict,
) -> tuple[bool, str, str | None]:
    """Zip video + sidecar JSON for TikTok / IG handoff or scheduler upload."""
    base = settings.data_dir / "jobs" / job_id / "exports"
    base.mkdir(parents=True, exist_ok=True)
    zip_path = base / f"{candidate_id}_bundle.zip"
    meta_path = base / f"{candidate_id}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(video_path, arcname="clip.mp4")
            z.write(str(meta_path), arcname="metadata.json")
    except OSError as e:
        return False, str(e), None
    return True, "", str(zip_path.resolve())


def try_youtube_shorts_upload(video_path: str, title: str, description: str) -> tuple[bool, str, str | None]:
    """
    Optional resumable upload via YouTube Data API v3.
    Requires: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
    and YOUTUBE_CLIENT_SECRETS_PATH; token stored at youtube_token_path or data/youtube_token.json
    """
    secrets = settings.youtube_client_secrets_path
    token_path = settings.youtube_token_path or (settings.data_dir / "youtube_token.json")

    if not secrets or not Path(secrets).is_file():
        return False, "YouTube client secrets not configured", None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return False, "google-api-python-client not installed", None

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    try:
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "public"},
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
        vid = response.get("id")
        return True, "", vid
    except Exception as e:
        return False, str(e), None
