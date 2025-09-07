from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SERVICE_ACCOUNT_FILE = Path("incapacidades-sa.json")  # ← tu archivo
SCOPES = ["https://www.googleapis.com/auth/drive"]
BASE_FOLDER_NAME = "INCAPACIDADES"

def get_service():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def get_or_create_folder(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    res = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    if res["files"]:
        return res["files"][0]["id"]
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]

def get_subfolder(service, empresa: str, tipo: str) -> str:
    base_id = get_or_create_folder(service, BASE_FOLDER_NAME)
    emp_id  = get_or_create_folder(service, empresa, base_id)
    mapping = {
        "maternity": "LICENCIA_MATERNIDAD",
        "paternity": "PATERNIDAD",
        "general":   "GENERAL",
        "labor":     "ACCIDENTE_TRABAJO",
        "traffic":   "ACCIDENTE_TRANSITO",
    }
    sub_name = mapping.get(tipo, "OTROS")
    return get_or_create_folder(service, sub_name, emp_id)

def upload_to_drive(file_path: Path, empresa: str, cedula: str, tipo: str) -> str:
    service = get_service()
    parent_id = get_subfolder(service, empresa.strip().upper(), tipo)
    file_metadata = {"name": f"{cedula}_{file_path.name}", "parents": [parent_id]}
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="webViewLink").execute()
    return file.get("webViewLink")