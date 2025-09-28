# app/email_sender.py
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self):
        # Configuración con tu nueva App Password
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email = "davidbaezaospino@gmail.com"
        self.password = "rhht tviz womn tnas"  # Tu nueva App Password
        
        # También intentar leer de variables de entorno como fallback
        self.email = os.environ.get("SMTP_EMAIL", self.email)
        self.password = os.environ.get("SMTP_PASS", self.password)
        
    def send_html_email(self, to_email: str, subject: str, html_body: str, 
                       text_body: str = None, attachments: list = None) -> tuple:
        """
        Envía correo HTML con soporte para adjuntos
        
        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        print(f"=== ENVIANDO EMAIL ===")
        print(f"TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"FROM: {self.email}")
        print(f"SERVER: {self.smtp_server}:{self.smtp_port}")
        
        # Crear mensaje
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"IncaNeurobaeza <{self.email}>"
        msg["To"] = to_email
        
        # Agregar texto plano si se proporciona
        if text_body:
            part1 = MIMEText(text_body, "plain", "utf-8")
            msg.attach(part1)
        
        # Agregar HTML
        part2 = MIMEText(html_body, "html", "utf-8")
        msg.attach(part2)
        
        # Agregar adjuntos si los hay
        if attachments:
            for attachment in attachments:
                if isinstance(attachment, dict) and 'filename' in attachment and 'content' in attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename={attachment["filename"]}'
                    )
                    msg.attach(part)
        
        try:
            print("Conectando a Gmail SMTP...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            print("Conexión establecida")
            
            server.starttls()
            print("TLS activado")
            
            server.login(self.email, self.password)
            print("Login exitoso")
            
            server.sendmail(self.email, [to_email], msg.as_string())
            server.quit()
            print(f"✅ Email enviado exitosamente a {to_email}")
            
            return True, None
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"Error de autenticación SMTP: {str(e)}"
            print(f"❌ {error_msg}")
            print("POSIBLES CAUSAS:")
            print("1. Clave de aplicación incorrecta o expirada")
            print("2. 2FA no activado en Gmail")
            print("3. 'Acceso de apps menos seguras' deshabilitado")
            return False, error_msg
            
        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"Destinatario rechazado: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg
            
        except smtplib.SMTPServerDisconnected as e:
            error_msg = f"Servidor desconectado: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Error general enviando email: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg

# Instancia global del servicio
email_service = EmailSender()