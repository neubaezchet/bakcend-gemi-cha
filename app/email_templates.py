"""
Sistema de Templates de Email Unificado con Checklists Dinámicos
IncaNeurobaeza - 2024
"""

# ==================== PLANTILLA BASE ÚNICA ====================

def get_email_template_universal(
    tipo_email,  # 'confirmacion', 'incompleta', 'ilegible', 'eps', 'tthh', 'completa', 'falsa'
    nombre,
    serial,
    empresa,
    tipo_incapacidad,
    telefono,
    email,
    link_drive,
    checks_seleccionados=[],
    archivos_nombres=None,
    quinzena=None
):
    """
    PLANTILLA UNIVERSAL - Solo cambia contenido según tipo
    """
    
    # ========== CONFIGURACIÓN SEGÚN TIPO ==========
    configs = {
        'confirmacion': {
            'color_principal': '#667eea',
            'color_secundario': '#764ba2',
            'icono': '✅',
            'titulo': 'Recibido Confirmado',
            'mostrar_requisitos': True,
            'mostrar_boton_reenvio': False,
            'mostrar_plazo': False,
        },
        'incompleta': {
            'color_principal': '#ef4444',
            'color_secundario': '#dc2626',
            'icono': '❌',
            'titulo': 'Documentación Incompleta',
            'mostrar_requisitos': True,
            'mostrar_boton_reenvio': True,
            'mostrar_plazo': True,
        },
        'ilegible': {
            'color_principal': '#f59e0b',
            'color_secundario': '#d97706',
            'icono': '⚠️',
            'titulo': 'Documento Ilegible',
            'mostrar_requisitos': True,
            'mostrar_boton_reenvio': True,
            'mostrar_plazo': True,
        },
        'eps': {
            'color_principal': '#ca8a04',
            'color_secundario': '#a16207',
            'icono': '📋',
            'titulo': 'Transcripción en EPS Requerida',
            'mostrar_requisitos': False,
            'mostrar_boton_reenvio': True,
            'mostrar_plazo': False,
        },
        'completa': {
            'color_principal': '#16a34a',
            'color_secundario': '#15803d',
            'icono': '✅',
            'titulo': 'Incapacidad Validada',
            'mostrar_requisitos': False,
            'mostrar_boton_reenvio': False,
            'mostrar_plazo': False,
        },
        'tthh': {
            'color_principal': '#dc2626',
            'color_secundario': '#991b1b',
            'icono': '🚨',
            'titulo': 'ALERTA - Presunto Fraude',
            'mostrar_requisitos': True,
            'mostrar_boton_reenvio': False,
            'mostrar_plazo': False,
        },
        'falsa': {
            'color_principal': '#991b1b',
            'color_secundario': '#7f1d1d',
            'icono': '🚫',
            'titulo': 'Recibido Confirmado',
            'mostrar_requisitos': False,
            'mostrar_boton_reenvio': False,
            'mostrar_plazo': False,
        },
    }
    
    config = configs[tipo_email]
    
    # ========== GENERAR MENSAJE PRINCIPAL DINÁMICO ==========
    mensaje_principal = generar_mensaje_segun_tipo(tipo_email, checks_seleccionados, tipo_incapacidad, serial, quinzena, archivos_nombres)
    
    # ========== GENERAR LISTA DE REQUISITOS ==========
    requisitos_html = ''
    if config['mostrar_requisitos']:
        requisitos_html = generar_checklist_requisitos(tipo_incapacidad, checks_seleccionados, tipo_email)
    
    # ========== GENERAR SECCIONES ADICIONALES ==========
    seccion_ilegibilidad = generar_seccion_ilegibilidad() if 'ilegible' in tipo_email or any('ilegible' in c or 'recortada' in c or 'borrosa' in c for c in checks_seleccionados) else ''
    
    seccion_instrucciones = generar_instrucciones(tipo_email) if tipo_email in ['incompleta', 'ilegible'] else ''
    
    boton_reenvio = f'''
        <div style="text-align: center; margin: 30px 0;">
            <a href="https://example.com/reenviar/{serial}" 
               style="display: inline-block; background: linear-gradient(135deg, {config['color_principal']} 0%, {config['color_secundario']} 100%); 
                      color: white; padding: 16px 40px; text-decoration: none; border-radius: 25px; 
                      font-weight: bold; font-size: 16px; box-shadow: 0 4px 8px rgba(0,0,0,0.3);">
                🔄 Subir Documentos Corregidos
            </a>
        </div>
    ''' if config['mostrar_boton_reenvio'] else ''
    
    plazo_html = '''
        <div style="background: #fff3cd; border: 2px solid #ffc107; padding: 15px; border-radius: 8px; margin: 25px 0; text-align: center;">
            <p style="margin: 0; color: #856404; font-weight: bold;">
                ⏰ Por favor, envía la documentación corregida lo antes posible
            </p>
        </div>
    ''' if config['mostrar_plazo'] else ''
    
    # ========== PLANTILLA HTML COMPLETA ==========
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{config['titulo']} - {serial}</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 8px rgba(0,0,0,0.15);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, {config['color_principal']} 0%, {config['color_secundario']} 100%); color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0; font-size: 26px;">{config['icono']} {config['titulo']}</h1>
                <p style="margin: 5px 0 0 0; font-style: italic;">IncaNeurobaeza</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                <p style="font-size: 16px; color: #333;">
                    {'Estimado equipo de <strong>Talento Humano</strong>,' if tipo_email == 'tthh' else f'Hola <strong>{nombre}</strong>,'}
                </p>
                
                <!-- Mensaje Principal Dinámico -->
                {mensaje_principal}
                
                <!-- Detalles del Caso (Solo para TTHH) -->
                {generar_detalles_caso(serial, nombre, empresa, tipo_incapacidad, telefono, email) if tipo_email == 'tthh' else ''}
                
                <!-- Checklist de Requisitos -->
                {requisitos_html}
                
                <!-- Sección de Ilegibilidad -->
                {seccion_ilegibilidad}
                
                <!-- Instrucciones -->
                {seccion_instrucciones}
                
                <!-- Botón de Reenvío -->
                {boton_reenvio}
                
                <!-- Plazo -->
                {plazo_html}
                
                <!-- Link a Drive -->
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{link_drive}" style="color: #3b82f6; text-decoration: underline; font-size: 14px;">
                        📄 Ver documentos en Drive
                    </a>
                </div>
                
                <!-- Aviso WhatsApp (Solo confirmación e incompleta) -->
                {generar_aviso_wasap() if tipo_email in ['confirmacion', 'incompleta', 'ilegible'] else ''}
                
                <!-- Contacto -->
                <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #4b5563; font-size: 13px; text-align: center;">
                        📞 <strong>{telefono}</strong> &nbsp;|&nbsp; 📧 <strong>{email}</strong>
                    </p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background: #f8f9fa; padding: 20px; text-align: center; border-top: 1px solid #e9ecef;">
                <strong style="color: #667eea; font-size: 16px;">IncaNeurobaeza</strong>
                <div style="color: #6c757d; font-style: italic; margin-top: 5px; font-size: 14px;">
                    "Trabajando para ayudarte"
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ==================== FUNCIONES MODULARES ====================

def generar_mensaje_segun_tipo(tipo_email, checks, tipo_incapacidad, serial, quinzena=None, archivos_nombres=None):
    """Genera el mensaje principal según el tipo de email y checks"""
    
    if tipo_email == 'confirmacion':
        archivos_list = "<br>".join([f"• {archivo}" for archivo in (archivos_nombres or [])])
        return f'''
        <div style="background: #e3f2fd; border-left: 4px solid #2196f3; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #1565c0; font-weight: bold; font-size: 15px;">
                ✅ Confirmo recibido de la documentación
            </p>
            <p style="margin: 10px 0 0 0; color: #1976d2; line-height: 1.6;">
                Se procederá a realizar la revisión para validar que cumpla con los requisitos establecidos 
                para <strong>{tipo_incapacidad}</strong>.
            </p>
        </div>
        
        <div style="margin: 20px 0;">
            <h4 style="color: #333; margin-bottom: 10px;">📎 Documentos recibidos:</h4>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-size: 14px;">
                {archivos_list if archivos_list else '<em>No especificado</em>'}
            </div>
        </div>
        '''
    
    elif tipo_email == 'incompleta':
        explicacion = generar_explicacion_checks(checks)
        return f'''
        <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #991b1b; font-weight: bold; font-size: 15px;">
                ❌ No se pudo cargar la incapacidad {serial}
            </p>
            <p style="margin: 10px 0 0 0; color: #b91c1c; line-height: 1.6;">
                {explicacion}
            </p>
        </div>
        
        <div style="background: #fff3cd; border: 2px solid #ffc107; padding: 20px; border-radius: 8px; margin: 25px 0;">
            <p style="margin: 0; color: #856404; font-weight: bold; text-align: center;">
                Te recordamos revisar cuidadosamente que todos los documentos estén claros, completos y sin recortes antes de reenviarlos.
            </p>
        </div>
        '''
    
    elif tipo_email == 'ilegible':
        explicacion = generar_explicacion_checks(checks)
        return f'''
        <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #92400e; font-weight: bold; font-size: 15px;">
                ⚠️ Documento ilegible o con problemas de calidad
            </p>
            <p style="margin: 10px 0 0 0; color: #78350f; line-height: 1.6;">
                {explicacion}
            </p>
        </div>
        
        <div style="background: #fef3c7; border: 2px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 25px 0;">
            <h4 style="margin-top: 0; color: #92400e;">
                📸 Recomendaciones para tomar fotos claras:
            </h4>
            <ul style="color: #78350f; line-height: 1.8; margin: 10px 0;">
                <li>Usar buena iluminación (preferiblemente luz natural)</li>
                <li>Colocar el documento sobre una superficie plana</li>
                <li>Asegurarse de que <strong>todos los bordes</strong> sean visibles</li>
                <li>Evitar sombras, reflejos o dedos en la imagen</li>
                <li>Tomar la foto desde arriba, perpendicular al documento</li>
                <li>Verificar que el texto sea legible antes de enviar</li>
            </ul>
        </div>
        '''
    
    elif tipo_email == 'eps':
        return f'''
        <div style="background: #fef3c7; border-left: 4px solid #ca8a04; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #92400e; font-weight: bold; font-size: 15px;">
                📋 Transcripción en EPS requerida
            </p>
            <p style="margin: 10px 0 0 0; color: #78350f; line-height: 1.6;">
                Tu incapacidad requiere <strong>transcripción física en tu EPS</strong>. 
                Por favor, dirígete a tu EPS con tu documento de identidad y solicita la 
                transcripción de esta incapacidad. Una vez tengas el documento transcrito, 
                súbelo nuevamente al sistema.
            </p>
        </div>
        '''
    
    elif tipo_email == 'completa':
        return f'''
        <div style="background: #d1fae5; border: 2px solid #10b981; padding: 20px; margin: 20px 0; border-radius: 8px;">
            <p style="margin: 0; color: #065f46; font-weight: bold; font-size: 15px;">
                ✅ Tu incapacidad ha sido validada exitosamente
            </p>
            <p style="margin: 10px 0 0 0; color: #047857; line-height: 1.6;">
                Tu caso ha pasado al área de <strong>Radicación</strong> para el proceso final. 
                Nos comunicaremos contigo cuando el proceso esté completo.
            </p>
            <div style="text-align: center; margin: 20px 0; font-size: 24px;">
                📌 ➜ 🟢 ➜ ⚪
            </div>
            <p style="margin: 0; text-align: center; color: #059669; font-size: 12px;">
                Recepción → <strong>Validación</strong> → Radicación
            </p>
        </div>
        '''
    
    elif tipo_email == 'tthh':
        return f'''
        <div style="background: #fee2e2; border: 3px solid #ef4444; padding: 25px; margin: 20px 0; border-radius: 8px;">
            <h3 style="margin: 0 0 15px 0; color: #991b1b;">
                ⚠️ Incapacidad en Revisión por Presunto Fraude
            </h3>
            <p style="margin: 0; color: #b91c1c; font-size: 15px; line-height: 1.6;">
                La siguiente incapacidad presenta inconsistencias que requieren 
                <strong>validación adicional</strong> con la colaboradora.
            </p>
        </div>
        '''
    
    elif tipo_email == 'falsa':
        return f'''
        <div style="background: #e3f2fd; border-left: 4px solid #2196f3; padding: 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <p style="margin: 0; color: #1565c0; font-weight: bold; font-size: 15px;">
                ✅ Confirmo recibido de la documentación
            </p>
            <p style="margin: 10px 0 0 0; color: #1976d2; line-height: 1.6;">
                Se procederá a realizar la revisión correspondiente.
            </p>
        </div>
        '''
    
    return ""

def generar_explicacion_checks(checks):
    """Convierte los checks en explicación en lenguaje natural usando las descripciones actualizadas"""
    from app.checks_disponibles import CHECKS_DISPONIBLES
    
    mensajes = []
    for check_key in checks:
        if check_key in CHECKS_DISPONIBLES:
            mensajes.append(CHECKS_DISPONIBLES[check_key]['descripcion'])
    
    if not mensajes:
        return "Se encontró incompleta y requiere corrección."
    elif len(mensajes) == 1:
        return mensajes[0]
    else:
        # Unir con saltos de línea para mejor legibilidad
        return "<br><br>".join([f"• {msg}" for msg in mensajes])

def generar_checklist_requisitos(tipo_incapacidad, checks_faltantes, tipo_email):
    """Genera la checklist visual de requisitos"""
    
    # Definir requisitos completos por tipo
    requisitos_completos = {
        'Maternidad': [
            ('incapacidad', 'Incapacidad o licencia de maternidad', 'Documento oficial emitido por EPS con todas las páginas'),
            ('epicrisis', 'Epicrisis o resumen de atención', 'Documento completo con todas las páginas, sin recortes'),
            ('nacido_vivo', 'Certificado de nacido vivo', 'Original legible y sin recortes'),
            ('registro_civil', 'Registro civil del bebé', 'Completo y legible'),
        ],
        'Paternidad': [
            ('incapacidad', 'Incapacidad de paternidad', 'Documento oficial emitido por EPS'),
            ('epicrisis', 'Epicrisis o resumen de atención de la madre', 'Documento completo con todas las páginas'),
            ('cedula_padre', 'Cédula del padre', 'Ambas caras legibles'),
            ('nacido_vivo', 'Certificado de nacido vivo', 'Original legible'),
            ('registro_civil', 'Registro civil del bebé', 'Completo y legible'),
            ('licencia_maternidad', 'Licencia de maternidad de la madre (si trabaja)', 'Solo si la madre está activa laboralmente'),
        ],
        'Accidente de Tránsito': [
            ('incapacidad', 'Incapacidad médica', 'Documento oficial emitido por EPS con todas las páginas'),
            ('epicrisis', 'Epicrisis o resumen de atención', 'Documento completo, sin recortes'),
            ('furips', 'FURIPS (Formato Único de Reporte)', 'Completo y legible'),
            ('soat', 'SOAT del vehículo', 'Solo si el vehículo es identificado (no fantasma)'),
        ],
        'Enfermedad General': [
            ('incapacidad', 'Incapacidad médica', 'Documento oficial emitido por EPS con todas las páginas'),
            ('epicrisis', 'Epicrisis o resumen de atención', 'Requerido para incapacidades de 3 o más días'),
        ],
        'Enfermedad Laboral': [
            ('incapacidad', 'Incapacidad médica', 'Documento oficial emitido por ARL con todas las páginas'),
            ('epicrisis', 'Epicrisis o resumen de atención', 'Requerido para incapacidades de 3 o más días'),
        ],
    }
    
    requisitos = requisitos_completos.get(tipo_incapacidad, [])
    if not requisitos:
        return ''
    
    # Determinar el color del borde
    color_borde = '#fecaca' if tipo_email in ['incompleta', 'ilegible'] else '#e0f2fe'
    
    html = f'''
    <div style="background: white; border: 2px solid {color_borde}; padding: 25px; border-radius: 8px; margin: 25px 0;">
        <h3 style="margin-top: 0; color: #374151; border-bottom: 2px solid #d1d5db; padding-bottom: 10px;">
            📋 Requisitos para {tipo_incapacidad}
        </h3>
        <div style="font-size: 14px; line-height: 2;">
    '''
    
    for codigo, nombre, descripcion in requisitos:
        # Verificar si está en la lista de faltantes
        faltante = any(codigo in check for check in checks_faltantes)
        
        if faltante:
            # ❌ FALTANTE
            html += f'''
            <div style="display: flex; align-items: start; margin-bottom: 12px; background: #fee2e2; padding: 12px; border-radius: 6px;">
                <span style="color: #dc2626; font-size: 20px; margin-right: 10px;">❌</span>
                <div style="flex: 1;">
                    <strong style="color: #991b1b;">{nombre}</strong>
                    <div style="color: #b91c1c; font-size: 12px; margin-top: 4px;">
                        ({descripcion})
                    </div>
                </div>
            </div>
            '''
        else:
            # ✅ OK
            html += f'''
            <div style="display: flex; align-items: start; margin-bottom: 12px; background: #f0fdf4; padding: 12px; border-radius: 6px; opacity: 0.7;">
                <span style="color: #16a34a; font-size: 20px; margin-right: 10px;">✅</span>
                <div style="flex: 1;">
                    <strong style="color: #166534;">{nombre}</strong>
                    <div style="color: #15803d; font-size: 12px; margin-top: 4px;">
                        ({descripcion})
                    </div>
                </div>
            </div>
            '''
    
    html += '</div></div>'
    return html

def generar_seccion_ilegibilidad():
    """Genera consejos para fotos claras"""
    return '''
    <div style="background: #fef3c7; border: 2px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 25px 0;">
        <h4 style="margin-top: 0; color: #92400e;">
            📸 Recomendaciones para tomar fotos claras:
        </h4>
        <ul style="color: #78350f; line-height: 1.8; margin: 10px 0;">
            <li>Usar buena iluminación (preferiblemente luz natural)</li>
            <li>Colocar el documento sobre una superficie plana</li>
            <li>Asegurarse de que <strong>todos los bordes</strong> sean visibles</li>
            <li>Evitar sombras, reflejos o dedos en la imagen</li>
            <li>Tomar la foto desde arriba, perpendicular al documento</li>
            <li>Verificar que el texto sea legible antes de enviar</li>
        </ul>
    </div>
    '''

def generar_instrucciones(tipo_email):
    """Genera instrucciones claras para corrección"""
    return '''
    <div style="background: #dbeafe; border: 2px solid #3b82f6; padding: 20px; border-radius: 8px; margin: 25px 0;">
        <h4 style="margin-top: 0; color: #1e40af;">📝 Qué debes hacer:</h4>
        <ol style="color: #1e3a8a; line-height: 1.8; margin: 10px 0; padding-left: 20px;">
            <li><strong>Adjunta nuevamente la incapacidad COMPLETA y LEGIBLE</strong></li>
            <li>Verifica que <strong>TODOS los bordes</strong> de los documentos sean visibles</li>
            <li>Asegúrate de que la <strong>información sea clara</strong>, sin recortes ni manchas</li>
            <li>Incluye <strong>TODOS</strong> los documentos marcados arriba como faltantes (❌)</li>
        </ol>
    </div>
    '''

def generar_aviso_wasap():
    """Genera aviso de estar pendiente primero por WhatsApp"""
    return '''
    <div style="background: #fff3cd; border: 2px solid #ffc107; padding: 20px; border-radius: 8px; margin: 25px 0;">
        <p style="margin: 0; color: #856404; font-weight: bold; text-align: center; font-size: 15px;">
            ⚠️ IMPORTANTE: Estar pendiente
        </p>
        <p style="margin: 10px 0 0 0; color: #856404; text-align: center;">
            <strong>📱 Primero vía WhatsApp</strong> y luego por <strong>📧 correo electrónico</strong>
        </p>
        <p style="margin: 10px 0 0 0; color: #856404; text-align: center; font-size: 13px;">
            para seguir en el proceso de radicación o para notificación de correcciones necesarias.
        </p>
    </div>
    '''

def generar_detalles_caso(serial, nombre, empresa, tipo_incapacidad, telefono, email):
    """Genera tabla de detalles del caso (para TTHH)"""
    return f'''
    <div style="background: #f8f9fa; border: 2px solid #dee2e6; padding: 20px; border-radius: 8px; margin: 25px 0;">
        <h4 style="margin-top: 0; color: #495057; border-bottom: 2px solid #6c757d; padding-bottom: 10px;">
            📋 Información del Caso
        </h4>
        <table style="width: 100%; font-size: 14px;">
            <tr>
                <td style="padding: 8px 0; color: #666; font-weight: bold; width: 180px;">Serial:</td>
                <td style="padding: 8px 0; color: #333;"><strong style="color: #dc2626;">{serial}</strong></td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: #666; font-weight: bold;">Colaboradora:</td>
                <td style="padding: 8px 0; color: #333;">{nombre}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; color: #666; font-weight: bold;">Empresa:</t