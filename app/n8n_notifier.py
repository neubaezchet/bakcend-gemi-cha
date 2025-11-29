"""
Notificador n8n - Reemplaza Brevo
IncaBaeza - 2024
"""

import os
import requests
from typing import List, Optional

N8N_WEBHOOK_URL = os.environ.get(
    "N8N_WEBHOOK_URL", 
    "https://n8n-incaneurobaeza.onrender.com/webhook/incapacidades"
)

def enviar_a_n8n(
    tipo_notificacion: str, 
    email: str, 
    serial: str, 
    subject: str,
    html_content: str, 
    cc_email: Optional[str] = None, 
    adjuntos_base64: Optional[List[dict]] = None
) -> bool:
    """
    Envía notificación a n8n para procesamiento de emails
    
    Args:
        tipo_notificacion: 'confirmacion', 'incompleta', 'ilegible', 'completa', 
                          'eps', 'tthh', 'extra', 'recordatorio', 'alerta_jefe'
        email: Email del destinatario principal
        serial: Serial del caso
        subject: Asunto del email
        html_content: HTML del email generado
        cc_email: Email de copia (empresa)
        adjuntos_base64: Lista de adjuntos en base64
    
    Returns:
        bool: True si se envió correctamente
    """
    
    # ✅ PAYLOAD CORRECTO para n8n
    payload = {
        "tipo_notificacion": tipo_notificacion,
        "email": email,
        "serial": serial,
        "subject": subject,
        "html_content": html_content,
        "cc_email": cc_email if cc_email else "",  # ✅ String vacío si es None
        "adjuntos": adjuntos_base64 if adjuntos_base64 else []
    }
    
    try:
        print(f"📤 Enviando a n8n: {tipo_notificacion} - {serial} - {email}")
        
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ Email enviado via n8n: {serial} ({tipo_notificacion})")
            return True
        else:
            print(f"❌ Error en n8n ({response.status_code}): {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏱️ Timeout enviando a n8n: {serial}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"🔌 Error de conexión con n8n: {N8N_WEBHOOK_URL}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False


def verificar_n8n_activo() -> bool:
    """Verifica si n8n está respondiendo"""
    try:
        health_url = N8N_WEBHOOK_URL.replace("/webhook/incapacidades", "/healthz")
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except:
        return False