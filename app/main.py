from typing import List
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os, uuid, shutil, tempfile
from pathlib import Path
from datetime import datetime, date
import calendar
from app.drive_uploader import upload_to_drive
from app.pdf_merger import merge_pdfs_from_uploads
from app.email_templates import get_confirmation_template, get_alert_template

# Importar Brevo
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

def get_current_quinzena():
    """Obtiene la quincena actual para el mensaje"""
    today = date.today()
    mes_nombre = calendar.month_name[today.month]
    if today.day <= 15:
        return f"primera quincena de {mes_nombre}"
    else:
        return f"segunda quincena de {mes_nombre}"

def send_html_email(to_email: str, subject: str, html_body: str, text_body: str = None):
    """
    Envía emails usando Brevo API (reemplaza Gmail SMTP bloqueado en Render)
    """
    # Obtener credenciales de variables de entorno
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    brevo_from_email = os.environ.get("BREVO_FROM_EMAIL", "notificaciones@smtp-brevo.com")
    reply_to_email = os.environ.get("SMTP_EMAIL", "davidbaezaospino@gmail.com")

    # Validar que existe la API key
    if not brevo_api_key:
        error_msg = "Error: Falta la variable de entorno BREVO_API_KEY"
        print(error_msg)
        return False, error_msg

    try:
        print(f"📧 Intentando enviar correo a {to_email} con Brevo...")
        
        # Configurar el cliente de Brevo
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = brevo_api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        # Convertir bytes a string si es necesario
        if isinstance(html_body, bytes):
            html_body = html_body.decode('utf-8')
        if text_body and isinstance(text_body, bytes):
            text_body = text_body.decode('utf-8')
        
        # Crear el objeto de email
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email}],
            sender={"name": "IncaNeurobaeza", "email": brevo_from_email},
            reply_to={"email": reply_to_email},
            subject=subject,
            html_content=html_body,
            text_content=text_body
        )
        
        # Enviar el email
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
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"No se pudo leer el Excel: {e}"})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = f"INC-{str(uuid.uuid4())[:8].upper()}"
    
    # Procesar y combinar archivos en un solo PDF
    try:
        empresa_destino = empleado.iloc[0]["empresa"] if empleado is not None and not empleado.empty else "OTRA_EMPRESA"
        
        # Combinar todos los archivos en un solo PDF (SIN portada)
        pdf_final_path, original_filenames = await merge_pdfs_from_uploads(archivos, cedula, tipo)
        
        # Subir el PDF combinado a Drive
        link_pdf = upload_to_drive(pdf_final_path, empresa_destino, cedula, tipo, consecutivo)
        
        # Limpiar archivo temporal
        pdf_final_path.unlink()
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error procesando archivos: {e}"})

    # Obtener quincena actual para el mensaje
    quinzena_actual = get_current_quinzena()
    
    # Si el empleado está en el Excel
    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo_empleado = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        
        # Template de confirmación para el empleado
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
        
        Confirmo recibido de la documentación correspondiente y procederemos a realizar la revisión. 
        En caso de que cumpla con los requisitos establecidos, se realizará la carga en el sistema {quinzena_actual}.
        
        Consecutivo: {consecutivo}
        Empresa: {empresa_reg}
        Documentos: {', '.join([f.decode() if isinstance(f, bytes) else f for f in original_filenames])}
        Link del archivo: {link_pdf}
        
        Estar pendiente vía WhatsApp y correo para seguir en el proceso de radicación.
        
        --
        IncaNeurobaeza
        "Trabajando para ayudarte"
        """
        
        # Lista de correos para enviar (evitar duplicados)
        emails_to_send = []
        if correo_empleado:
            emails_to_send.append(correo_empleado)
        if email and email.lower() != correo_empleado.lower():
            emails_to_send.append(email)
        
        # Enviar correo a todos los emails
        envios_exitosos = 0
        errores_envio = []
        
        for email_dest in emails_to_send:
            sent, err = send_html_email(
                email_dest, 
                f"Confirmación Recepción Incapacidad - {consecutivo}",
                html_empleado,
                text_empleado
            )
            if sent:
                envios_exitosos += 1
            else:
                errores_envio.append(f"Error enviando a {email_dest}: {err}")
        
        # Enviar copia a supervisión
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
        
        sent_supervision, err_supervision = send_html_email(
            "xoblaxbaezaospino@gmail.com", 
            f"Copia Registro Incapacidad - {consecutivo} - {empresa_reg}",
            html_supervision
        )
        
        if envios_exitosos == 0 or not sent_supervision:
            return JSONResponse(status_code=500, content={
                "error": f"Errores en envío de correos: {'; '.join(errores_envio)} | Supervisión: {err_supervision}", 
                "link_pdf": link_pdf,
                "consecutivo": consecutivo
            })
            
        return {
            "status": "ok",
            "mensaje": f"Registro exitoso. Correos enviados a {envios_exitosos} destinatarios",
            "consecutivo": consecutivo,
            "link_pdf": link_pdf,
            "archivos_combinados": len(original_filenames),
            "correos_enviados": emails_to_send
        }
    
    else:
        # Si no está en Excel, enviar alerta
        html_alerta = get_alert_template(
            tipo="alerta",
            cedula=cedula,
            consecutivo=consecutivo,
            email_contacto=email,
            telefono=telefono,
            quinzena=quinzena_actual
        )
        
        # Enviar confirmación al email del formulario
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
                "Trabajando para ayudarte"<br>
                Este es un mensaje automático, no responder a este correo.
            </div>
        </div>
        """
        
        # Enviar confirmación al solicitante
        sent_solicitante, err_sol = send_html_email(
            email,
            f"Confirmación Recepción Documentación - {consecutivo}",
            html_confirmacion_no_registrado
        )
        
        # Enviar alerta a supervisión
        sent_alerta, err_alert = send_html_email(
            "xoblaxbaezaospino@gmail.com", 
            f"⚠️ ALERTA: Cédula no encontrada - {consecutivo}",
            html_alerta
        )
        
        if not sent_alerta or not sent_solicitante:
            return JSONResponse(status_code=500, content={
                "error": f"Error enviando correos - Alerta: {err_alert} | Solicitante: {err_sol}", 
                "consecutivo": consecutivo
            })
            
        return {
            "status": "warning",
            "mensaje": "Cédula no encontrada - Documentación recibida para revisión",
            "consecutivo": consecutivo,
            "correos_enviados": [email]
        }

@app.get("/")
def root():
    return {"message": "✅ API IncaNeurobaeza funcionando con Brevo - Trabajando para ayudarte"}