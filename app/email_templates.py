def get_confirmation_template(nombre, consecutivo, empresa, quinzena, link_pdf, archivos_nombres, email_contacto, telefono):
    """Template HTML para confirmación de recepción de incapacidad"""
    archivos_list = "<br>".join([f"• {archivo}" for archivo in archivos_nombres])
    
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Confirmación Incapacidad</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 28px; font-weight: bold;">IncaNeurobaeza</h1>
                <p style="margin: 5px 0 0 0; font-style: italic; opacity: 0.9;">"Trabajando para ayudarte"</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 40px 30px;">
                <h2 style="color: #333; margin-bottom: 20px;">Buen día, {nombre}</h2>
                
                <div style="background: #f8f9fa; padding: 20px; border-left: 4px solid #667eea; margin: 25px 0; border-radius: 0 5px 5px 0;">
                    <p style="margin: 0; color: #333; line-height: 1.6;">
                        <strong>Confirmo recibido de la documentación correspondiente</strong> y procederemos a <strong>realizar la revisión</strong>. 
                        En caso de que cumpla con los requisitos establecidos, se realizará la carga en el sistema <strong>{quinzena}</strong>.
                    </p>
                </div>
                
                <div style="background: white; border: 1px solid #e9ecef; padding: 20px; border-radius: 8px; margin: 25px 0;">
                    <h3 style="margin-top: 0; color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px;">Detalles del Registro</h3>
                    <table style="width: 100%; font-size: 14px;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Consecutivo:</td>
                            <td style="padding: 8px 0; color: #333;">{consecutivo}</td>
                            <td rowspan="4" style="text-align: center; vertical-align: middle; width: 80px;">
                                <img src="https://api.qrserver.com/v1/create-qr-code/?size=70x70&data={consecutivo}" alt="QR Code" style="border: 1px solid #ddd; border-radius: 4px;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Empresa:</td>
                            <td style="padding: 8px 0; color: #333;">{empresa}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Email contacto:</td>
                            <td style="padding: 8px 0; color: #333;">{email_contacto}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Teléfono:</td>
                            <td style="padding: 8px 0; color: #333;">{telefono}</td>
                        </tr>
                    </table>
                </div>
                
                <div style="margin: 25px 0;">
                    <h4 style="color: #333; margin-bottom: 15px;">📋 Documentos recibidos:</h4>
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; font-size: 14px; line-height: 1.5;">
                        {archivos_list}
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{link_pdf}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                        📄 Ver Documentos Combinados
                    </a>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeeba; padding: 20px; border-radius: 8px; margin: 25px 0;">
                    <p style="margin: 0; color: #856404; text-align: center; font-weight: bold;">
                        ⚠️ Estar pendiente vía WhatsApp y correo para seguir en el proceso de radicación si llegase a cumplir los requisitos establecidos, 
                        del contrario se notificará para su debida gestión.
                    </p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background: #f8f9fa; padding: 25px; text-align: center; border-top: 1px solid #e9ecef;">
                <div style="margin-bottom: 15px;">
                    <strong style="color: #667eea; font-size: 18px;">IncaNeurobaeza</strong>
                </div>
                <div style="color: #6c757d; font-style: italic; margin-bottom: 10px;">
                    "Trabajando para ayudarte"
                </div>
                <div style="font-size: 12px; color: #6c757d; line-height: 1.4;">
                    Este es un mensaje automático de confirmación<br>
                    Para consultas adicionales, responder a este correo
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def get_alert_template(tipo, cedula, consecutivo, email_contacto, telefono, nombre=None, empresa=None, link_pdf=None, archivos_nombres=None, quinzena=None):
    """Template HTML para alertas a supervisión"""
    
    if tipo == "copia":
        titulo = "Copia Registro de Incapacidad"
        contenido_principal = f"""
        <div style="background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="color: #155724; margin-top: 0;">✅ Empleado Registrado - {empresa}</h3>
            <p style="margin: 0; color: #155724;">Se ha procesado exitosamente la incapacidad del empleado <strong>{nombre}</strong>.</p>
        </div>
        
        <div style="background: white; border: 1px solid #e9ecef; padding: 20px; border-radius: 8px; margin: 25px 0;">
            <h4 style="margin-top: 0; color: #667eea;">Información del Empleado</h4>
            <table style="width: 100%; font-size: 14px;">
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Nombre:</td>
                    <td style="padding: 8px 0; color: #333;">{nombre}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Cédula:</td>
                    <td style="padding: 8px 0; color: #333;">{cedula}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Empresa:</td>
                    <td style="padding: 8px 0; color: #333;">{empresa}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Email contacto:</td>
                    <td style="padding: 8px 0; color: #333;">{email_contacto}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Teléfono:</td>
                    <td style="padding: 8px 0; color: #333;">{telefono}</td>
                </tr>
            </table>
        </div>
        
        <div style="margin: 25px 0;">
            <h4 style="color: #333; margin-bottom: 15px;">📋 Documentos procesados:</h4>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; font-size: 14px; line-height: 1.5;">
                {'<br>'.join([f"• {archivo}" for archivo in archivos_nombres]) if archivos_nombres else 'No especificado'}
            </div>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{link_pdf}" style="display: inline-block; background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                📄 Ver Documentos en Drive
            </a>
        </div>
        """
    
    else:  # alerta
        titulo = "⚠️ ALERTA: Cédula No Encontrada"
        contenido_principal = f"""
        <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="color: #721c24; margin-top: 0;">⚠️ Cédula No Registrada</h3>
            <p style="margin: 0; color: #721c24;">Se ha recibido documentación de una cédula no encontrada en la base de datos.</p>
        </div>
        
        <div style="background: white; border: 1px solid #e9ecef; padding: 20px; border-radius: 8px; margin: 25px 0;">
            <h4 style="margin-top: 0; color: #dc3545;">Datos de la Solicitud</h4>
            <table style="width: 100%; font-size: 14px;">
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Cédula:</td>
                    <td style="padding: 8px 0; color: #333; font-weight: bold;">{cedula}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Email contacto:</td>
                    <td style="padding: 8px 0; color: #333;">{email_contacto}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Teléfono:</td>
                    <td style="padding: 8px 0; color: #333;">{telefono}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666; font-weight: bold;">Fecha recepción:</td>
                    <td style="padding: 8px 0; color: #333;">{quinzena}</td>
                </tr>
            </table>
        </div>
        
        <div style="background: #fff3cd; border: 1px solid #ffeeba; padding: 20px; border-radius: 8px; margin: 25px 0;">
            <p style="margin: 0; color: #856404; text-align: center; font-weight: bold;">
                🔍 ACCIÓN REQUERIDA: Validar información y contactar al solicitante
            </p>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{titulo}</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: bold;">IncaNeurobaeza - Supervisión</h1>
                <p style="margin: 5px 0 0 0; font-style: italic; opacity: 0.9;">Sistema de Gestión</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                <h2 style="color: #333; margin-bottom: 20px;">{titulo}</h2>
                
                <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0;">
                    <strong>Consecutivo:</strong> {consecutivo}
                </div>
                
                {contenido_principal}
            </div>
            
            <!-- Footer -->
            <div style="background: #f8f9fa; padding: 20px; text-align: center; border-top: 1px solid #e9ecef;">
                <div style="font-size: 12px; color: #6c757d;">
                    Sistema Automático IncaNeurobaeza<br>
                    Notificación de supervisión
                </div>
            </div>
        </div>
    </body>
    </html>
    """