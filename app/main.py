from app.image_quality_validator import validate_uploaded_file
from typing import List
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os, uuid, shutil, tempfile, logging
from pathlib import Path
from datetime import datetime, date
import calendar
from app.drive_uploader import upload_to_drive
from app.pdf_merger import merge_pdfs_from_uploads
from app.email_templates import get_confirmation_template, get_alert_template
from app.whatsapp_service import WhatsAppService
from app.simple_tracking import SimpleTrackingSystem
from app.email_sender import email_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

whatsapp_service = WhatsAppService()
tracking_system = SimpleTrackingSystem()

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

def get_current_quinzena():
    today = date.today()
    mes_nombre = calendar.month_name[today.month]
    if today.day <= 15:
        return f"primera quincena de {mes_nombre}"
    else:
        return f"segunda quincena de {mes_nombre}"

@app.get("/empleados/{cedula}")
def obtener_empleado(cedula: str):
    try:
        df = pd.read_excel(DATA_PATH)
        empleado = df[df["cedula"] == int(cedula)]
        if empleado.empty:
            return JSONResponse(status_code=404, content={"error": "Empleado no encontrado"})
        return {
            "nombre": empleado.iloc[0]["nombre"],
            "empresa": empleado.iloc[0]["empresa"],
            "correo": empleado.iloc[0]["correo"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/subir-incapacidad/")
async def subir_incapacidad(
    cedula: str = Form(...),
    tipo: str = Form(...),
    email: str = Form(...),
    telefono: str = Form(...),
    archivos: List[UploadFile] = File(...)
):
    print(f"=== INICIANDO PROCESO INCAPACIDAD ===")
    
    # VALIDAR CALIDAD DE ARCHIVOS
    archivos_rechazados = []
    for archivo in archivos:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(archivo.filename).suffix) as tmp:
            shutil.copyfileobj(archivo.file, tmp)
            temp_path = Path(tmp.name)
            archivo.file.seek(0)
            
            is_valid, message, details = validate_uploaded_file(temp_path)
            temp_path.unlink()
            
            if not is_valid:
                archivos_rechazados.append(f"{archivo.filename}: {message}")

    if archivos_rechazados:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Algunos archivos no tienen calidad aceptable",
                "archivos_rechazados": archivos_rechazados
            }
        )
    
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = f"INC-{str(uuid.uuid4())[:8].upper()}"
    
    try:
        empresa_destino = empleado.iloc[0]["empresa"] if empleado is not None and not empleado.empty else "OTRA_EMPRESA"
        pdf_final_path, original_filenames = await merge_pdfs_from_uploads(archivos, cedula, tipo)
        link_pdf = upload_to_drive(pdf_final_path, empresa_destino, cedula, tipo, consecutivo)
        pdf_final_path.unlink()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    tracking_system.create_tracking(
        consecutivo=consecutivo,
        cedula=cedula,
        nombre=empleado.iloc[0]["nombre"] if empleado is not None and not empleado.empty else "",
        empresa=empresa_destino,
        telefono=telefono,
        email=email,
        archivos=original_filenames
    )

    quinzena_actual = get_current_quinzena()
    
    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo_empleado = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        
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
        
        text_empleado = f"Buen dia {nombre}, Confirmo recibido. Consecutivo: {consecutivo}"
        
        emails_to_send = []
        if correo_empleado and correo_empleado.strip():
            emails_to_send.append(correo_empleado.strip())
        if email and email.strip() and email.strip().lower() != (correo_empleado or "").strip().lower():
            emails_to_send.append(email.strip())
        
        envios_exitosos = 0
        errores_envio = []
        
        for email_dest in emails_to_send:
            sent, err = email_service.send_html_email(email_dest, f"Confirmacion - {consecutivo}", html_empleado, text_empleado)
            if sent:
                envios_exitosos += 1
            else:
                errores_envio.append(f"{email_dest}: {err}")
        
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
        
        email_service.send_html_email("xoblaxbaezaospina@gmail.com", f"Copia - {consecutivo}", html_supervision)
        
        return {
            "status": "ok",
            "consecutivo": consecutivo,
            "link_pdf": link_pdf,
            "correos_enviados": emails_to_send,
            "envios_exitosos": envios_exitosos
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
        
        email_service.send_html_email(email, f"Confirmacion - {consecutivo}", html_alerta)
        email_service.send_html_email("xoblaxbaezaospina@gmail.com", f"ALERTA - {consecutivo}", html_alerta)
        
        return {
            "status": "warning",
            "mensaje": "Cedula no encontrada",
            "consecutivo": consecutivo
        }

@app.get("/")
def root():
    return {"message": "API IncaNeurobaeza funcionando"}

@app.get("/test-email")
def test_email():
    try:
        sent, error = email_service.send_html_email(
            "davidbaezaospino@gmail.com",
            "Test",
            "<h1>Test</h1>",
            "Test"
        )
        return {"success": sent, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}