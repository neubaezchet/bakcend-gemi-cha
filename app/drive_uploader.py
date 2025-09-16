from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
from pathlib import Path
from datetime import datetime

# Lista de nombres de meses en español
MESES_ES = [
    "", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
]
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_user_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
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
    service = get_user_service()

    # 1. Carpeta raíz
    root_folder_id = get_or_create_folder(service, tipo.upper().strip())

    # 2. Subcarpeta por empresa
    empresa_folder_id = get_or_create_folder(service, empresa.upper().strip(), root_folder_id)

    # 3. Subcarpeta por mes y año actual
    now = datetime.now()
    nombre_mes_es = MESES_ES[now.month]
    mes_folder_name = f"{tipo.upper().strip()} {nombre_mes_es} {now.year}"
    mes_folder_id = get_or_create_folder(service, mes_folder_name, empresa_folder_id)

    # 4. Sube archivo
    file_metadata = {
        'name': f"{cedula}_{file_path.name}",
        'parents': [mes_folder_id]
    }
    media = MediaFileUpload(str(file_path), resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='webViewLink'
    ).execute()
    return uploaded.get('webViewLink')

# Ejemplo de uso:
if __name__ == "__main__":
    # Cambia estos valores por los datos reales
    path_al_archivo = Path("actividad5 (1).pdf")   # Cambia a la ruta real de tu archivo
    empresa = "MiEmpresa"                         # Cambia por el nombre de la empresa
    cedula = "123456789"                          # Cambia por la cédula del usuario

    link = upload_to_drive(path_al_archivo, empresa, cedula)
    print("Archivo subido. Link de visualización:", link)