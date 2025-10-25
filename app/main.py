from typing import List, Optional
from fastapi import FastAPI, UploadFile, Form, File, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import pandas as pd
import os, uuid
from pathlib import Path
from datetime import datetime, date
import calendar

from app.drive_uploader import upload_to_drive
from app.pdf_merger import merge_pdfs_from_uploads
from app.email_templates import get_confirmation_template, get_alert_template
from app.database import (
    get_db, init_db, Case, CaseDocument, Employee, Company,
    EstadoCaso, EstadoDocumento, TipoIncapacidad
)
from app.validador import router as validador_router
from app.sync_excel import sincronizar_empleado_desde_excel  # ✅ NUEVO
from app.serial_generator import generar_serial_unico  # ✅ NUEVO

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

app = FastAPI(title="IncaNeurobaeza API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(validador_router)

# ==================== HEALTH CHECK DE GOOGLE DRIVE ====================

from fastapi import APIRouter
from app.drive_uploader import (
    get_authenticated_service, 
    clear_service_cache, 
    clear_token_cache,
    TOKEN_FILE
)
import datetime
import json

drive_router = APIRouter(prefix="/drive", tags=["Google Drive"])

@drive_router.get("/health")
async def drive_health_check():
    """
    Verifica el estado de la conexión con Google Drive
    Útil para monitoreo con Uptime Robot, etc.
    """
    try:
        service = get_authenticated_service()
        
        # Test: listar 1 archivo
        service.files().list(pageSize=1, fields="files(id)").execute()
        
        # Obtener info del token
        token_info = None
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    expiry_str = token_data.get('expiry')
                    if expiry_str:
                        expiry = datetime.datetime.fromisoformat(expiry_str)
                        now = datetime.datetime.utcnow()
                        remaining = (expiry - now).total_seconds()
                        token_info = {
                            'expires_in_minutes': round(remaining / 60, 1),
                            'expires_at': expiry_str,
                            'status': 'valid' if remaining > 0 else 'expired'
                        }
            except Exception as e:
                token_info = {'error': str(e)}
        
        return {
            "status": "healthy",
            "service": "connected",
            "token_info": token_info,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }

@drive_router.post("/refresh-cache")
async def refresh_drive_cache():
    """
    Fuerza la renovación del cache del servicio
    Útil si hay problemas y quieres forzar reconexión
    """
    try:
        clear_service_cache()
        service = get_authenticated_service()
        return {
            "status": "ok",
            "message": "Cache renovado exitosamente"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@drive_router.post("/clear-all-cache")
async def clear_all_drive_cache():
    """
    Limpia TODO el cache (servicio + token)
    Útil para debugging o si necesitas forzar re-autenticación completa
    """
    try:
        clear_service_cache()
        clear_token_cache()
        service = get_authenticated_service()
        return {
            "status": "ok",
            "message": "Todo el cache limpiado y servicio recreado"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

# Agregar el router al app
app.include_router(drive_router)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

# ==================== INICIALIZACIÓN ====================

from app.sync_scheduler import iniciar_sincronizacion_automatica

scheduler = None

@app.on_event("startup")
def startup_event():
    global scheduler
    init_db()
    print("🚀 API iniciada")
    try:
        scheduler = iniciar_sincronizacion_automatica()
        print("✅ Sincronización automática activada")
    except Exception as e:
        print(f"⚠️ Error iniciando sync: {e}")

@app.on_event("shutdown")
def shutdown_event():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        print("🛑 Sincronización detenida")

# ==================== UTILIDADES ====================

def get_current_quinzena():
    today = date.today()
    mes_nombre = calendar.month_name[today.month]
    return f"primera quincena de {mes_nombre}" if today.day <= 15 else f"segunda quincena de {mes_nombre}"

def send_html_email(to_email: str, subject: str, html_body: str, text_body: str = None):
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    brevo_from_email = os.environ.get("BREVO_FROM_EMAIL", "notificaciones@smtp-brevo.com")
    reply_to_email = os.environ.get("SMTP_EMAIL", "davidbaezaospino@gmail.com")

    if not brevo_api_key:
        print("Error: Falta BREVO_API_KEY")
        return False, "Falta BREVO_API_KEY"

    try:
        print(f"📧 Enviando correo a {to_email}...")
        
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = brevo_api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        if isinstance(html_body, bytes): html_body = html_body.decode('utf-8')
        if text_body and isinstance(text_body, bytes): text_body = text_body.decode('utf-8')
        
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email}],
            sender={"name": "IncaNeurobaeza", "email": brevo_from_email},
            reply_to={"email": reply_to_email},
            subject=subject,
            html_content=html_body,
            text_content=text_body
        )
        
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Correo enviado (ID: {api_response.message_id})")
        return True, None
        
    except ApiException as e:
        print(f"❌ Error Brevo: {e}")
        return False, str(e)
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, str(e)

def mapear_tipo_incapacidad(tipo_frontend: str) -> TipoIncapacidad:
    tipo_map = {
        'maternity': TipoIncapacidad.MATERNIDAD,
        'paternidad': TipoIncapacidad.PATERNIDAD,
        'paternity': TipoIncapacidad.PATERNIDAD,
        'general': TipoIncapacidad.ENFERMEDAD_GENERAL,
        'labor': TipoIncapacidad.ENFERMEDAD_LABORAL,
        'traffic': TipoIncapacidad.ACCIDENTE_TRANSITO,
        'especial': TipoIncapacidad.ENFERMEDAD_ESPECIAL,
    }
    return tipo_map.get(tipo_frontend.lower(), TipoIncapacidad.ENFERMEDAD_GENERAL)

# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "message": "✅ API IncaNeurobaeza v2.0 - Trabajando para ayudarte",
        "status": "online",
        "cors": "enabled"
    }

@app.get("/empleados/{cedula}")
def obtener_empleado(cedula: str, db: Session = Depends(get_db)):
    """Consulta empleado (con sync instantánea)"""
    
    # PASO 1: Buscar en BD
    empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
    
    if empleado:
        return {
            "nombre": empleado.nombre,
            "empresa": empleado.empresa.nombre if empleado.empresa else "No especificada",
            "correo": empleado.correo,
            "eps": empleado.eps
        }
    
    # PASO 2: Sincronizar desde Excel
    print(f"🔄 Sync instantánea para {cedula}...")
    empleado_sync = sincronizar_empleado_desde_excel(cedula)
    
    if empleado_sync:
        return {
            "nombre": empleado_sync.nombre,
            "empresa": empleado_sync.empresa.nombre if empleado_sync.empresa else "No especificada",
            "correo": empleado_sync.correo,
            "eps": empleado_sync.eps
        }
    
    return JSONResponse(status_code=404, content={"error": "Empleado no encontrado"})

# ==================== CONTINUACIÓN DE main.py ====================

@app.post("/subir-incapacidad/")
async def subir_incapacidad(
    cedula: str = Form(...),
    tipo: str = Form(...),
    email: str = Form(...),
    telefono: str = Form(...),
    archivos: List[UploadFile] = File(...),
    births: Optional[str] = Form(None),
    motherWorks: Optional[str] = Form(None),
    isPhantomVehicle: Optional[str] = Form(None),
    daysOfIncapacity: Optional[str] = Form(None),
    subType: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Endpoint de recepción de incapacidades"""
    
   # ✅ PASO 1: Verificar en BD (búsqueda instantánea)
    empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
    
    # ✅ PASO 2: Si NO está en BD, sincronizar desde Excel
    if not empleado_bd:
        print(f"🔄 Sincronización instantánea para {cedula}...")
        empleado_bd = sincronizar_empleado_desde_excel(cedula)
    
    # ✅ PASO 3: Determinar si el empleado fue encontrado (en BD o Excel)
    if empleado_bd:
        empleado_encontrado = True
    else:
        try:
            if os.path.exists(DATA_PATH):
                df = pd.read_excel(DATA_PATH)
                empleado_encontrado = not df[df["cedula"] == int(cedula)].empty
            else:
                empleado_encontrado = False
        except:
            empleado_encontrado = False
 # ✅ Generar serial único basado en nombre y cédula
    if empleado_bd:
      consecutivo = generar_serial_unico(db, empleado_bd.nombre, cedula)
    else:
      # Si no hay empleado, usar iniciales genéricas
      consecutivo = generar_serial_unico(db, "DESCONOCIDO", cedula)
    
    # Verificar si hay casos bloqueantes
    if empleado_bd:
      caso_bloqueante = db.query(Case).filter(
        Case.employee_id == empleado_bd.id,
        Case.estado.in_([EstadoCaso.INCOMPLETA, EstadoCaso.ILEGIBLE, EstadoCaso.INCOMPLETA_ILEGIBLE]),
        Case.bloquea_nueva == True
      ).first()
      
      if caso_bloqueante:
        return JSONResponse(status_code=409, content={
          "bloqueo": True,
          "serial_pendiente": caso_bloqueante.serial,
          "mensaje": f"Caso pendiente ({caso_bloqueante.serial}) debe completarse primero."
        })
    metadata_form = {}
    tiene_soat = None
    tiene_licencia = None
    
    if births:
        metadata_form['nacidos_vivos'] = births
    
    if tipo.lower() == 'paternidad' and motherWorks is not None:
        tiene_licencia = motherWorks.lower() == 'true'
        metadata_form['madre_trabaja'] = 'Sí' if tiene_licencia else 'No'
    
    if isPhantomVehicle is not None:
        tiene_soat = isPhantomVehicle.lower() != 'true'
        metadata_form['vehiculo_fantasma'] = 'Sí' if isPhantomVehicle.lower() == 'true' else 'No'
        metadata_form['tiene_soat'] = 'Sí' if tiene_soat else 'No'
    
    if daysOfIncapacity:
        metadata_form['dias_incapacidad'] = daysOfIncapacity
    
    if subType:
        metadata_form['subtipo'] = subType
    
    try:
        empresa_destino = empleado_bd.empresa.nombre if empleado_bd else "OTRA_EMPRESA"
        
        pdf_final_path, original_filenames = await merge_pdfs_from_uploads(archivos, cedula, tipo)
        
        link_pdf = upload_to_drive(
            pdf_final_path, 
            empresa_destino, 
            cedula, 
            tipo, 
            consecutivo,
            tiene_soat=tiene_soat,
            tiene_licencia=tiene_licencia
        )
        
        pdf_final_path.unlink()
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error procesando archivos: {e}"})
    
    tipo_bd = mapear_tipo_incapacidad(subType if subType else tipo)
    
    nuevo_caso = Case(
        serial=consecutivo,
        cedula=cedula,
        employee_id=empleado_bd.id if empleado_bd else None,
        company_id=empleado_bd.company_id if empleado_bd else None,
        tipo=tipo_bd,
        subtipo=subType,
        dias_incapacidad=int(daysOfIncapacity) if daysOfIncapacity else None,
        estado=EstadoCaso.NUEVO,
        metadata_form=metadata_form,
        eps=empleado_bd.eps if empleado_bd else None,
        drive_link=link_pdf,
        email_form=email,
        telefono_form=telefono,
        bloquea_nueva=False
    )
    
    db.add(nuevo_caso)
    db.commit()
    db.refresh(nuevo_caso)
    
    print(f"✅ Caso {consecutivo} guardado (ID {nuevo_caso.id}) - Empresa: {empleado_bd.empresa.nombre if empleado_bd and empleado_bd.empresa else 'N/A'}")
    
    quinzena_actual = get_current_quinzena()
    
    if empleado_encontrado and empleado_bd:
        nombre = empleado_bd.nombre
        correo_empleado = empleado_bd.correo
        empresa_reg = empleado_bd.empresa.nombre if empleado_bd.empresa else "No especificada"
        
        html_empleado = get_confirmation_template(
            nombre=nombre,
            consecutivo=consecutivo,
            empresa=empresa_reg,
            quinzena=quinzena_actual,
            link_pdf=link_pdf,
            archivos_nombres=original_filenames,
            email_contacto=email,
            telefono=telefono
        )
        
        text_empleado = f"""Buen día {nombre},
        
Confirmo recibido de la documentación.
Consecutivo: {consecutivo}
Empresa: {empresa_reg}
Link: {link_pdf}

--
IncaNeurobaeza"""
        
        emails_to_send = []
        if correo_empleado:
            emails_to_send.append(correo_empleado)
        if email and email.lower() != correo_empleado.lower():
            emails_to_send.append(email)
        
        for email_dest in emails_to_send:
            send_html_email(
                email_dest, 
                f"Confirmación Recepción - {consecutivo}",
                html_empleado,
                text_empleado
            )
        
        html_supervision = get_alert_template(
            tipo="copia",
            cedula=cedula,
            nombre=nombre,
            consecutivo=consecutivo,
            empresa=empresa_reg,
            link_pdf=link_pdf,
            archivos_nombres=original_filenames,
            email_contacto=email,
            telefono=telefono
        )
        
        send_html_email(
            "xoblaxbaezaospino@gmail.com", 
            f"Copia Registro - {consecutivo} - {empresa_reg}",
            html_supervision
        )
        
        return {
            "status": "ok",
            "mensaje": "Registro exitoso",
            "consecutivo": consecutivo,
            "case_id": nuevo_caso.id,
            "link_pdf": link_pdf,
            "archivos_combinados": len(original_filenames),
            "correos_enviados": emails_to_send
        }
    
    else:
        html_alerta = get_alert_template(
            tipo="alerta",
            cedula=cedula,
            consecutivo=consecutivo,
            email_contacto=email,
            telefono=telefono,
            quinzena=quinzena_actual
        )
        
        html_confirmacion = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1>IncaNeurobaeza</h1>
                <p style="margin: 0; font-style: italic;">"Trabajando para ayudarte"</p>
            </div>
            <div style="padding: 30px 20px;">
                <p>Buen día,</p>
                <p>Confirmo recibido de la documentación. Su solicitud está siendo revisada.</p>
                <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
                    <strong>Consecutivo:</strong> {consecutivo}<br>
                    <strong>Cédula:</strong> {cedula}
                </div>
                <p><strong>Importante:</strong> Su cédula no está en nuestra base de datos. Nos comunicaremos con usted.</p>
            </div>
        </div>
        """
        
        send_html_email(email, f"Confirmación - {consecutivo}", html_confirmacion)
        send_html_email("xoblaxbaezaospino@gmail.com", f"⚠️ ALERTA Cédula no encontrada - {consecutivo}", html_alerta)
        
        return {
            "status": "warning",
            "mensaje": "Cédula no encontrada - Documentación recibida",
            "consecutivo": consecutivo,
            "case_id": nuevo_caso.id,
            "link_pdf": link_pdf,
            "correos_enviados": [email]
        }

@app.post("/admin/migrar-excel")
async def migrar_excel_a_bd(db: Session = Depends(get_db)):
    """Migra empleados desde Excel a BD"""
    
    if not os.path.exists(DATA_PATH):
        return JSONResponse(status_code=404, content={"error": f"Excel no encontrado en {DATA_PATH}"})
    
    try:
        df = pd.read_excel(DATA_PATH)
        migraciones = 0
        errores = []
        
        for _, row in df.iterrows():
            try:
                empresa_nombre = row["empresa"]
                company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                
                if not company:
                    company = Company(nombre=empresa_nombre, activa=True)
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                
                cedula = str(row["cedula"])
                empleado_existente = db.query(Employee).filter(Employee.cedula == cedula).first()
                
                if not empleado_existente:
                    nuevo_empleado = Employee(
                        cedula=cedula,
                        nombre=row["nombre"],
                        correo=row["correo"],
                        telefono=row.get("telefono", None),
                        company_id=company.id,
                        eps=row.get("eps", None),
                        activo=True
                    )
                    db.add(nuevo_empleado)
                    db.commit()
                    migraciones += 1
                
            except Exception as e:
                errores.append(f"Error en {row.get('cedula', 'N/A')}: {str(e)}")
        
        return {
            "status": "ok",
            "migraciones_exitosas": migraciones,
            "errores": errores,
            "total_procesados": len(df)
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error: {str(e)}"})

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Verifica estado de API y BD"""
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "version": "2.0.0",
            "cors_enabled": True
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        })