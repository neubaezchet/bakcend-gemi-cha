import requests
import os
from urllib.parse import quote

class WhatsAppService:
    def __init__(self):
        # Configuración de WhatsApp Business API
        self.api_token = os.environ.get("WHATSAPP_API_TOKEN", "")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_ID", "")
        self.base_url = os.environ.get("WHATSAPP_API_URL", "https://graph.facebook.com/v18.0")
        
        # URL base de tu app para el seguimiento
        self.app_base_url = os.environ.get("TRACKING_URL", "https://tu-app.onrender.com")

    def generate_tracking_qr_url(self, consecutivo: str) -> str:
        """Genera URL del QR que lleva a la página de seguimiento"""
        tracking_page_url = f"{self.app_base_url}/seguimiento/{consecutivo}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(tracking_page_url)}"
        return qr_url

    def send_confirmation_whatsapp(self, telefono: str, nombre: str, consecutivo: str, 
                                 empresa: str = None, quinzena: str = None, 
                                 archivos_nombres: list = None, email_contacto: str = "",
                                 cedula: str = "") -> bool:
        """
        Envía mensaje de WhatsApp con el mismo contenido del correo + QR de seguimiento
        """
        try:
            if not self.api_token or not self.phone_number_id:
                print("⚠️ WhatsApp no configurado - saltando envío")
                return False
                
            # Limpiar número de teléfono
            clean_phone = self.clean_phone_number(telefono)
            
            # Crear mensaje idéntico al correo pero para WhatsApp
            if empresa:  # Empleado registrado
                archivos_lista = "\n".join([f"• {archivo}" for archivo in (archivos_nombres or [])])
                
                message = f"""🏥 *IncaNeurobaeza*
_"Trabajando para ayudarte"_

Buen día *{nombre}*,

✅ Confirmo recibido de la documentación correspondiente y procederemos a *realizar la revisión*. En caso de que cumpla con los requisitos establecidos, se realizará la carga en el sistema *{quinzena}*.

📋 *Detalles del Registro:*
- *Consecutivo:* {consecutivo}
- *Empresa:* {empresa}
- *Email contacto:* {email_contacto}
- *Teléfono:* {telefono}

📄 *Documentos recibidos:*
{archivos_lista}

⚠️ *IMPORTANTE:*
Estar pendiente vía WhatsApp y correo para seguir en el proceso de radicación si llegase a cumplir los requisitos establecidos, del contrario se notificará para su debida gestión.

🔍 *Seguimiento en tiempo real:*
Le envío un código QR para que pueda ver el estado de su proceso en cualquier momento.

*¿Necesita ayuda?* Responda a este mensaje."""

            else:  # Cédula no encontrada
                message = f"""🏥 *IncaNeurobaeza*
_"Trabajando para ayudarte"_

Buen día,

📄 Confirmo recibido de la documentación correspondiente. Su solicitud está siendo revisada.

📋 *Detalles:*
- *Consecutivo:* {consecutivo}
- *Cédula:* {cedula}

⚠️ *IMPORTANTE:*
Su cédula no se encuentra en nuestra base de datos. Nos comunicaremos con usted para validar la información.

🔍 *Seguimiento:*
Le envío un código QR para que pueda ver el estado de su proceso.

Manténgase pendiente por este medio y correo electrónico.

*¿Dudas?* Responda a este mensaje."""

            # Enviar mensaje de texto
            success_text = self.send_text_message(clean_phone, message)
            
            # Generar y enviar QR que lleva a la página de seguimiento
            qr_url = self.generate_tracking_qr_url(consecutivo)
            qr_caption = f"🔍 *Seguimiento de su incapacidad*\n\nEscanee este código QR para ver el estado actual y el progreso de su trámite.\n\n*Consecutivo:* {consecutivo}"
            success_qr = self.send_image_message(clean_phone, qr_url, qr_caption)
            
            return success_text and success_qr
            
        except Exception as e:
            print(f"Error enviando WhatsApp: {e}")
            return False

    def send_text_message(self, phone: str, message: str) -> bool:
        """Envía mensaje de texto por WhatsApp"""
        try:
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "messaging_product": "whatsapp",
                "to": phone,
                "text": {"body": message}
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                print(f"✅ WhatsApp texto enviado a {phone}")
                return True
            else:
                print(f"❌ Error WhatsApp texto: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error enviando texto WhatsApp: {e}")
            return False

    def send_image_message(self, phone: str, image_url: str, caption: str = "") -> bool:
        """Envía imagen (QR) por WhatsApp"""
        try:
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "image",
                "image": {
                    "link": image_url,
                    "caption": caption
                }
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                print(f"✅ WhatsApp QR enviado a {phone}")
                return True
            else:
                print(f"❌ Error WhatsApp QR: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error enviando QR WhatsApp: {e}")
            return False

    def clean_phone_number(self, phone: str) -> str:
        """Limpia y formatea número de teléfono para Colombia"""
        # Quitar espacios, guiones, paréntesis, +
        clean = ''.join(filter(str.isdigit, phone))
        
        # Si ya tiene 57 al inicio, mantenerlo
        if clean.startswith('57') and len(clean) >= 12:
            return clean
        # Si empieza con 3 (móviles colombianos), agregar 57
        elif clean.startswith('3') and len(clean) == 10:
            return f"57{clean}"
        # Si no tiene código de país, asumir que es colombiano
        elif len(clean) == 10:
            return f"57{clean}"
        else:
            return clean