import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pathlib import Path
from datetime import datetime

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

def get_quinzena_folder_name():
    """Determina el nombre de la carpeta de quincena actual"""
    today = datetime.now()
    mes = today.strftime("%B")  # Nombre del mes en inglés
    
    # Traducir mes al español
    meses_es = {
        'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo',
        'April': 'Abril', 'May': 'Mayo', 'June': 'Junio',
        'July': 'Julio', 'August': 'Agosto', 'September': 'Septiembre',
        'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
    }
    mes_es = meses_es.get(mes, mes)
    
    if today.day <= 15:
        return f"Primera_Quincena_{mes_es}"
    else:
        return f"Segunda_Quincena_{mes_es}"

def normalize_tipo_incapacidad(tipo: str) -> str:
    """Normaliza el tipo de incapacidad al formato de carpeta"""
    tipo_map = {
        'maternidad': 'Maternidad',
        'paternidad': 'Paternidad',
        'enfermedad general': 'Enfermedad_General',
        'enfermedad_general': 'Enfermedad_General',
        'general': 'Enfermedad_General',
        'accidente laboral': 'Accidente_Laboral',
        'accidente_laboral': 'Accidente_Laboral',
        'labor': 'Accidente_Laboral',
        'accidente de tránsito': 'Accidente_Transito',
        'accidente_transito': 'Accidente_Transito',
        'accidente de transito': 'Accidente_Transito',
        'traffic': 'Accidente_Transito'
    }
    return tipo_map.get(tipo.lower(), tipo.replace(' ', '_').title())

def upload_to_drive(
    file_path: Path, 
    empresa: str, 
    cedula: str, 
    tipo: str, 
    consecutivo: str = None,
    tiene_soat: bool = None,
    tiene_licencia: bool = None
) -> str:
    """
    Sube un archivo a Google Drive con la nueva estructura de carpetas
    
    Estructura:
    Incapacidades/
    └── {Empresa}/
        └── {Año}/
            └── {Quincena}/
                ├── Maternidad/
                ├── Paternidad/
                │   ├── Con_Licencia/
                │   └── Sin_Licencia/
                ├── Enfermedad_General/
                ├── Accidente_Laboral/
                └── Accidente_Transito/
                    ├── Con_SOAT/
                    └── Sin_SOAT/
    
    Args:
        file_path: Ruta del archivo a subir
        empresa: Nombre de la empresa
        cedula: Cédula del empleado
        tipo: Tipo de incapacidad
        consecutivo: Consecutivo único (opcional)
        tiene_soat: Booleano para Accidente de Tránsito (opcional)
        tiene_licencia: Booleano para Paternidad (opcional)
        
    Returns:
        URL pública del archivo subido
    """
    try:
        service = get_authenticated_service()
        
        # Obtener fecha y año actual
        año_actual = str(datetime.now().year)
        fecha = datetime.now().strftime("%Y%m%d")
        
        # 1. Carpeta principal "Incapacidades"
        main_folder_id = create_folder_if_not_exists(service, "Incapacidades")
        
        # 2. Carpeta de empresa
        empresa_folder_id = create_folder_if_not_exists(service, empresa, main_folder_id)
        
        # 3. Carpeta del año
        year_folder_id = create_folder_if_not_exists(service, año_actual, empresa_folder_id)
        
        # 4. Carpeta de quincena
        quinzena_folder_name = get_quinzena_folder_name()
        quinzena_folder_id = create_folder_if_not_exists(service, quinzena_folder_name, year_folder_id)
        
        # 5. Carpeta de tipo de incapacidad
        tipo_normalizado = normalize_tipo_incapacidad(tipo)
        tipo_folder_id = create_folder_if_not_exists(service, tipo_normalizado, quinzena_folder_id)
        
        # 6. Subcarpetas especiales según el tipo
        final_folder_id = tipo_folder_id
        
        if tipo_normalizado == 'Accidente_Transito':
            if tiene_soat is not None:
                subfolder_name = 'Con_SOAT' if tiene_soat else 'Sin_SOAT'
                final_folder_id = create_folder_if_not_exists(service, subfolder_name, tipo_folder_id)
        
        elif tipo_normalizado == 'Paternidad':
            if tiene_licencia is not None:
                subfolder_name = 'Con_Licencia' if tiene_licencia else 'Sin_Licencia'
                final_folder_id = create_folder_if_not_exists(service, subfolder_name, tipo_folder_id)
        
        # 7. Nombre del archivo con formato: CONSECUTIVO_CEDULA_TIPO_FECHA.pdf
        if consecutivo:
            filename = f"{consecutivo}_{cedula}_{tipo_normalizado}_{fecha}.pdf"
        else:
            filename = f"{cedula}_{tipo_normalizado}_{fecha}.pdf"
        
        # 8. Metadatos del archivo
        file_metadata = {
            'name': filename,
            'parents': [final_folder_id],
            'description': f'Incapacidad {tipo} - Cédula: {cedula} - Empresa: {empresa}'
        }
        
        # 9. Subir archivo
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
        
        # 10. Hacer público el archivo (opcional)
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
        except Exception as perm_error:
            print(f"Advertencia: No se pudo hacer público el archivo: {perm_error}")
        
        # 11. Retornar URL para visualizar
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