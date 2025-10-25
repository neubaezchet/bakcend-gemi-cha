"""
Google Drive Upload con Cache, Thread-Safety y Auto-Recuperación
IncaNeurobaeza - 2024
"""

import os
import json
import time
import datetime
import threading
import functools
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Variables de entorno
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

# Archivo de cache del token (Render usa /tmp)
TOKEN_FILE = Path("/tmp/google_token.json")

# ==================== CACHE Y LOCKS ====================

# Cache global del servicio de Drive
_service_cache = None
_service_cache_lock = threading.Lock()

# Lock para renovación de credenciales (evita renovaciones simultáneas)
_creds_lock = threading.Lock()

# Contador de errores para auto-recuperación
_error_count = 0
_max_errors_before_clear = 3

# ==================== FUNCIONES DE CACHE ====================

def clear_service_cache():
    """Limpia el cache del servicio (útil cuando hay errores)"""
    global _service_cache, _error_count
    with _service_cache_lock:
        _service_cache = None
        _error_count = 0
    print("🧹 Cache del servicio limpiado")

def clear_token_cache():
    """Elimina el archivo de cache del token"""
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            print("🧹 Token cache eliminado")
    except Exception as e:
        print(f"⚠️ Error eliminando token cache: {e}")

# ==================== DECORADOR DE RETRY ====================

def retry_on_error(max_retries=3, delay=2):
    """Decorator para reintentar automáticamente en caso de error"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e).lower()
                    
                    print(f"⚠️ Error en {func.__name__} (intento {attempt+1}/{max_retries}): {e}")
                    
                    # Si es error de autenticación, limpiar cache
                    if any(x in error_str for x in ['unauthorized', 'invalid', 'expired', 'invalid_grant']):
                        print("🔄 Error de autenticación detectado, limpiando cache...")
                        clear_service_cache()
                        clear_token_cache()
                        
                        if attempt < max_retries - 1:
                            wait_time = delay * (2 ** attempt)  # Backoff exponencial
                            print(f"⏳ Esperando {wait_time}s antes de reintentar...")
                            time.sleep(wait_time)
                            continue
                    
                    # Si no es error de auth, no reintentar
                    raise
            
            raise last_exception
        return wrapper
    return decorator

# ==================== RENOVACIÓN DE CREDENCIALES ====================

def _get_or_refresh_credentials():
    """
    Obtiene o renueva las credenciales de Google Drive
    - Thread-safe (usa lock)
    - Renovación preventiva (5 minutos antes)
    - Auto-recuperación en caso de error
    """
    
    with _creds_lock:  # ← EVITA RENOVACIONES SIMULTÁNEAS
        creds = None
        
        # Validar que tenemos las credenciales necesarias
        if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
            raise ValueError(
                "❌ Faltan credenciales de Google Drive:\n"
                f"  CLIENT_ID: {'✅' if CLIENT_ID else '❌'}\n"
                f"  CLIENT_SECRET: {'✅' if CLIENT_SECRET else '❌'}\n"
                f"  REFRESH_TOKEN: {'✅' if REFRESH_TOKEN else '❌'}\n"
                "Configura estas variables en Render Dashboard → Environment"
            )
        
        # PASO 1: Intentar cargar token existente del cache
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, 'r') as token:
                    token_data = json.load(token)
                    creds = Credentials.from_authorized_user_info(
                        token_data, 
                        scopes=["https://www.googleapis.com/auth/drive.file"]
                    )
                    
                    # Verificar si el token necesita renovación
                    if creds.expiry:
                        now = datetime.datetime.utcnow()
                        time_until_expiry = (creds.expiry - now).total_seconds()
                        minutes_left = time_until_expiry / 60
                        
                        # Renovar si expira en menos de 5 minutos o ya expiró
                        if time_until_expiry < 300 or not creds.valid:
                            if minutes_left < 0:
                                print(f"⚠️ Token EXPIRADO hace {abs(minutes_left):.1f} minutos")
                            else:
                                print(f"⏰ Token expira en {minutes_left:.1f} min, renovando preventivamente...")
                            creds = None  # Forzar renovación
                        else:
                            print(f"✅ Token válido por {minutes_left:.1f} minutos más")
                            return creds  # Token válido, retornar
            except Exception as e:
                print(f"⚠️ Error cargando token del cache: {e}")
                creds = None
        
        # PASO 2: Si no hay creds válidas, renovar
        if not creds:
            print("🔄 Renovando access_token con refresh_token...")
            
            # Intentar renovar con refresh_token existente
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    print("✅ Token renovado exitosamente (desde creds expiradas)")
                except Exception as e:
                    error_str = str(e)
                    if 'invalid_grant' in error_str.lower():
                        raise Exception(
                            "❌ ERROR CRÍTICO: El REFRESH_TOKEN ha sido revocado.\n\n"
                            "SOLUCIÓN:\n"
                            "1. Ejecuta localmente: python regenerar_token.py\n"
                            "2. Copia el nuevo REFRESH_TOKEN\n"
                            "3. Actualízalo en Render Dashboard → Environment\n"
                            "4. Guarda cambios y espera 1-2 minutos\n\n"
                            f"Detalles técnicos: {error_str}"
                        )
                    raise Exception(f"Error renovando token: {error_str}")
            else:
                # Crear credenciales desde cero usando REFRESH_TOKEN
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
                    print("✅ Token generado exitosamente desde REFRESH_TOKEN")
                except Exception as e:
                    error_str = str(e)
                    if 'invalid_grant' in error_str.lower():
                        raise Exception(
                            "❌ ERROR CRÍTICO: El REFRESH_TOKEN es inválido o ha sido revocado.\n\n"
                            "SOLUCIÓN:\n"
                            "1. Verifica que GOOGLE_REFRESH_TOKEN esté correctamente copiado en Render\n"
                            "2. Si persiste, ejecuta: python regenerar_token.py\n"
                            "3. Actualiza el nuevo token en Render Dashboard → Environment\n\n"
                            f"Detalles técnicos: {error_str}"
                        )
                    raise Exception(f"Error creando credenciales: {error_str}")
            
            # PASO 3: Guardar token renovado en cache
            try:
                token_data = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes,
                    'expiry': creds.expiry.isoformat() if creds.expiry else None
                }
                with open(TOKEN_FILE, 'w') as token:
                    json.dump(token_data, token)
                print("💾 Token renovado guardado en cache")
            except Exception as e:
                print(f"⚠️ No se pudo guardar token en cache: {e}")
                # No es crítico, podemos continuar
        
        return creds

# ==================== SERVICIO DE DRIVE ====================

@retry_on_error(max_retries=3, delay=2)
def get_authenticated_service():
    """
    Obtiene el servicio autenticado de Google Drive
    - Con cache para reutilizar servicio
    - Con retry automático en caso de error
    - Thread-safe
    """
    global _service_cache, _error_count
    
    # PASO 1: Si ya tenemos el servicio en cache, verificar si sigue válido
    with _service_cache_lock:
        if _service_cache is not None:
            try:
                # Test rápido: listar 1 archivo para verificar conexión
                _service_cache.files().list(pageSize=1, fields="files(id)").execute()
                _error_count = 0  # Reset contador de errores
                return _service_cache
            except Exception as e:
                print(f"⚠️ Servicio en cache inválido: {e}")
                _service_cache = None
                _error_count += 1
                
                # Si hay muchos errores consecutivos, limpiar todo
                if _error_count >= _max_errors_before_clear:
                    print(f"⚠️ {_error_count} errores consecutivos, limpiando cache completo...")
                    clear_token_cache()
                    _error_count = 0
    
    # PASO 2: Necesitamos crear/renovar el servicio
    print("🔧 Creando nuevo servicio de Google Drive...")
    creds = _get_or_refresh_credentials()
    
    try:
        service = build('drive', 'v3', credentials=creds)
        
        # Verificar que el servicio funciona
        service.files().list(pageSize=1, fields="files(id)").execute()
        print("✅ Servicio de Drive creado y verificado")
        
        # Guardar en cache
        with _service_cache_lock:
            _service_cache = service
            _error_count = 0
        
        return service
    except Exception as e:
        print(f"❌ Error creando servicio de Drive: {e}")
        raise

# ==================== FUNCIONES DE UTILIDAD ====================

def create_folder_if_not_exists(service, folder_name, parent_folder_id='root'):
    """Crea una carpeta en Drive si no existe"""
    folder_name_bytes = folder_name if isinstance(folder_name, bytes) else folder_name.encode()
    parent_id = parent_folder_id if isinstance(parent_folder_id, str) else parent_folder_id.decode()
    
    # Buscar carpeta existente
    query = f"name='{folder_name_bytes.decode()}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    folders = results.get('files', [])
    
    if folders:
        print(f"📁 Carpeta '{folder_name_bytes.decode()}' ya existe (ID: {folders[0]['id']})")
        return folders[0]['id']
    
    # Crear carpeta
    folder_metadata = {
        'name': folder_name_bytes.decode(),
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    print(f"✅ Carpeta '{folder_name_bytes.decode()}' creada (ID: {folder.get('id')})")
    return folder.get('id')

def get_quinzena_folder_name():
    """Determina el nombre de la carpeta de quincena actual"""
    from datetime import datetime
    import calendar
    
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
    tipo_a_usar = subtipo if subtipo else tipo
    
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

# ==================== FUNCIÓN PRINCIPAL DE UPLOAD ====================

@retry_on_error(max_retries=3, delay=2)
def upload_to_drive(
    file_path: Path, 
    empresa: str, 
    cedula: str, 
    tipo: str, 
    consecutivo: str = None,
    tiene_soat: bool = None,
    tiene_licencia: bool = None,
    subtipo: str = None
) -> str:
    """
    Sube archivo a Google Drive con estructura de carpetas
    - Con retry automático
    - Con auto-recuperación de errores
    """
    from datetime import datetime
    
    try:
        service = get_authenticated_service()
        
        año_actual = str(datetime.now().year)
        fecha = datetime.now().strftime("%Y%m%d")
        
        # Crear estructura de carpetas
        print(f"📁 Creando estructura de carpetas en Drive...")
        main_folder_id = create_folder_if_not_exists(service, b"Incapacidades", 'root')
        empresa_folder_id = create_folder_if_not_exists(service, empresa.encode() if isinstance(empresa, str) else empresa, main_folder_id)
        year_folder_id = create_folder_if_not_exists(service, año_actual.encode(), empresa_folder_id)
        
        quinzena_nombre = get_quinzena_folder_name()
        quinzena_folder_id = create_folder_if_not_exists(service, quinzena_nombre.encode(), year_folder_id)
        
        tipo_normalizado = normalize_tipo_incapacidad(tipo, subtipo)
        tipo_folder_id = create_folder_if_not_exists(service, tipo_normalizado.encode(), quinzena_folder_id)
        
        final_folder_id = tipo_folder_id
        
        # Subcarpetas especiales
        if tipo_normalizado == 'Accidente_Transito' and tiene_soat is not None:
            subfolder_name = 'Con_SOAT' if tiene_soat else 'Sin_SOAT'
            final_folder_id = create_folder_if_not_exists(service, subfolder_name.encode(), tipo_folder_id)
        
        elif tipo_normalizado == 'Paternidad' and tiene_licencia is not None:
            subfolder_name = 'Con_Licencia' if tiene_licencia else 'Sin_Licencia'
            final_folder_id = create_folder_if_not_exists(service, subfolder_name.encode(), tipo_folder_id)
        
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
        main_folder_id = create_folder_if_not_exists(service, b"Incapacidades", 'root')
        empresa_folder_id = create_folder_if_not_exists(service, empresa.encode() if isinstance(empresa, str) else empresa, main_folder_id)
        return f"https://drive.google.com/drive/folders/{empresa_folder_id}"
    except Exception as e:
        return f"Error: {str(e)}"