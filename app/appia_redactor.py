"""
Redactor de Emails con Claude Haiku
Sistema híbrido: Solo se usa para casos complejos
Costo: ~$2.70 USD/mes
"""

import anthropic
import os
from app.checks_disponibles import CHECKS_DISPONIBLES

# Cliente de Anthropic
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

def redactar_email_incompleta(nombre: str, serial: str, checks_seleccionados: list, tipo_incapacidad: str) -> str:
    """
    Redacta email personalizado para casos incompletos
    Usa Claude Haiku (barato y eficiente)
    """
    
    # Construir lista de problemas
    problemas = []
    for check_key in checks_seleccionados:
        if check_key in CHECKS_DISPONIBLES:
            problemas.append(CHECKS_DISPONIBLES[check_key]['descripcion'])
    
    problemas_texto = "\n".join([f"• {p}" for p in problemas])
    
    prompt = f"""Redacta un email profesional, claro y amable para notificar a {nombre} que su incapacidad médica (serial {serial}) está incompleta.

**Problemas encontrados:**
{problemas_texto}

**Tipo de incapacidad:** {tipo_incapacidad}

**Requisitos del email:**
- Tono profesional pero amigable
- Máximo 200 palabras
- Explicar claramente QUÉ documentos faltan o tienen problemas
- Dar instrucciones precisas de cómo corregir
- Recordar que debe subir los documentos corregidos lo antes posible
- NO inventar información adicional
- NO agregar datos no mencionados
- Formato: Solo el cuerpo del mensaje (sin saludos ni despedidas, eso va en la plantilla)

Responde ÚNICAMENTE con el contenido del email, sin agregar explicaciones."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",  # Modelo económico
            max_tokens=400,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Email redactado con IA para {serial} ({len(contenido)} caracteres)")
        return contenido
        
    except Exception as e:
        print(f"❌ Error redactando con IA: {e}")
        # Fallback a plantilla estática
        return f"""Tu incapacidad está incompleta debido a los siguientes problemas:

{problemas_texto}

Por favor, revisa cuidadosamente y vuelve a enviar los documentos corregidos lo antes posible."""


def redactar_email_ilegible(nombre: str, serial: str, checks_seleccionados: list) -> str:
    """
    Redacta email para documentos ilegibles o con problemas de calidad
    """
    
    problemas = []
    for check_key in checks_seleccionados:
        if check_key in CHECKS_DISPONIBLES:
            problemas.append(CHECKS_DISPONIBLES[check_key]['descripcion'])
    
    problemas_texto = "\n".join([f"• {p}" for p in problemas])
    
    prompt = f"""Redacta un email profesional para notificar a {nombre} que sus documentos (serial {serial}) tienen problemas de calidad.

**Problemas de calidad detectados:**
{problemas_texto}

**Requisitos:**
- Tono empático y constructivo
- Máximo 150 palabras
- Dar consejos prácticos para tomar fotos claras:
  * Usar buena iluminación
  * Colocar documento plano
  * Mostrar todos los bordes
  * Evitar sombras y reflejos
- Enfatizar la importancia de documentos legibles
- Formato: Solo cuerpo del mensaje

Responde ÚNICAMENTE con el contenido."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",
            max_tokens=300,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Email ilegible redactado con IA para {serial}")
        return contenido
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"""Tus documentos presentan problemas de calidad que impiden su lectura:

{problemas_texto}

**Recomendaciones para tomar fotos claras:**
- Usa buena iluminación (preferiblemente luz natural)
- Coloca el documento sobre una superficie plana
- Asegúrate de que todos los bordes sean visibles
- Evita sombras, reflejos o dedos en la imagen
- Verifica que el texto sea legible antes de enviar

Por favor, vuelve a enviar los documentos con mejor calidad."""


def redactar_alerta_tthh(empleado_nombre: str, serial: str, empresa: str, checks_seleccionados: list, observaciones: str = "") -> str:
    """
    Redacta email de alerta para Talento Humano (presunto fraude)
    """
    
    problemas = []
    for check_key in checks_seleccionados:
        if check_key in CHECKS_DISPONIBLES:
            problemas.append(CHECKS_DISPONIBLES[check_key]['label'])
    
    problemas_texto = ", ".join(problemas) if problemas else "Inconsistencias detectadas"
    
    prompt = f"""Redacta un email FORMAL para el equipo de Talento Humano alertando sobre una incapacidad con posibles inconsistencias.

**Datos del caso:**
- Colaborador/a: {empleado_nombre}
- Empresa: {empresa}
- Serial: {serial}
- Problemas detectados: {problemas_texto}
- Observaciones adicionales: {observaciones if observaciones else 'Ninguna'}

**Requisitos:**
- Tono PROFESIONAL y OBJETIVO
- Máximo 250 palabras
- Estructura:
  1. Notificación del caso
  2. Listado de inconsistencias
  3. Solicitud de validación con la colaboradora
  4. Recordar confidencialidad del proceso
- NO hacer acusaciones directas
- Usar lenguaje neutral: "inconsistencias", "requiere validación"
- Formato: Solo cuerpo del mensaje

Responde ÚNICAMENTE con el contenido."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",
            max_tokens=500,
            temperature=0.5,  # Menos creativo, más formal
            messages=[{"role": "user", "content": prompt}]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Alerta TTHH redactada con IA para {serial}")
        return contenido
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"""Se ha detectado una incapacidad que requiere validación adicional.

**Datos del caso:**
- Colaborador/a: {empleado_nombre}
- Empresa: {empresa}
- Serial: {serial}
- Inconsistencias: {problemas_texto}

Por favor, realizar validación directa con la colaboradora para verificar la autenticidad de la documentación.

Recordamos que este proceso debe manejarse con confidencialidad."""


def redactar_recordatorio_7dias(nombre: str, serial: str, estado: str) -> str:
    """
    Redacta email de recordatorio después de 7 días sin respuesta
    """
    
    prompt = f"""Redacta un email de RECORDATORIO amable pero firme para {nombre} sobre su incapacidad pendiente (serial {serial}).

**Contexto:**
- Hace 7 días se le notificó que su incapacidad estaba {estado}
- Aún no ha enviado la documentación corregida
- Necesita completar el proceso para continuar

**Requisitos:**
- Tono amable pero urgente
- Máximo 150 palabras
- Recordar:
  * Cuánto tiempo ha pasado
  * Qué necesita enviar
  * Importancia de actuar pronto
- Ofrecer ayuda si tiene dudas
- Formato: Solo cuerpo del mensaje

Responde ÚNICAMENTE con el contenido."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",
            max_tokens=300,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Recordatorio 7 días redactado con IA para {serial}")
        return contenido
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"""Hace 7 días te notificamos que tu incapacidad (serial {serial}) requiere correcciones.

Aún no hemos recibido la documentación actualizada.

**Es importante que 
return f"""Hace 7 días te notificamos que tu incapacidad (serial {serial}) requiere correcciones.

Aún no hemos recibido la documentación actualizada.

**Es importante que completes este proceso lo antes posible** para poder continuar con la radicación.

Si tienes alguna duda sobre qué documentos necesitas enviar, no dudes en contactarnos.

Estamos para ayudarte."""


def redactar_alerta_jefe_7dias(jefe_nombre: str, empleado_nombre: str, serial: str, empresa: str) -> str:
    """
    Redacta email para el jefe después de 7 días sin respuesta del empleado
    """
    
    prompt = f"""Redacta un email PROFESIONAL para {jefe_nombre} (jefe/supervisor) informando sobre una incapacidad pendiente de su colaborador/a.

**Datos:**
- Colaborador/a: {empleado_nombre}
- Empresa: {empresa}
- Serial: {serial}
- Situación: Hace 7 días se solicitó documentación adicional, pero no se ha recibido respuesta

**Requisitos:**
- Tono PROFESIONAL y RESPETUOSO
- Máximo 200 palabras
- Solicitar apoyo para recordarle al colaborador/a
- Enfatizar importancia de completar el proceso
- Mencionar que esto puede afectar tiempos de radicación
- Ofrecer soporte si el empleado tiene dudas
- Formato: Solo cuerpo del mensaje

Responde ÚNICAMENTE con el contenido."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",
            max_tokens=400,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Alerta jefe 7 días redactada con IA para {serial}")
        return contenido
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"""Le informamos que su colaborador/a {empleado_nombre} tiene una incapacidad pendiente (serial {serial}) que requiere atención.

**Situación:**
Hace 7 días se le solicitó completar/corregir documentación, pero aún no hemos recibido respuesta.

**Solicitud:**
Agradeceríamos su apoyo para recordarle la importancia de completar este proceso, ya que está afectando los tiempos de radicación.

Si el colaborador/a tiene dudas sobre el proceso, estamos disponibles para brindar soporte.

Gracias por su colaboración."""


def redactar_mensaje_personalizado(nombre: str, serial: str, mensaje_libre: str) -> str:
    """
    Redacta email a partir de un mensaje libre del validador (botón Extra)
    """
    
    prompt = f"""Convierte el siguiente mensaje informal en un email profesional para {nombre} sobre su caso {serial}.

**Mensaje original del validador:**
{mensaje_libre}

**Requisitos:**
- Mantener el mensaje principal pero con redacción profesional
- Tono amable y claro
- Máximo 200 palabras
- Agregar estructura si es necesario
- NO cambiar el sentido del mensaje
- Formato: Solo cuerpo del mensaje

Responde ÚNICAMENTE con el contenido profesional."""

    try:
        message = client.messages.create(
            model="claude-haiku-3.5-20250219",
            max_tokens=400,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        
        contenido = message.content[0].text.strip()
        print(f"✅ Mensaje personalizado redactado con IA para {serial}")
        return contenido
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return mensaje_libre  # Fallback al mensaje original


# ==================== FUNCIONES DE ESTADÍSTICAS ====================

def obtener_stats_uso_ia():
    """
    Retorna estadísticas de uso de la IA (para monitoreo)
    """
    # Esto se puede implementar con una tabla en BD para trackear
    # Por ahora retorna un placeholder
    return {
        "emails_generados_hoy": 0,
        "costo_estimado_mes": "$2.70 USD",
        "modelo": "claude-haiku-3.5-20250219"
    }