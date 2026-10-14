import os
import json
import time
import random
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DEFAULT_PARENT_FOLDER_ID = "1YRth9_SQka7Mpg07GkggANXb9-ed_CkU"

SUBFOLDERS = [
    "01_Summary_Excel_Results",
    "02_Flux_Data",
    "03_Simulation_Outputs",
    "04_Input_Decks",
    "05_Execution_Logs_and_Benchmarks"
]

def api_call_with_retry(call_fn, max_retries=6, initial_delay=3.0):
    """Goi Drive API voi exponential backoff va randomized jitter chong 403 Rate Limit."""
    for attempt in range(1, max_retries + 1):
        try:
            return call_fn()
        except Exception as e:
            err_str = str(e).lower()
            if "ratelimitexceeded" in err_str or "403" in err_str or "quota" in err_str or "429" in err_str or "503" in err_str:
                wait_time = (initial_delay * (2 ** (attempt - 1))) + random.uniform(1.0, 5.0)
                print(f">>> [DRIVE RATE LIMIT] Lan {attempt}/{max_retries}, cho {wait_time:.1f}s truoc khi thu lai...")
                time.sleep(wait_time)
            else:
                if attempt == max_retries:
                    raise e
                time.sleep(2.0 + random.uniform(0.5, 2.0))
    return None

def get_drive_service(oauth_json_str_or_path: str = None):
    """Khoi tao Google Drive API service tu JSON string hoac file path."""
    if oauth_json_str_or_path is None:
        oauth_json_str_or_path = os.environ.get("GDRIVE_OAUTH_JSON")
        if not oauth_json_str_or_path:
            local_default = r"C:\antigravity_goat\user_oauth_creds.json"
            if os.path.exists(local_default):
                oauth_json_str_or_path = local_default

    if not oauth_json_str_or_path:
        raise ValueError("Khong tim thay thong tin xac thuc GDRIVE_OAUTH_JSON.")

    if os.path.exists(oauth_json_str_or_path):
        creds = Credentials.from_authorized_user_file(oauth_json_str_or_path)
    else:
        info = json.loads(oauth_json_str_or_path)
        creds = Credentials.from_authorized_user_info(info)

    return build("drive", "v3", credentials=creds)

def get_or_create_subfolders(service, parent_id: str = None):
    parent_id = parent_id or os.environ.get("GDRIVE_FOLDER_ID") or DEFAULT_PARENT_FOLDER_ID
    q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    existing_res = api_call_with_retry(lambda: service.files().list(q=q, supportsAllDrives=True, includeItemsFromAllDrives=True, fields="files(id, name)").execute())
    existing = existing_res.get("files", []) if existing_res else []
    existing_map = {f["name"]: f["id"] for f in existing}

    folder_ids = {}
    for sf in SUBFOLDERS:
        if sf in existing_map:
            folder_ids[sf] = existing_map[sf]
        else:
            meta = {
                "name": sf,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]
            }
            created = api_call_with_retry(lambda: service.files().create(body=meta, supportsAllDrives=True, fields="id, name").execute())
            if created:
                folder_ids[sf] = created["id"]
    return folder_ids

def upload_file_to_folder(service, local_path: str, target_folder_id: str, target_name: str = None, max_retries: int = 5):
    """Upload hoac cap nhat file truc tiep bang update (khong delete de tiet kiem quota)."""
    p = Path(local_path)
    if not p.exists():
        print(f"Bo qua upload: {local_path} khong ton tai")
        return None
    name = target_name or p.name

    for attempt in range(1, max_retries + 1):
        try:
            # Kiem tra file da ton tai chua
            q = f"'{target_folder_id}' in parents and name = '{name}' and trashed = false"
            res = service.files().list(q=q, supportsAllDrives=True, includeItemsFromAllDrives=True, fields="files(id)").execute()
            old_files = res.get("files", [])

            media = MediaFileUpload(str(p), resumable=True)
            if old_files:
                # Cap nhat truc tiep file hien tai
                file_id = old_files[0]["id"]
                updated = service.files().update(fileId=file_id, media_body=media, supportsAllDrives=True, fields="id, name, webViewLink").execute()
                return updated
            else:
                # Tao file moi
                meta = {
                    "name": name,
                    "parents": [target_folder_id]
                }
                created = service.files().create(body=meta, media_body=media, supportsAllDrives=True, fields="id, name, webViewLink").execute()
                return created
        except Exception as e:
            err_str = str(e).lower()
            if "ratelimitexceeded" in err_str or "403" in err_str or "quota" in err_str or "429" in err_str or "503" in err_str:
                wait_time = (3.0 * (2 ** (attempt - 1))) + random.uniform(1.0, 5.0)
                print(f"Canh bao upload {name} (lan {attempt}/{max_retries}) gap rate limit, cho {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                print(f"Canh bao upload {name} (lan {attempt}/{max_retries}): {e}")
                time.sleep(2.0 * attempt)
    print(f"Khong the upload {name} sau {max_retries} lan thu, giu lai local.")
    return None

def get_completed_jobs_from_drive(service, flux_folder_id: str, target_filename: str = None) -> set:
    """Quet file flux de lay danh sach job da chay xong. Neu co target_filename chi kiem tra dung file do."""
    completed = set()
    try:
        if target_filename:
            q = f"'{flux_folder_id}' in parents and name = '{target_filename}' and trashed = false"
        else:
            q = f"'{flux_folder_id}' in parents and name contains 'flux_runner_' and trashed = false"

        res = api_call_with_retry(lambda: service.files().list(q=q, fields="files(id, name)").execute())
        files = res.get("files", []) if res else []

        for f in files:
            if f["name"].endswith(".csv"):
                try:
                    content_bytes = api_call_with_retry(lambda: service.files().get_media(fileId=f["id"]).execute())
                    if content_bytes:
                        content = content_bytes.decode("utf-8", errors="ignore")
                        for line in content.splitlines()[1:]:
                            parts = line.strip().split(",")
                            if parts and parts[0]:
                                completed.add(parts[0])
                except Exception as e:
                    print(f"Loi khi doc {f['name']} tu Drive: {e}")
    except Exception as e:
        print(f"Loi khi quet completed jobs tu Drive: {e}")

    return completed
