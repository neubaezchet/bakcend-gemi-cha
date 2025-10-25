"""
Códigos de Checks Disponibles para el Sistema de Validación
IncaNeurobaeza - 2024
"""

# Diccionario completo de checks disponibles
CHECKS_DISPONIBLES = {
    # ========== DOCUMENTOS FALTANTES ==========
    'incapacidad_faltante': {
        'label': 'Falta soporte de incapacidad',
        'descripcion': 'El documento adjunto no es válido como soporte oficial de incapacidad',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'epicrisis_faltante': {
        'label': 'Falta epicrisis/resumen',
        'descripcion': 'No se adjuntó la epicrisis o resumen de atención',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'epicrisis_incompleta': {
        'label': 'Epicrisis incompleta',
        'descripcion': 'La epicrisis no incluye todas las páginas',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'soat_faltante': {
        'label': 'Falta SOAT',
        'descripcion': 'No se adjuntó el SOAT del vehículo',
        'aplica_tipos': ['Accidente de Tránsito']
    },
    'furips_faltante': {
        'label': 'Falta FURIPS',
        'descripcion': 'No se adjuntó el FURIPS (Formato Único de Reporte)',
        'aplica_tipos': ['Accidente de Tránsito']
    },
    'licencia_maternidad_faltante': {
        'label': 'Falta licencia maternidad',
        'descripcion': 'No se adjuntó la licencia de maternidad de la madre',
        'aplica_tipos': ['Paternidad']
    },
    'registro_civil_faltante': {
        'label': 'Falta registro civil',
        'descripcion': 'No se adjuntó el registro civil del bebé',
        'aplica_tipos': ['Maternidad', 'Paternidad']
    },
    'nacido_vivo_faltante': {
        'label': 'Falta certificado nacido vivo',
        'descripcion': 'No se adjuntó el certificado de nacido vivo',
        'aplica_tipos': ['Maternidad', 'Paternidad']
    },
    'cedula_padre_faltante': {
        'label': 'Falta cédula del padre',
        'descripcion': 'No se adjuntó la cédula del padre (ambas caras)',
        'aplica_tipos': ['Paternidad']
    },
    
    # ========== PROBLEMAS DE LEGIBILIDAD ==========
    'ilegible_recortada': {
        'label': 'Documento recortado',
        'descripcion': 'No se aprecian todos los bordes del documento',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'ilegible_borrosa': {
        'label': 'Documento borroso',
        'descripcion': 'La imagen tiene baja calidad o está desenfocada',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'ilegible_manchada': {
        'label': 'Documento manchado/dañado',
        'descripcion': 'El documento tiene manchas, está dañado o no es legible',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    
    # ========== PARA TALENTO HUMANO ==========
    'solicitar_epicrisis_tthh': {
        'label': 'Solicitar epicrisis a colaboradora',
        'descripcion': 'TTHH debe solicitar directamente la epicrisis',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
    'solicitar_transcripcion_tthh': {
        'label': 'Solicitar transcripción EPS',
        'descripcion': 'TTHH debe solicitar que se transcriba en la EPS',
        'aplica_tipos': ['Maternidad', 'Paternidad', 'Accidente de Tránsito', 'Enfermedad General', 'Enfermedad Laboral']
    },
}

def obtener_checks_por_tipo(tipo_incapacidad):
    """
    Retorna solo los checks que aplican para un tipo de incapacidad específico
    
    Args:
        tipo_incapacidad (str): Tipo de incapacidad
        
    Returns:
        dict: Diccionario con los checks aplicables
    """
    return {
        key: value for key, value in CHECKS_DISPONIBLES.items()
        if tipo_incapacidad in value['aplica_tipos']
    }

def obtener_checks_documentos(tipo_incapacidad):
    """Retorna solo checks relacionados con documentos faltantes"""
    checks = obtener_checks_por_tipo(tipo_incapacidad)
    return {k: v for k, v in checks.items() 
            if 'faltante' in k or 'incompleta' in k}

def obtener_checks_legibilidad(tipo_incapacidad):
    """Retorna solo checks relacionados con legibilidad"""
    checks = obtener_checks_por_tipo(tipo_incapacidad)
    return {k: v for k, v in checks.items() if 'ilegible' in k}

def obtener_checks_tthh(tipo_incapacidad):
    """Retorna solo checks para Talento Humano"""
    checks = obtener_checks_por_tipo(tipo_incapacidad)
    return {k: v for k, v in checks.items() if 'tthh' in k}