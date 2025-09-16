from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from pathlib import Path
import os

# Usa las variables de entorno de Render
CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)',
        pageSize=10
    ).execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]
    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()
    return folder.get('id')

def upload_to_drive(file_path: Path, empresa: str, cedula: str, tipo: str = "INCAPACIDADES"):
    service = get_drive_service()
    # 1. Carpeta raíz por tipo
    root_folder_id = get_or_create_folder(service, tipo.upper().strip())
    # 2. Subcarpeta por empresa
    empresa_folder_id = get_or_create_folder(service, empresa.upper().strip(), root_folder_id)
    # 3. Sube archivo
    file_metadata = {
        'name': f"{cedula}_{file_path.name}",
        'parents': [empresa_folder_id]
    }
    media = MediaFileUpload(str(file_path), resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='webViewLink'
    ).execute()
    return uploaded.get('webViewLink')