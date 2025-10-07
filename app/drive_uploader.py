import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pathlib import Path

# Variables de entorno necesarias
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

def get_authenticated_service():
    """Crea el servicio autenticado de Google Drive"""
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        raise ValueError("Faltan credenciales de Google. Verifica las variables de entorno.")
    
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    
    # Renovar el token si es necesario
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    
    return build('drive', 'v3', credentials=creds)

def create_folder_if_not_exists(service, folder_name, parent_folder_id='root'):
    """Crea una carpeta en Drive si no existe"""
    # Buscar si ya existe la carpeta
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and parents in '{parent_folder_id}'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get('files', [])
    
    if folders:
        return folders[0]['id']
    
    # Crear carpeta si no existe
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def upload_to_drive(file_path: Path, empresa: str, cedula: str, tipo: str, consecutivo: str = None) -> str:
    """
    Sube un archivo a Google Drive organizándolo por empresa
    
    Args:
        file_path: Ruta del archivo a subir
        empresa: Nombre de la empresa
        cedula: Cédula del empleado
        tipo: Tipo de incapacidad
        consecutivo: Consecutivo único (opcional)
        
    Returns:
        URL pública del archivo subido
    """
    try:
        service = get_authenticated_service()
        
        # Crear estructura de carpetas: Incapacidades / {Empresa} / {Año}
        from datetime import datetime
        año_actual = str(datetime.now().year)
        
        # Carpeta principal "Incapacidades"
        main_folder_id = create_folder_if_not_exists(service, "Incapacidades")
        
        # Carpeta de empresa dentro de "Incapacidades"
        empresa_folder_id = create_folder_if_not_exists(service, empresa, main_folder_id)
        
        # Carpeta del año dentro de la empresa
        year_folder_id = create_folder_if_not_exists(service, año_actual, empresa_folder_id)
        
        # Nombre del archivo con formato: CONSECUTIVO_CEDULA_TIPO_FECHA.pdf
        fecha = datetime.now().strftime("%Y%m%d")
        if consecutivo:
            filename = f"{consecutivo}_{cedula}_{tipo}_{fecha}.pdf"
        else:
            filename = f"{cedula}_{tipo}_{fecha}.pdf"
        
        # Metadatos del archivo
        file_metadata = {
            'name': filename,
            'parents': [year_folder_id],
            'description': f'Incapacidad {tipo} - Cédula: {cedula} - Empresa: {empresa}'
        }
        
        # Subir archivo
        media = MediaFileUpload(
            str(file_path), 
            mimetype='application/pdf',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink,webContentLink'
        ).execute()
        
        # Hacer público el archivo (opcional - comentar si no quieres que sea público)
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
        except Exception as perm_error:
            print(f"Advertencia: No se pudo hacer público el archivo: {perm_error}")
        
        # Retornar URL para visualizar
        return file.get('webViewLink', f"https://drive.google.com/file/d/{file.get('id')}/view")
        
    except Exception as e:
        raise Exception(f"Error subiendo archivo a Drive: {str(e)}")

def get_folder_link(empresa: str) -> str:
    """Obtiene el link de la carpeta de una empresa específica"""
    try:
        service = get_authenticated_service()
        
        # Buscar carpeta principal
        main_folder_id = create_folder_if_not_exists(service, "Incapacidades")
        
        # Buscar carpeta de empresa
        empresa_folder_id = create_folder_if_not_exists(service, empresa, main_folder_id)
        
        return f"https://drive.google.com/drive/folders/{empresa_folder_id}"
        
    except Exception as e:
        return f"Error obteniendo link de carpeta: {str(e)}"