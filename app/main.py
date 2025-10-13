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

# Importar Brevo
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

app = FastAPI(title="IncaNeurobaeza API", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://portal-neurobaeza.vercel.app",
        "https://portal-neurobaeza-*.vercel.app",
        "https://repogemin.vercel.app",
        "https://repogemin-*.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir router del portal de validadores
app.include_router(validador_router)

# Ruta al Excel de empleados (para migración inicial)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

# ==================== INICIALIZACIÓN ====================

@app.on_event("startup")
def startup_event():
    """Inicializa la base de datos al arrancar"""
    init_db()
    print("🚀 API iniciada correctamente")

# ==================== UTILIDADES ====================

def get_current_quinzena():
    """Obtiene la quincena actual para el mensaje"""
    today = date.today()
    mes_nombre = calendar.month_name[today.month]
    if today.day <= 15:
        return f"primera quincena de {mes_nombre}"
    else:
        return f"segunda quincena de {mes_nombre}"

def send_html_email(to_email: str, subject: str, html_body: str, text_body: str = None):
    """Envía emails usando Brevo API"""
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    brevo_from_email = os.environ.get("BREVO_FROM_EMAIL", "notificaciones@smtp-brevo.com")
    reply_to_email = os.environ.get("SMTP_EMAIL", "davidbaezaospino@gmail.com")

    if not brevo_api_key:
        error_msg = "Error: Falta la variable de entorno BREVO_API_KEY"
        print(error_msg)
        return False, error_msg

    try:
        print(f"📧 Intentando enviar correo a {to_email} con Brevo...")
        
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = brevo_api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        if isinstance(html_body, bytes):
            html_body = html_body.decode('utf-8')
        if text_body and isinstance(text_body, bytes):
            text_body = text_body.decode('utf-8')
        
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email}],
            sender={"name": "IncaNeurobaeza", "email": brevo_from_email},
            reply_to={"email": reply_to_email},
            subject=subject,
            html_content=html_body,
            text_content=text_body
        )
        
        api_response = api_instance.send_transac_email(send_smtp_email)
        
        print(f"✅ Correo enviado exitosamente a {to_email}")
        print(f"   Message ID: {api_response.message_id}")
        return True, None
        
    except ApiException as e:
        error_msg = f"Error de Brevo API: {e}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error enviando correo: {e}"
        print(f"❌ {error_msg}")
        return False, str(e)

def mapear_tipo_incapacidad(tipo_frontend: str) -> TipoIncapacidad:
    """Mapea el tipo de incapacidad del frontend al enum de BD"""
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
        "endpoints": {
            "trabajadores": "/empleados/{cedula}, /subir-incapacidad/",
            "validadores": "/validador/* (requiere X-Admin-Token)",
            "docs": "/docs"
        }
    }

@app.get("/empleados/{cedula}")
def obtener_empleado(cedula: str, db: Session = Depends(get_db)):
    """Consulta empleado por cédula (para frontend de trabajadores)"""
    
    # Intentar en BD primero
    empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
    
    if empleado:
        return {
            "nombre": empleado.nombre,
            "empresa": empleado.empresa.nombre if empleado.empresa else "No especificada",
            "correo": empleado.correo,
            "eps": empleado.eps
        }
    
    # Si no está en BD, intentar en Excel (fallback)
    try:
        df = pd.read_excel(DATA_PATH)
        empleado_excel = df[df["cedula"] == int(cedula)]
        if not empleado_excel.empty:
            return {
                "nombre": empleado_excel.iloc[0]["nombre"],
                "empresa": empleado_excel.iloc[0]["empresa"],
                "correo": empleado_excel.iloc[0]["correo"],
                "eps": empleado_excel.iloc[0].get("eps", None)
            }
    except Exception as e:
        print(f"Error leyendo Excel: {e}")
    
    return JSONResponse(status_code=404, content={"error": "Empleado no encontrado"})

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
    """Endpoint de recepción de incapacidades (trabajadores)"""
    
    empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
    
    if not empleado_bd:
        try:
            df = pd.read_excel(DATA_PATH)
            empleado_excel = df[df["cedula"] == int(cedula)]
            empleado_encontrado = not empleado_excel.empty
        except:
            empleado_encontrado = False
    else:
        empleado_encontrado = True
    
    consecutivo = f"INC-{str(uuid.uuid4())[:8].upper()}"
    
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
                "mensaje": f"Tienes un caso pendiente ({caso_bloqueante.serial}) que debe completarse antes de subir uno nuevo. Contacta al validador si necesitas autorización."
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
    
    print(f"✅ Caso {consecutivo} persistido en BD con ID {nuevo_caso.id}")
    
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
        
        text_empleado = f"""
        Buen día {nombre},
        
        Confirmo recibido de la documentación correspondiente.
        Consecutivo: {consecutivo}
        Empresa: {empresa_reg}
        Link del archivo: {link_pdf}
        
        --
        IncaNeurobaeza
        """
        
        emails_to_send = []
        if correo_empleado:
            emails_to_send.append(correo_empleado)
        if email and email.lower() != correo_empleado.lower():
            emails_to_send.append(email)
        
        for email_dest in emails_to_send:
            send_html_email(
                email_dest, 
                f"Confirmación Recepción Incapacidad - {consecutivo}",
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
            f"Copia Registro Incapacidad - {consecutivo} - {empresa_reg}",
            html_supervision
        )
        
        return {
            "status": "ok",
            "mensaje": f"Registro exitoso. Caso persistido en BD.",
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
        
        html_confirmacion_no_registrado = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1>IncaNeurobaeza</h1>
                <p style="margin: 0; font-style: italic;">"Trabajando para ayudarte"</p>
            </div>
            <div style="padding: 30px 20px;">
                <p>Buen día,</p>
                <p>Confirmo recibido de la documentación correspondiente. Su solicitud está siendo revisada.</p>
                <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
                    <strong>Consecutivo:</strong> {consecutivo}<br>
                    <strong>Cédula:</strong> {cedula}
                </div>
                <p><strong>Importante:</strong> Su cédula no se encuentra en nuestra base de datos. Nos comunicaremos con usted para validar la información.</p>
            </div>
            <div style="background: #f8f9fa; padding: 15px; text-align: center; border-radius: 0 0 10px 10px; font-size: 12px; color: #666;">
                <strong>IncaNeurobaeza</strong><br>
                "Trabajando para ayudarte"
            </div>
        </div>
        """
        
        send_html_email(
            email,
            f"Confirmación Recepción Documentación - {consecutivo}",
            html_confirmacion_no_registrado
        )
        
        send_html_email(
            "xoblaxbaezaospino@gmail.com", 
            f"⚠️ ALERTA: Cédula no encontrada - {consecutivo}",
            html_alerta
        )
        
        return {
            "status": "warning",
            "mensaje": "Cédula no encontrada - Documentación recibida para revisión",
            "consecutivo": consecutivo,
            "case_id": nuevo_caso.id,
            "link_pdf": link_pdf,
            "correos_enviados": [email]
        }

@app.post("/admin/migrar-excel")
async def migrar_excel_a_bd(db: Session = Depends(get_db)):
    """Migra los empleados desde el Excel a la base de datos"""
    
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
                    print(f"✅ Empresa creada: {empresa_nombre}")
                
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
                    print(f"✅ Empleado migrado: {row['nombre']} ({cedula})")
                
            except Exception as e:
                errores.append(f"Error en fila {row.get('cedula', 'N/A')}: {str(e)}")
                print(f"❌ {errores[-1]}")
        
        return {
            "status": "ok",
            "migraciones_exitosas": migraciones,
            "errores": errores,
            "total_procesados": len(df)
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": f"Error en migración: {str(e)}"
        })

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Verifica el estado de la API y la BD"""
    try:
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "version": "2.0.0"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        })