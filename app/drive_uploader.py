import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pathlib import Path
from datetime import datetime
import json

# Variables de entorno necesarias
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

# ✅ Archivo para guardar el token renovado (Render usa /tmp)
TOKEN_FILE = Path("/tmp/google_token.json")

def get_authenticated_service():
    """Crea el servicio autenticado de Google Drive con auto-renovación"""
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        error_msg = "❌ Faltan credenciales de Google Drive:\n"
        if not CLIENT_ID: error_msg += "  - GOOGLE_CLIENT_ID\n"
        if not CLIENT_SECRET: error_msg += "  - GOOGLE_CLIENT_SECRET\n"
        if not REFRESH_TOKEN: error_msg += "  - GOOGLE_REFRESH_TOKEN\n"
        raise ValueError(error_msg)
    
    creds = None
    
    # PASO 1: Intentar cargar token existente
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes=[
                    "https://www.googleapis.com/auth/drive.file"
                ])
                print("✅ Token cargado desde caché")
        except Exception as e:
            print(f"⚠️ Error cargando token: {e}")
            creds = None
    
    # PASO 2: Si no hay token o está inválido, renovarlo
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Renovando token expirado...")
            try:
                creds.refresh(Request())
            except Exception as e:
                error_str = str(e)
                if 'invalid_grant' in error_str:
                    raise Exception(
                        "❌ ERROR CRÍTICO: El GOOGLE_REFRESH_TOKEN ha expirado o fue revocado.\n\n"
                        "SOLUCIÓN:\n"
                        "1. Ejecuta el script 'regenerar_token.py' localmente\n"
                        "2. Copia el nuevo GOOGLE_REFRESH_TOKEN\n"
                        "3. Actualízalo en Render Dashboard → Environment\n\n"
                        f"Detalles técnicos: {error_str}"
                    )
                else:
                    raise Exception(f"Error renovando token: {error_str}")
        else:
            print("🆕 Creando credenciales desde refresh_token...")
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=["https://www.googleapis.com/auth/drive.file"]
                )
                creds.refresh(Request())
            except Exception as e:
                error_str = str(e)
                if 'invalid_grant' in error_str:
                    raise Exception(
                        "❌ ERROR CRÍTICO: El GOOGLE_REFRESH_TOKEN es inválido.\n\n"
                        "SOLUCIÓN:\n"
                        "1. Verifica que GOOGLE_REFRESH_TOKEN esté correctamente copiado\n"
                        "2. Si persiste, genera uno nuevo con 'regenerar_token.py'\n\n"
                        f"Detalles técnicos: {error_str}"
                    )
                else:
                    raise Exception(f"Error creando credenciales: {error_str}")
        
        # PASO 3: Guardar token renovado
        try:
            token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            with open(TOKEN_FILE, 'w') as token:
                json.dump(token_data, token)
            print("✅ Token renovado guardado")
        except Exception as e:
            print(f"⚠️ No se pudo guardar token: {e}")
    
    try:
        service = build('drive', 'v3', credentials=creds)
        # Verificar que el servicio funciona
        service.files().list(pageSize=1).execute()
        print("✅ Conexión a Google Drive exitosa")
        return service
    except Exception as e:
        raise Exception(f"Error construyendo servicio de Drive: {str(e)}")

def create_folder_if_not_exists(service, folder_name, parent_folder_id='root'):
    """Crea una carpeta en Drive si no existe"""
    # ✅ CRÍTICO: Buscar en el parent correcto, no en toda la unidad
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    folders = results.get('files', [])
    
    if folders:
        print(f"📁 Carpeta '{folder_name}' ya existe (ID: {folders[0]['id']})")
        return folders[0]['id']
    
    # Si no existe, crearla
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    print(f"✅ Carpeta '{folder_name}' creada (ID: {folder.get('id')})")
    return folder.get('id')

def get_quinzena_folder_name():
    """Determina el nombre de la carpeta de quincena actual"""
    today = datetime.now()
    mes = today.strftime("%B")
    
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

def normalize_tipo_incapacidad(tipo: str, subtipo: str = None) -> str:
    """Normaliza el tipo de incapacidad al formato de carpeta"""
    # ✅ NUEVO: Si subtipo existe, usarlo para especificar mejor
    if subtipo:
        tipo_a_usar = subtipo
    else:
        tipo_a_usar = tipo
    
    tipo_map = {
        'maternidad': 'Maternidad',
        'maternity': 'Maternidad',
        'paternidad': 'Paternidad',
        'paternity': 'Paternidad',
        'enfermedad general': 'Enfermedad_General',
        'enfermedad_general': 'Enfermedad_General',
        'general': 'Enfermedad_General',
        'accidente laboral': 'Accidente_Laboral',
        'accidente_laboral': 'Accidente_Laboral',
        'labor': 'Accidente_Laboral',
        'accidente de tránsito': 'Accidente_Transito',
        'accidente_transito': 'Accidente_Transito',
        'accidente de transito': 'Accidente_Transito',
        'traffic': 'Accidente_Transito',
        'especial': 'Enfermedad_Especial'
    }
    return tipo_map.get(tipo_a_usar.lower(), tipo_a_usar.replace(' ', '_').title())

def upload_to_drive(
    file_path: Path, 
    empresa: str, 
    cedula: str, 
    tipo: str, 
    consecutivo: str = None,
    tiene_soat: bool = None,
    tiene_licencia: bool = None,
    subtipo: str = None  # ✅ NUEVO: Para especificar mejor el tipo
) -> str:
    """
    Sube archivo a Google Drive con estructura de carpetas COMPLETA
    
    Estructura:
    Incapacidades/
    └── {Empresa}/
        └── {Año}/
            └── {Quincena}/
                ├── Maternidad/
                ├── Paternidad/
                │   ├── Con_Licencia/
                │   └── Sin_Licencia/
                └── Accidente_Transito/
                    ├── Con_SOAT/
                    └── Sin_SOAT/
    """
    try:
        service = get_authenticated_service()
        
        año_actual = str(datetime.now().year)
        fecha = datetime.now().strftime("%Y%m%d")
        
        # ✅ CRÍTICO: Crear estructura desde "root" (Mi unidad)
        # Paso 1: Crear/encontrar carpeta "Incapacidades" en Mi unidad
        print("📁 Buscando/creando carpeta 'Incapacidades' en Mi unidad...")
        main_folder_id = create_folder_if_not_exists(service, "Incapacidades", parent_folder_id='root')
        
        # Paso 2: Crear/encontrar carpeta de empresa
        print(f"📁 Buscando/creando carpeta '{empresa}'...")
        empresa_folder_id = create_folder_if_not_exists(service, empresa, main_folder_id)
        
        # Paso 3: Crear/encontrar carpeta del año
        print(f"📁 Buscando/creando carpeta '{año_actual}'...")
        year_folder_id = create_folder_if_not_exists(service, año_actual, empresa_folder_id)
        
        # Paso 4: Crear/encontrar carpeta de quincena
        quinzena_nombre = get_quinzena_folder_name()
        print(f"📁 Buscando/creando carpeta '{quinzena_nombre}'...")
        quinzena_folder_id = create_folder_if_not_exists(service, quinzena_nombre, year_folder_id)
        
        # Paso 5: Crear/encontrar carpeta del tipo de incapacidad
        tipo_normalizado = normalize_tipo_incapacidad(tipo, subtipo)
        print(f"📁 Buscando/creando carpeta '{tipo_normalizado}'...")
        tipo_folder_id = create_folder_if_not_exists(service, tipo_normalizado, quinzena_folder_id)
        
        final_folder_id = tipo_folder_id
        
        # ✅ Subcarpetas especiales
        if tipo_normalizado == 'Accidente_Transito' and tiene_soat is not None:
            subfolder_name = 'Con_SOAT' if tiene_soat else 'Sin_SOAT'
            print(f"📁 Buscando/creando subcarpeta '{subfolder_name}'...")
            final_folder_id = create_folder_if_not_exists(service, subfolder_name, tipo_folder_id)
        
        elif tipo_normalizado == 'Paternidad' and tiene_licencia is not None:
            subfolder_name = 'Con_Licencia' if tiene_licencia else 'Sin_Licencia'
            print(f"📁 Buscando/creando subcarpeta '{subfolder_name}'...")
            final_folder_id = create_folder_if_not_exists(service, subfolder_name, tipo_folder_id)
        
        # Nombre del archivo
        if consecutivo:
            filename = f"{consecutivo}_{cedula}_{tipo_normalizado}_{fecha}.pdf"
        else:
            filename = f"{cedula}_{tipo_normalizado}_{fecha}.pdf"
        
        print(f"📤 Subiendo archivo: {filename}")
        
        file_metadata = {
            'name': filename,
            'parents': [final_folder_id],
            'description': f'Incapacidad {tipo} - Cédula: {cedula} - Empresa: {empresa}'
        }
        
        media = MediaFileUpload(str(file_path), mimetype='application/pdf', resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink,webContentLink'
        ).execute()
        
        # Hacer público
        try:
            service.permissions().create(
                fileId=file.get('id'),
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
        except Exception as e:
            print(f"⚠️ No se pudo hacer público: {e}")
        
        link = file.get('webViewLink', f"https://drive.google.com/file/d/{file.get('id')}/view")
        print(f"✅ Archivo subido exitosamente")
        print(f"🔗 Link: {link}")
        return link
        
    except Exception as e:
        error_msg = f"Error subiendo archivo a Drive: {str(e)}"
        print(f"❌ {error_msg}")
        raise Exception(error_msg)

def get_folder_link(empresa: str) -> str:
    """Obtiene el link de la carpeta de una empresa"""
    try:
        service = get_authenticated_service()
        main_folder_id = create_folder_if_not_exists(service, "Incapacidades")
        empresa_folder_id = create_folder_if_not_exists(service, empresa, main_folder_id)
        return f"https://drive.google.com/drive/folders/{empresa_folder_id}"
    except Exception as e:
        return f"Error: {str(e)}"