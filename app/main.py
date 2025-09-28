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
from app.pdf_merger import merge_pdfs_from_uploads  # Nueva funciÃ³n
from app.email_templates import get_confirmation_template, get_alert_template  # Templates
from app.whatsapp_service import WhatsAppService
from app.simple_tracking import SimpleTrackingSystem
from fastapi.responses import HTMLResponse

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

def send_html_email(to_email: str, subject: str, html_body: str, text_body: str = None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # CONFIGURACIÃ“N DE CORREO - Usando tu Gmail actual
    from_email = os.environ.get("SMTP_EMAIL", "davidbaezaospino@gmail.com")
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "davidbaezaospino@gmail.com")
    smtp_pass = os.environ.get("SMTP_PASS", "rfgr brbi xedv ntzt")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"IncaNeurobaeza <{from_email}>"
    msg["To"] = to_email

    # Agregar versiÃ³n texto plano como fallback
    if text_body:
        part1 = MIMEText(text_body, "plain")
        msg.attach(part1)
    
    # Agregar versiÃ³n HTML
    part2 = MIMEText(html_body, "html")
    msg.attach(part2)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        print(f"ðŸ“§ Correo HTML enviado a {to_email}")
        return True, None
    except Exception as e:
        print(f"Error enviando correo: {e}")
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

    # Crear registro de seguimiento
    tracking_system.create_tracking(
        consecutivo=consecutivo,
        cedula=cedula,
        nombre=empleado.iloc[0]["nombre"] if empleado is not None and not empleado.empty else "",
        empresa=empresa_destino,
        telefono=telefono,
        email=email,
        archivos=original_filenames
    )

    # Obtener quincena actual para el mensaje
    quinzena_actual = get_current_quinzena()
    
    # Si el empleado estÃ¡ en el Excel
    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo_empleado = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        
        # Template de confirmaciÃ³n para el empleado
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
        Buen dÃ­a {nombre},
        
        Confirmo recibido de la documentaciÃ³n correspondiente y procederemos a realizar la revisiÃ³n. 
        En caso de que cumpla con los requisitos establecidos, se realizarÃ¡ la carga en el sistema {quinzena_actual}.
        
        Consecutivo: {consecutivo}
        Empresa: {empresa_reg}
        Documentos: {', '.join(original_filenames)}
        Link del archivo: {link_pdf}
        
        Estar pendiente vÃ­a WhatsApp y correo para seguir en el proceso de radicaciÃ³n.
        
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
                f"ConfirmaciÃ³n RecepciÃ³n Incapacidad - {consecutivo}",
                html_empleado,
                text_empleado
            )
            if sent:
                envios_exitosos += 1
            else:
                errores_envio.append(f"Error enviando a {email_dest}: {err}")
        
        # Enviar copia a supervisiÃ³n
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
                "error": f"Errores en envÃ­o de correos: {'; '.join(errores_envio)} | SupervisiÃ³n: {err_supervision}", 
                "link_pdf": link_pdf,
                "consecutivo": consecutivo
            })
        
        # Enviar WhatsApp con QR de seguimiento
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
            
        return {
            "status": "ok",
            "mensaje": f"Registro exitoso. Correos enviados a {envios_exitosos} destinatarios",
            "consecutivo": consecutivo,
            "link_pdf": link_pdf,
            "archivos_combinados": len(original_filenames),
            "correos_enviados": emails_to_send,
            "whatsapp_enviado": whatsapp_sent
        }
    
    else:
        # Si no estÃ¡ en Excel, enviar alerta
        html_alerta = get_alert_template(
            tipo="alerta",
            cedula=cedula,
            consecutivo=consecutivo,
            email_contacto=email,
            telefono=telefono,
            quinzena=quinzena_actual
        )
        
        # Enviar confirmaciÃ³n al email del formulario
        html_confirmacion_no_registrado = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1>IncaNeurobaeza</h1>
                <p style="margin: 0; font-style: italic;">"Trabajando para ayudarte"</p>
            </div>
            <div style="padding: 30px 20px;">
                <p>Buen dÃ­a,</p>
                <p>Confirmo recibido de la documentaciÃ³n correspondiente. Su solicitud estÃ¡ siendo revisada.</p>
                <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
                    <strong>Consecutivo:</strong> {consecutivo}<br>
                    <strong>CÃ©dula:</strong> {cedula}
                </div>
                <p><strong>Importante:</strong> Su cÃ©dula no se encuentra en nuestra base de datos. Nos comunicaremos con usted para validar la informaciÃ³n.</p>
            </div>
            <div style="background: #f8f9fa; padding: 15px; text-align: center; border-radius: 0 0 10px 10px; font-size: 12px; color: #666;">
                <strong>IncaNeurobaeza</strong><br>
                "Trabajando para ayudarte"<br>
                Este es un mensaje automÃ¡tico, no responder a este correo.
            </div>
        </div>
        """
        
        # Enviar confirmaciÃ³n al solicitante
        sent_solicitante, err_sol = send_html_email(
            email,
            f"ConfirmaciÃ³n RecepciÃ³n DocumentaciÃ³n - {consecutivo}",
            html_confirmacion_no_registrado
        )
        
        # Enviar alerta a supervisiÃ³n
        sent_alerta, err_alert = send_html_email(
            "xoblaxbaezaospino@gmail.com", 
            f"âš ï¸ ALERTA: CÃ©dula no encontrada - {consecutivo}",
            html_alerta
        )
        
        if not sent_alerta or not sent_solicitante:
            return JSONResponse(status_code=500, content={
                "error": f"Error enviando correos - Alerta: {err_alert} | Solicitante: {err_sol}", 
                "consecutivo": consecutivo
            })
        
        # Enviar WhatsApp para cÃ©dula no encontrada
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
            
        return {
            "status": "warning",
            "mensaje": "CÃ©dula no encontrada - DocumentaciÃ³n recibida para revisiÃ³n",
            "consecutivo": consecutivo,
            "correos_enviados": [email],
            "whatsapp_enviado": whatsapp_sent
        }

@app.get("/seguimiento/{consecutivo}", response_class=HTMLResponse)
async def seguimiento_incapacidad(consecutivo: str):
    """PÃ¡gina web de seguimiento de incapacidad"""
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
        
        # Generar HTML de prÃ³ximos pasos
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
                    <small>ðŸ“… {fecha_formato}</small>
                </div>
            </div>
            """
        
        # PÃ¡gina HTML completa (copio la pÃ¡gina completa que creÃ© antes)
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Seguimiento Incapacidad - {consecutivo}</title>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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
                .progress-container {{ margin: 30px 0; }}
                .progress-bar {{
                    width: 100%;
                    height: 10px;
                    background: #e9ecef;
                    border-radius: 10px;
                    overflow: hidden;
                    margin-bottom: 20px;
                }}
                .progress-fill {{
                    height: 100%;
                    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                    width: {progress_percentage}%;
                    transition: width 1s ease;
                    border-radius: 10px;
                }}
                .steps {{
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 10px;
                    text-align: center;
                    font-size: 0.9rem;
                }}
                .step {{ padding: 10px 5px; }}
                .step.completed {{ color: #28a745; font-weight: bold; }}
                .step.current {{ color: #667eea; font-weight: bold; }}
                .step.pending {{ color: #6c757d; }}
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
                    content: 'â–¶'; position: absolute; left: 0; 
                    color: #667eea; font-size: 0.8rem;
                }}
                .contact-section {{
                    background: #f8f9fa; padding: 25px; text-align: center;
                    margin-top: 30px; border-radius: 0 0 20px 20px;
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
                @media (max-width: 768px) {{
                    .steps {{ grid-template-columns: repeat(2, 1fr); }}
                    .info-grid {{ grid-template-columns: 1fr; }}
                    .content {{ padding: 30px 20px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- Header -->
                <div class="header">
                    <h1><i class="fas fa-hospital"></i> IncaNeurobaeza</h1>
                    <p class="subtitle">"Trabajando para ayudarte"</p>
                    <div class="consecutivo">
                        <i class="fas fa-qrcode"></i> {consecutivo}
                    </div>
                </div>

                <!-- Content -->
                <div class="content">
                    <!-- Current Status -->
                    <div style="text-align: center;">
                        <h4>Estado Actual del Proceso</h4>
                        <div class="status-badge">
                            <i class="fas fa-info-circle"></i> {estado_actual.replace("_", " ").title()}
                        </div>
                    </div>

                    <!-- Progress Bar -->
                    <div class="progress-container">
                        <div class="progress-bar">
                            <div class="progress-fill"></div>
                        </div>
                        <div class="steps">
                            <div class="step {'completed' if progress_percentage >= 25 else 'pending'}">
                                <i class="fas fa-inbox"></i><br>Recibido
                            </div>
                            <div class="step {'completed' if progress_percentage >= 50 else ('current' if progress_percentage >= 25 else 'pending')}">
                                <i class="fas fa-search"></i><br>RevisiÃ³n
                            </div>
                            <div class="step {'completed' if progress_percentage >= 75 else ('current' if progress_percentage >= 50 else 'pending')}">
                                <i class="fas fa-check"></i><br>Aprobado
                            </div>
                            <div class="step {'completed' if progress_percentage >= 100 else ('current' if progress_percentage >= 75 else 'pending')}">
                                <i class="fas fa-flag"></i><br>Radicado
                            </div>
                        </div>
                    </div>

                    <!-- Info Grid -->
                    <div class="info-grid">
                        <div class="info-card">
                            <h6><i class="fas fa-user"></i> EMPLEADO</h6>
                            <p>{tracking_info.get('nombre') or 'En validaciÃ³n'}</p>
                        </div>
                        <div class="info-card">
                            <h6><i class="fas fa-id-card"></i> CÃ‰DULA</h6>
                            <p>{tracking_info.get('cedula')}</p>
                        </div>
                        <div class="info-card">
                            <h6><i class="fas fa-building"></i> EMPRESA</h6>
                            <p>{tracking_info.get('empresa') or 'Por confirmar'}</p>
                        </div>
                        <div class="info-card">
                            <h6><i class="fas fa-calendar"></i> FECHA</h6>
                            <p>{fecha_creacion}</p>
                        </div>
                    </div>

                    <!-- Timeline -->
                    <div class="timeline">
                        <h5><i class="fas fa-history"></i> Historial del Proceso</h5>
                        {historial_html}
                    </div>

                    <!-- Next Steps -->
                    <div class="next-steps">
                        <h5><i class="fas fa-tasks"></i> PrÃ³ximos Pasos</h5>
                        <ul>{next_steps_html}</ul>
                    </div>
                </div>

                <!-- Contact -->
                <div class="contact-section">
                    <h6><i class="fas fa-headset"></i> Â¿Necesita ayuda?</h6>
                    <div class="contact-buttons">
                        <a href="https://wa.me/57{tracking_info.get('telefono', '').replace('57', '')}?text=Consulta sobre incapacidad {consecutivo}" 
                           class="contact-btn whatsapp-btn" target="_blank">
                            <i class="fab fa-whatsapp"></i> WhatsApp
                        </a>
                        <a href="mailto:davidbaezaospino@gmail.com?subject=Consulta {consecutivo}" 
                           class="contact-btn email-btn">
                            <i class="fas fa-envelope"></i> Email
                        </a>
                    </div>
                </div>
            </div>

            <script>
                // Auto-refresh cada 30 segundos
                setTimeout(() => location.reload(), 30000);
                
                // Animar barra de progreso al cargar
                window.addEventListener('load', () => {{
                    setTimeout(() => {{
                        document.querySelector('.progress-fill').style.width = '{progress_percentage}%';
                    }}, 500);
                }});
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)

@app.get("/")
def root():
    return {"message": "âœ… API IncaNeurobaeza funcionando - Trabajando para ayudarte"}