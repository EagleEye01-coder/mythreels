"""Stage 5: upload to YouTube as PRIVATE. Approval = you flip it to Public in YouTube Studio.

Env (GitHub secrets): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
import os


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    return build("youtube", "v3", credentials=creds)


def upload(video_path, title, description, cfg, lang, dry=False):
    yt = cfg["youtube"]
    desc = f"{description}\n\n{yt['ai_disclosure_line']}"
    if dry:
        print(f"[dry] would upload {video_path} as '{title}' ({lang}, {yt['privacy']})")
        return "DRY_RUN"
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": title[:100], "description": desc, "tags": yt["tags"],
                    "categoryId": yt["category_id"],
                    "defaultAudioLanguage": lang, "defaultLanguage": lang},
        "status": {"privacyStatus": yt["privacy"],
                   "selfDeclaredMadeForKids": yt["made_for_kids"],
                   "containsSyntheticMedia": True},
    }
    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    req = _service().videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]
