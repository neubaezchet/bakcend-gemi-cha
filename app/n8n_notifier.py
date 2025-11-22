"""
Notificador n8n - Reemplaza Brevo
IncaBaeza - 2024
"""

import os
import requests

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "https://tu-n8n.app/webhook/incapacidades")

def enviar_a_n8n(tipo_notificacion: str, email: str, serial: str, html_content: str, 
                 cc_email: str = None, adjuntos_base64: list = None):
    """
    Envía notificación a n8n en lugar de Brevo
    
    Args:
        tipo_notificacion: 'confirmacion', 'incompleta', 'completa', 'eps', 'tthh', 'extra'
        email: Email del destinatario principal
        serial: Serial del caso
        html_content: HTML del email generado
        cc_email: Email de copia (opcional)
        adjuntos_base64: Lista de adjuntos en base64 (opcional)
    
    Returns:
        bool: True si se envió correctamente
    """
    
    payload = {
        "tipo_notificacion": tipo_notificacion,
        "email": email,
        "serial": serial,
        "html_content": html_content,
        "cc_email": cc_email,
        "adjuntos": adjuntos_base64 or []
    }
    
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Notificación enviada a n8n: {serial} ({tipo_notificacion})")
            return True
        else:
            print(f"❌ Error en n8n: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error conectando a n8n: {e}")
        return False