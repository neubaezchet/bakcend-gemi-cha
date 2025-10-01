from app.image_quality_validator import validate_uploaded_file
from typing import List
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os, uuid, shutil, tempfile, logging, sys, traceback
from pathlib import Path
from datetime import datetime, date
import calendar
from app.drive_uploader import upload_to_drive
from app.pdf_merger import merge_pdfs_from_uploads
from app.email_templates import get_confirmation_template, get_alert_template
from app.whatsapp_service import WhatsAppService
from app.simple_tracking import SimpleTrackingSystem

# IMPORTAR EL NUEVO SISTEMA DE EMAILS
from app.email_sender import email_service

# Configurar logging para debug
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
    """Obtiene la quincena actual para el mensaje"""
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
    print(f"Cedula: {cedula}")
    print(f"Email: {email}")
    print(f"Telefono: {telefono}")
    print(f"Tipo: {tipo}")
    print(f"Archivos recibidos: {len(archivos)}")
    
    # VALIDAR CALIDAD DE ARCHIVOS
    print("=== VALIDANDO CALIDAD DE ARCHIVOS ===")
    archivos_rechazados = []
    for archivo in archivos:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(archivo.filename).suffix) as tmp:
            shutil.copyfileobj(archivo.file, tmp)
            temp_path = Path(tmp.name)
            archivo.file.seek(0)  # Reset para siguiente uso
            
            # Validar calidad
            print(f"Validando: {archivo.filename}")
            is_valid, message, details = validate_uploaded_file(temp_path)
            temp_path.unlink()  # Limpiar temporal
            
            if not is_valid:
                print(f"❌ Archivo rechazado: {archivo.filename} - {message}")
                archivos_rechazados.append(f"{archivo.filename}: {message}")
            else:
                print(f"✅ Archivo aceptado: {archivo.filename}")

    if archivos_rechazados:
        print(f"❌ PROCESO DETENIDO - Archivos con baja calidad")
        return JSONResponse(
            status_code=400,
            content={
                "error": "Algunos archivos no tienen calidad aceptable",
                "archivos_rechazados": archivos_rechazados
            }
        )
    
    print("✅ Todos los archivos pasaron validación de calidad")
    
    try:
        df = pd.read_excel(DATA_PATH)
        print("✅ Excel leído correctamente")
    except Exception as e:
        error_msg = f"No se pudo leer el Excel: {e}"
        print(f"❌ {error_msg}")
        return JSONResponse(status_code=500, content={"error": error_msg})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = f"INC-{str(uuid.uuid4())[:8].upper()}"
    
    print(f"Consecutivo generado: {consecutivo}")
    print(f"Empleado encontrado: {empleado is not None and not empleado.empty}")
    
    # Procesar y combinar archivos en un solo PDF
    try:
        empresa_destino = empleado.iloc[0]["empresa"] if empleado is not None and not empleado.empty else "OTRA_EMPRESA"
        
        print("Procesando archivos...")
        pdf_final_path, original_filenames = await merge_pdfs_from_uploads(archivos, cedula, tipo)
        print(f"✅ PDF combinado creado: {len(original_filenames)} archivos")
        
        print("Subiendo a Drive...")
        link_pdf = upload_to_drive(pdf_final_path, empresa_destino, cedula, tipo, consecutivo)
        print(f"✅ Subido a Drive: {link_pdf}")
        
        # Limpiar archivo temporal
        pdf_final_path.unlink()
        print("✅ Archivo temporal limpiado")
        
    except Exception as e:
        error_msg = f"Error procesando archivos: {e}"
        print(f"❌ {error_msg}")
        return JSONResponse(status_code=500, content={"error": error_msg})

    # Crear registro de seguimiento
    print("Creando tracking...")
    tracking_system.create_tracking(
        consecutivo=consecutivo,
        cedula=cedula,
        nombre=empleado.iloc[0]["nombre"] if empleado is not None and not empleado.empty else "",
        empresa=empresa_destino,
        telefono=telefono,
        email=email,
        archivos=original_filenames
    )
    print("✅ Tracking creado")

    # Obtener quincena actual para el mensaje
    quinzena_actual = get_current_quinzena()
    
    # Si el empleado está en el Excel
    if empleado is not None and not empleado.empty:
        print("=== EMPLEADO REGISTRADO - PROCESANDO EMAILS ===")
        
        nombre = empleado.iloc[0]["nombre"]
        correo_empleado = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        
        print(f"Datos empleado: {nombre} - {correo_empleado} - {empresa_reg}")
        
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
        Buen dia {nombre},
        
        Confirmo recibido de la documentacion correspondiente y procederemos a realizar la revision. 
        En caso de que cumpla con los requisitos establecidos, se realizara la carga en el sistema {quinzena_actual}.
        
        Consecutivo: {consecutivo}
        Empresa: {empresa_reg}
        Documentos: {', '.join(original_filenames)}
        Link del archivo: {link_pdf}
        
        Estar pendiente via WhatsApp y correo para seguir en el proceso de radicacion.
        
        --
        IncaNeurobaeza
        "Trabajando para ayudarte"
        """
        
        # Lista de correos para enviar (evitar duplicados)
        emails_to_send = []
        if correo_empleado and correo_empleado.strip():
            emails_to_send.append(correo_empleado.strip())
        if email and email.strip() and email.strip().lower() != (correo_empleado or "").strip().lower():
            emails_to_send.append(email.strip())
        
        print(f"Emails destino: {emails_to_send}")
        
        # Enviar correo a todos los emails usando el nuevo sistema
        envios_exitosos = 0
        errores_envio = []
        
        for email_dest in emails_to_send:
            print(f"--- Enviando email a: {email_dest} ---")
            sent, err = email_service.send_html_email(
                email_dest, 
                f"Confirmacion Recepcion Incapacidad - {consecutivo}",
                html_empleado,
                text_empleado
            )
            if sent:
                envios_exitosos += 1
                print(f"✅ Email enviado exitosamente a {email_dest}")
            else:
                error_msg = f"Error enviando a {email_dest}: {err}"
                errores_envio.append(error_msg)
                print(f"❌ {error_msg}")
        
        # Enviar copia a supervisión
        print("--- Enviando copia a supervision ---")
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
        
        sent_supervision, err_supervision = email_service.send_html_email(
            "xoblaxbaezaospina@gmail.com", 
            f"Copia Registro Incapacidad - {consecutivo} - {empresa_reg}",
            html_supervision
        )
        
        if sent_supervision:
            print("✅ Email de supervision enviado exitosamente")
        else:
            print(f"❌ Error email supervision: {err_supervision}")
            errores_envio.append(f"Supervision: {err_supervision}")
        
        # Enviar WhatsApp
        print("--- Enviando WhatsApp ---")
        whatsapp_sent = False
        try:
            whatsapp_sent = whatsapp_service.send_confirmation_whatsapp(
                telefono=telefono,
                nombre=nombre,
                consecutivo=consecutivo,
                empresa=empresa_reg,
                quinzena=quinzena_actual,
                archivos_nombres=original_filenames,
                email_contacto=email,
                cedula=cedula
            )
            print(f"WhatsApp enviado: {whatsapp_sent}")
        except Exception as e:
            print(f"❌ Error WhatsApp: {e}")
        
        # Preparar respuesta
        response_data = {
            "status": "ok" if envios_exitosos > 0 else "partial",
            "mensaje": f"Registro procesado. Emails: {envios_exitosos}/{len(emails_to_send)} enviados",
            "consecutivo": consecutivo,
            "link_pdf": link_pdf,
            "archivos_combinados": len(original_filenames),
            "correos_enviados": emails_to_send,
            "envios_exitosos": envios_exitosos,
            "whatsapp_enviado": whatsapp_sent
        }
        
        if errores_envio:
            response_data["errores_envio"] = errores_envio
            
        if envios_exitosos == 0:
            response_data["status"] = "error"
            response_data["mensaje"] = f"Error: No se pudo enviar ningun email. {'; '.join(errores_envio[:2])}"
            return JSONResponse(status_code=500, content=response_data)
            
        return response_data
    
    else:
        print("=== CEDULA NO ENCONTRADA - PROCESANDO ALERTAS ===")
        
        # HTML de confirmación para solicitante no registrado
        html_confirmacion_no_registrado = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Confirmacion Documentacion</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: bold;">IncaNeurobaeza</h1>
                    <p style="margin: 5px 0 0 0; font-style: italic; opacity: 0.9;">"Trabajando para ayudarte"</p>
                </div>
                <div style="padding: 30px 20px;">
                    <p>Buen dia,</p>
                    <p>Confirmo recibido de la documentacion correspondiente. Su solicitud esta siendo revisada.</p>
                    <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
                        <strong>Consecutivo:</strong> {consecutivo}<br>
                        <strong>Cedula:</strong> {cedula}
                    </div>
                    <p><strong>Importante:</strong> Su cedula no se encuentra en nuestra base de datos. Nos comunicaremos con usted para validar la informacion.</p>
                </div>
                <div style="background: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                    <strong>IncaNeurobaeza</strong><br>
                    "Trabajando para ayudarte"<br>
                    Este es un mensaje automatico.
                </div>
            </div>
        </body>
        </html>
        """
        
        # Template de alerta para supervisión
        html_alerta = get_alert_template(
            tipo="alerta",
            cedula=cedula,
            consecutivo=consecutivo,
            email_contacto=email,
            telefono=telefono,
            quinzena=quinzena_actual
        )
        
        # Enviar confirmación al solicitante usando el nuevo sistema
        print(f"--- Enviando confirmacion a solicitante: {email} ---")
        sent_solicitante, err_sol = email_service.send_html_email(
            email,
            f"Confirmacion Recepcion Documentacion - {consecutivo}",
            html_confirmacion_no_registrado
        )
        
        # Enviar alerta a supervisión
        print("--- Enviando alerta a supervision ---")
        sent_alerta, err_alert = email_service.send_html_email(
            "xoblaxbaezaospina@gmail.com", 
            f"ALERTA: Cedula no encontrada - {consecutivo}",
            html_alerta
        )
        
        # Enviar WhatsApp para cédula no encontrada
        print("--- Enviando WhatsApp (cedula no encontrada) ---")
        whatsapp_sent = False
        try:
            whatsapp_sent = whatsapp_service.send_confirmation_whatsapp(
                telefono=telefono,
                nombre="",
                consecutivo=consecutivo,
                empresa=None,
                quinzena=quinzena_actual,
                archivos_nombres=original_filenames,
                email_contacto=email,
                cedula=cedula
            )
            print(f"WhatsApp enviado: {whatsapp_sent}")
        except Exception as e:
            print(f"❌ Error WhatsApp: {e}")
            
        # Preparar respuesta
        emails_enviados = []
        errores = []
        
        if sent_solicitante:
            emails_enviados.append(email)
            print(f"✅ Confirmacion enviada a {email}")
        else:
            errores.append(f"Solicitante: {err_sol}")
            print(f"❌ Error enviando a {email}: {err_sol}")
            
        if sent_alerta:
            emails_enviados.append("xoblaxbaezaospina@gmail.com")
            print("✅ Alerta enviada a supervision")
        else:
            errores.append(f"Supervision: {err_alert}")
            print(f"❌ Error enviando alerta: {err_alert}")
        
        response_data = {
            "status": "warning" if emails_enviados else "error",
            "mensaje": "Cedula no encontrada - Documentacion recibida para revision",
            "consecutivo": consecutivo,
            "correos_enviados": emails_enviados,
            "whatsapp_enviado": whatsapp_sent
        }
        
        if errores:
            response_data["errores_envio"] = errores
            
        if not emails_enviados:
            response_data["mensaje"] = f"Error: No se pudo enviar ningun email. {'; '.join(errores)}"
            return JSONResponse(status_code=500, content=response_data)
            
        return response_data

@app.get("/seguimiento/{consecutivo}", response_class=HTMLResponse)
async def seguimiento_incapacidad(consecutivo: str):
    """Pagina web de seguimiento de incapacidad"""
    try:
        tracking_info = tracking_system.get_tracking_info(consecutivo)
        
        if not tracking_info:
            return HTMLResponse(content=f"""
            <!DOCTYPE html>
            <html><head><title>No encontrado</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>Consecutivo no encontrado</h1>
            <p>El consecutivo {consecutivo} no existe en nuestros registros.</p>
            </body></html>
            """)
        
        # Preparar datos
        estado_actual = tracking_info["estado_actual"]
        progress_percentage = tracking_system.get_progress_percentage(estado_actual)
        next_steps = tracking_system.get_next_steps(estado_actual)
        status_color = tracking_system.get_status_color(estado_actual)
        fecha_creacion = datetime.fromisoformat(tracking_info["fecha_creacion"]).strftime("%d/%m/%Y")
        
        # Generar HTML de proximos pasos
        next_steps_html = ""
        for step in next_steps:
            next_steps_html += f"<li>{step}</li>"
        
        # Generar HTML del historial
        historial_html = ""
        for i, evento in enumerate(tracking_info["historial"]):
            fecha_formato = datetime.fromisoformat(evento["fecha"]).strftime("%d/%m/%Y %H:%M")
            historial_html += f"""
            <div class="timeline-item">
                <div class="timeline-marker" style="background-color: {tracking_system.get_status_color(evento['estado'])};">
                    {i + 1}
                </div>
                <div class="timeline-content">
                    <h6>{evento["estado"].replace("_", " ").title()}</h6>
                    <p>{evento["descripcion"]}</p>
                    <small>{fecha_formato}</small>
                </div>
            </div>
            """
        
        # Pagina HTML completa
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Seguimiento Incapacidad - {consecutivo}</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                .container {{ 
                    max-width: 800px; 
                    margin: 0 auto; 
                    background: white; 
                    border-radius: 20px; 
                    overflow: hidden;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.15);
                }}
                .header {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; 
                    padding: 40px 30px; 
                    text-align: center; 
                }}
                .header h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
                .header .subtitle {{ opacity: 0.9; font-style: italic; }}
                .consecutivo {{ 
                    background: rgba(255,255,255,0.2); 
                    padding: 10px 20px; 
                    border-radius: 50px; 
                    margin-top: 20px;
                    display: inline-block;
                }}
                .content {{ padding: 40px 30px; }}
                .status-badge {{ 
                    display: inline-block;
                    padding: 15px 30px;
                    border-radius: 50px;
                    color: white;
                    font-weight: bold;
                    font-size: 1.1rem;
                    margin: 20px 0;
                    text-transform: uppercase;
                    background-color: {status_color};
                }}
                .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 30px 0;
                }}
                .info-card {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 15px;
                    border-left: 4px solid #667eea;
                }}
                .info-card h6 {{
                    color: #667eea;
                    font-weight: bold;
                    margin-bottom: 10px;
                    font-size: 0.85rem;
                }}
                .info-card p {{ color: #333; font-weight: 500; }}
                .timeline {{ margin: 30px 0; }}
                .timeline-item {{ display: flex; margin-bottom: 20px; }}
                .timeline-marker {{
                    width: 40px; height: 40px; border-radius: 50%;
                    display: flex; align-items: center; justify-content: center;
                    color: white; font-weight: bold; margin-right: 15px;
                    flex-shrink: 0;
                }}
                .timeline-content {{
                    background: #f8f9fa; padding: 15px 20px; border-radius: 15px;
                    flex: 1; position: relative;
                }}
                .timeline-content h6 {{ color: #333; margin-bottom: 5px; }}
                .timeline-content p {{ color: #666; margin-bottom: 5px; }}
                .timeline-content small {{ color: #999; font-size: 0.8rem; }}
                .next-steps {{
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    padding: 25px; border-radius: 15px; margin: 30px 0;
                }}
                .next-steps h5 {{ color: #667eea; margin-bottom: 15px; }}
                .next-steps ul {{ list-style: none; }}
                .next-steps li {{ 
                    padding: 8px 0; position: relative; padding-left: 25px; 
                }}
                .next-steps li::before {{
                    content: '▶'; position: absolute; left: 0; 
                    color: #667eea; font-size: 0.8rem;
                }}
                .contact-section {{
                    background: #f8f9fa; padding: 25px; text-align: center;
                    margin-top: 30px;
                }}
                .contact-buttons {{ 
                    display: flex; justify-content: center; gap: 15px; 
                    flex-wrap: wrap; margin-top: 15px; 
                }}
                .contact-btn {{
                    padding: 12px 24px; border-radius: 25px; 
                    text-decoration: none; color: white; font-weight: bold;
                    transition: transform 0.3s ease;
                }}
                .contact-btn:hover {{ transform: translateY(-2px); color: white; }}
                .whatsapp-btn {{ background: #25d366; }}
                .email-btn {{ background: #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>IncaNeurobaeza</h1>
                    <p class="subtitle">"Trabajando para ayudarte"</p>
                    <div class="consecutivo">{consecutivo}</div>
                </div>

                <div class="content">
                    <div style="text-align: center;">
                        <h4>Estado Actual del Proceso</h4>
                        <div class="status-badge">{estado_actual.replace("_", " ").title()}</div>
                    </div>

                    <div class="info-grid">
                        <div class="info-card">
                            <h6>EMPLEADO</h6>
                            <p>{tracking_info.get('nombre') or 'En validacion'}</p>
                        </div>
                        <div class="info-card">
                            <h6>CEDULA</h6>
                            <p>{tracking_info.get('cedula')}</p>
                        </div>
                        <div class="info-card">
                            <h6>EMPRESA</h6>
                            <p>{tracking_info.get('empresa') or 'Por confirmar'}</p>
                        </div>
                        <div class="info-card">
                            <h6>FECHA</h6>
                            <p>{fecha_creacion}</p>
                        </div>
                    </div>

                    <div class="timeline">
                        <h5>Historial del Proceso</h5>
                        {historial_html}
                    </div>

                    <div class="next-steps">
                        <h5>Proximos Pasos</h5>
                        <ul>{next_steps_html}</ul>
                    </div>
                </div>

                <div class="contact-section">
                    <h6>¿Necesita ayuda?</h6>
                    <div class="contact-buttons">
                        <a href="https://wa.me/57{tracking_info.get('telefono', '').replace('57', '')}?text=Consulta sobre incapacidad {consecutivo}" 
                           class="contact-btn whatsapp-btn" target="_blank">WhatsApp</a>
                        <a href="mailto:davidbaezaospino@gmail.com?subject=Consulta {consecutivo}" 
                           class="contact-btn email-btn">Email</a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)

@app.get("/")
def root():
    return {"message": "API IncaNeurobaeza funcionando - Trabajando para ayudarte"}

# =================================
# ENDPOINTS DE DEBUG Y TESTING
# =================================

@app.get("/debug-email-config")
def debug_email_config():
    """Endpoint para ver la configuración de email actual"""
    config = {
        "smtp_server": email_service.smtp_server,
        "smtp_port": email_service.smtp_port,
        "email": email_service.email,
        "password_length": len(email_service.password),
        "password_preview": email_service.password[:4] + "..." + email_service.password[-4:] if len(email_service.password) > 8 else "***",
        "env_vars": {
            "SMTP_EMAIL": os.environ.get("SMTP_EMAIL"),
            "SMTP_PASS_exists": bool(os.environ.get("SMTP_PASS")),
            "SMTP_PASS_length": len(os.environ.get("SMTP_PASS", "")),
        }
    }
    return config

@app.get("/test-smtp-connection")
def test_smtp_connection():
    """Endpoint para probar solo la conexión SMTP sin enviar email"""
    try:
        success, message = email_service.test_connection()
        return {
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        error_details = {
            "success": False,
            "message": f"Excepción no controlada: {str(e)}",
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat()
        }
        print(f"❌ Error en test_smtp_connection: {error_details}")
        return error_details

@app.get("/test-email")
def test_email():
    """Endpoint para probar el envio de emails con el nuevo sistema - CON DETALLES DE ERROR"""
    print("=== PROBANDO NUEVO SISTEMA EMAIL ===")
    
    try:
        sent, error = email_service.send_html_email(
            "davidbaezaospino@gmail.com",
            "Test Email - IncaNeurobaeza NUEVO SISTEMA",
            "<h1>Email de Prueba - Nuevo Sistema</h1><p>Si recibes este mensaje, el nuevo sistema de emails está funcionando correctamente.</p>",
            "Email de Prueba - Nuevo Sistema - Si recibes este mensaje, el sistema está funcionando correctamente."
        )
        
        result = {
            "success": sent,
            "timestamp": datetime.now().isoformat(),
            "email_config": {
                "server": email_service.smtp_server,
                "port": email_service.smtp_port,
                "email": email_service.email,
                "password_length": len(email_service.password)
            }
        }
        
        if sent:
            result["message"] = "Email de prueba enviado exitosamente"
        else:
            result["message"] = f"Error enviando email: {error}"
            result["error_details"] = str(error)
            
        return result
            
    except Exception as e:
        error_result = {
            "success": False,
            "message": f"Excepción no controlada: {str(e)}",
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
            "email_config": {
                "server": getattr(email_service, 'smtp_server', 'N/A'),
                "port": getattr(email_service, 'smtp_port', 'N/A'),
                "email": getattr(email_service, 'email', 'N/A'),
                "password_length": len(getattr(email_service, 'password', ''))
            }
        }
        print(f"❌ Error en test_email: {error_result}")
        return error_result

@app.get("/debug-all-env-vars")
def debug_all_env_vars():
    """Endpoint para ver todas las variables de entorno relacionadas con email"""
    env_vars = {}
    email_related = ['SMTP_EMAIL', 'SMTP_PASS', 'SMTP_SERVER', 'SMTP_PORT', 'SMTP_USER']
    
    for var in email_related:
        value = os.environ.get(var)
        if value:
            if 'PASS' in var.upper():
                env_vars[var] = f"***{value[-4:]}" if len(value) > 4 else "***"
            else:
                env_vars[var] = value
        else:
            env_vars[var] = None
    
    return {
        "environment_variables": env_vars,
        "total_env_vars": len(os.environ),
        "python_path": os.environ.get('PYTHONPATH', 'Not set'),
        "current_working_directory": os.getcwd()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
            "