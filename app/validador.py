"""
Router del Portal de Validadores - IncaNeurobaeza
Endpoints para gestión, validación y búsqueda de casos
"""

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import pandas as pd
import io

from app.database import (
    get_db, Case, CaseDocument, CaseEvent, CaseNote, Employee, 
    Company, SearchHistory, EstadoCaso, EstadoDocumento, TipoIncapacidad
)

router = APIRouter(prefix="/validador", tags=["Portal de Validadores"])

# ==================== MODELOS PYDANTIC ====================

class FiltrosCasos(BaseModel):
    empresa: Optional[str] = None
    estado: Optional[str] = None
    tipo: Optional[str] = None
    q: Optional[str] = None  # Búsqueda general
    page: int = 1
    page_size: int = 20

class CambioEstado(BaseModel):
    estado: str
    motivo: Optional[str] = None
    documentos: Optional[List[Dict]] = None  # [{"doc": "epicrisis", "estado_doc": "INCOMPLETO"}]
    fecha_limite: Optional[str] = None

class NotaRapida(BaseModel):
    contenido: str
    es_importante: bool = False

class BusquedaRelacional(BaseModel):
    """Modelo para búsqueda relacional avanzada"""
    cedula: Optional[str] = None
    serial: Optional[str] = None
    nombre: Optional[str] = None
    tipo_incapacidad: Optional[str] = None
    eps: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None

class BusquedaRelacionalRequest(BaseModel):
    filtros_globales: Optional[Dict[str, Any]] = None
    registros: List[BusquedaRelacional]

# ==================== UTILIDADES ====================

def verificar_token_admin(x_admin_token: str = Header(...)):
    """Verifica que el token de administrador sea válido"""
    import os
    admin_token = os.environ.get("ADMIN_TOKEN")
    
    if not admin_token:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN no configurado en el servidor")
    
    if x_admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Token de administrador inválido")
    
    return True

def registrar_evento(db: Session, case_id: int, accion: str, actor: str = "Sistema", 
                     estado_anterior: str = None, estado_nuevo: str = None, 
                     motivo: str = None, metadata: dict = None):
    """Registra un evento en el historial del caso"""
    evento = CaseEvent(
        case_id=case_id,
        actor=actor,
        accion=accion,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        motivo=motivo,
        metadata_json=metadata
    )
    db.add(evento)
    db.commit()

# ==================== ENDPOINTS ====================

@router.get("/casos")
async def listar_casos(
    empresa: Optional[str] = None,
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Lista casos con filtros avanzados
    
    - **empresa**: Nombre de la empresa (opcional)
    - **estado**: Estado del caso (opcional)
    - **tipo**: Tipo de incapacidad (opcional)
    - **q**: Búsqueda general (serial/cédula/nombre)
    - **page**: Número de página (default: 1)
    - **page_size**: Tamaño de página (default: 20)
    """
    
    query = db.query(Case)
    
    # Filtro por empresa
    if empresa and empresa != "all":
        company = db.query(Company).filter(Company.nombre == empresa).first()
        if company:
            query = query.filter(Case.company_id == company.id)
    
    # Filtro por estado
    if estado and estado != "all":
        query = query.filter(Case.estado == estado)
    
    # Filtro por tipo
    if tipo and tipo != "all":
        query = query.filter(Case.tipo == tipo)
    
    # Búsqueda general (serial, cédula o nombre)
    if q:
        query = query.join(Employee, Case.employee_id == Employee.id, isouter=True)
        query = query.filter(
            or_(
                Case.serial.ilike(f"%{q}%"),
                Case.cedula.ilike(f"%{q}%"),
                Employee.nombre.ilike(f"%{q}%")
            )
        )
    
    # Contar total antes de paginar
    total = query.count()
    
    # Paginación
    offset = (page - 1) * page_size
    casos = query.order_by(Case.created_at.desc()).offset(offset).limit(page_size).all()
    
    # Formatear respuesta
    items = []
    for caso in casos:
        empleado = caso.empleado if caso.empleado else None
        empresa_obj = caso.empresa if caso.empresa else None
        
        items.append({
            "id": caso.id,
            "serial": caso.serial,
            "cedula": caso.cedula,
            "nombre": empleado.nombre if empleado else "No registrado",
            "empresa": empresa_obj.nombre if empresa_obj else "Otra empresa",
            "tipo": caso.tipo.value if caso.tipo else None,
            "estado": caso.estado.value,
            "created_at": caso.created_at.isoformat(),
            "bloquea_nueva": caso.bloquea_nueva
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.get("/casos/{serial}")
async def detalle_caso(
    serial: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Obtiene el detalle completo de un caso"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    empleado = caso.empleado
    empresa = caso.empresa
    documentos = caso.documentos
    eventos = db.query(CaseEvent).filter(CaseEvent.case_id == caso.id).order_by(CaseEvent.created_at.desc()).all()
    notas = db.query(CaseNote).filter(CaseNote.case_id == caso.id).order_by(CaseNote.created_at.desc()).all()
    
    return {
        "serial": caso.serial,
        "cedula": caso.cedula,
        "nombre": empleado.nombre if empleado else "No registrado",
        "empresa": empresa.nombre if empresa else "Otra empresa",
        "tipo": caso.tipo.value if caso.tipo else None,
        "subtipo": caso.subtipo,
        "dias_incapacidad": caso.dias_incapacidad,
        "estado": caso.estado.value,
        "eps": caso.eps,
        "fecha_inicio": caso.fecha_inicio.isoformat() if caso.fecha_inicio else None,
        "fecha_fin": caso.fecha_fin.isoformat() if caso.fecha_fin else None,
        "diagnostico": caso.diagnostico,
        "metadata_form": caso.metadata_form,
        "bloquea_nueva": caso.bloquea_nueva,
        "drive_link": caso.drive_link,
        "email_form": caso.email_form,
        "telefono_form": caso.telefono_form,
        "created_at": caso.created_at.isoformat(),
        "updated_at": caso.updated_at.isoformat(),
        "documentos": [
            {
                "id": doc.id,
                "doc_tipo": doc.doc_tipo,
                "requerido": doc.requerido,
                "estado_doc": doc.estado_doc.value,
                "drive_urls": doc.drive_urls,
                "version_actual": doc.version_actual,
                "observaciones": doc.observaciones
            }
            for doc in documentos
        ],
        "historial": [
            {
                "id": ev.id,
                "actor": ev.actor,
                "accion": ev.accion,
                "estado_anterior": ev.estado_anterior,
                "estado_nuevo": ev.estado_nuevo,
                "motivo": ev.motivo,
                "created_at": ev.created_at.isoformat()
            }
            for ev in eventos
        ],
        "notas": [
            {
                "id": nota.id,
                "autor": nota.autor,
                "contenido": nota.contenido,
                "es_importante": nota.es_importante,
                "created_at": nota.created_at.isoformat()
            }
            for nota in notas
        ]
    }

@router.post("/casos/{serial}/estado")
async def cambiar_estado(
    serial: str,
    cambio: CambioEstado,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Cambia el estado de un caso y envía notificaciones
    
    Estados posibles:
    - INCOMPLETA / ILEGIBLE / INCOMPLETA_ILEGIBLE
    - EPS_TRANSCRIPCION
    - DERIVADO_TTHH
    - CAUSA_EXTRA
    - COMPLETA
    """
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    estado_anterior = caso.estado.value
    nuevo_estado = cambio.estado
    
    # Validar estado
    try:
        EstadoCaso(nuevo_estado)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {nuevo_estado}")
    
    # Actualizar estado del caso
    caso.estado = EstadoCaso(nuevo_estado)
    
    # Actualizar documentos si se proporcionan
    if cambio.documentos:
        for doc_data in cambio.documentos:
            doc = db.query(CaseDocument).filter(
                CaseDocument.case_id == caso.id,
                CaseDocument.doc_tipo == doc_data.get("doc")
            ).first()
            
            if doc:
                doc.estado_doc = EstadoDocumento(doc_data.get("estado_doc", "PENDIENTE"))
                doc.observaciones = cambio.motivo
    
    # Registrar evento
    registrar_evento(
        db, caso.id, "cambio_estado", 
        actor="Validador",
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado,
        motivo=cambio.motivo,
        metadata={"fecha_limite": cambio.fecha_limite} if cambio.fecha_limite else None
    )
    
    # Actualizar bloqueo si es INCOMPLETA
    if nuevo_estado in ["INCOMPLETA", "ILEGIBLE", "INCOMPLETA_ILEGIBLE"]:
        caso.bloquea_nueva = True
    
    db.commit()
    
    # TODO: Aquí enviar emails con las plantillas correspondientes
    # usando el sistema de Brevo que ya tienes en email_templates.py
    
    return {
        "status": "ok",
        "serial": serial,
        "estado_anterior": estado_anterior,
        "estado_nuevo": nuevo_estado,
        "mensaje": f"Estado actualizado a {nuevo_estado}"
    }

@router.post("/casos/{serial}/autorizar-nueva")
async def autorizar_nueva_incapacidad(
    serial: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Autoriza que el trabajador pueda subir una nueva incapacidad (bloqueo híbrido)"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    caso.bloquea_nueva = False
    
    registrar_evento(
        db, caso.id, "autorizacion_nueva",
        actor="Validador",
        motivo="Se autorizó al trabajador para subir una nueva incapacidad distinta"
    )
    
    db.commit()
    
    return {
        "status": "ok",
        "serial": serial,
        "mensaje": "Trabajador autorizado para subir nueva incapacidad"
    }

@router.post("/casos/{serial}/nota")
async def agregar_nota(
    serial: str,
    nota: NotaRapida,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Agrega una nota rápida al caso (Mejora: Quick notes)"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    nueva_nota = CaseNote(
        case_id=caso.id,
        autor="Validador",  # TODO: Obtener de JWT cuando implementes auth
        contenido=nota.contenido,
        es_importante=nota.es_importante
    )
    
    db.add(nueva_nota)
    db.commit()
    
    return {
        "status": "ok",
        "nota_id": nueva_nota.id,
        "mensaje": "Nota agregada exitosamente"
    }

@router.get("/stats")
async def obtener_estadisticas(
    empresa: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Obtiene estadísticas para el dashboard"""
    
    query = db.query(Case)
    
    if empresa and empresa != "all":
        company = db.query(Company).filter(Company.nombre == empresa).first()
        if company:
            query = query.filter(Case.company_id == company.id)
    
    # Contar por estado
    stats = {
        "total_casos": query.count(),
        "por_estado": {},
        "por_tipo": {},
        "ultimos_7_dias": 0
    }
    
    # Agrupar por estado
    for estado in EstadoCaso:
        count = query.filter(Case.estado == estado).count()
        stats["por_estado"][estado.value] = count
    
    # Agrupar por tipo
    for tipo in TipoIncapacidad:
        count = query.filter(Case.tipo == tipo).count()
        stats["por_tipo"][tipo.value] = count
    
    # Casos de últimos 7 días
    hace_7_dias = datetime.utcnow() - timedelta(days=7)
    stats["ultimos_7_dias"] = query.filter(Case.created_at >= hace_7_dias).count()
    
    return stats

@router.get("/reglas/requisitos")
async def obtener_requisitos_documentos(
    tipo: str,
    dias: Optional[int] = None,
    vehiculo_fantasma: Optional[bool] = None,
    madre_trabaja: Optional[bool] = None,
    es_prorroga: bool = False,
    db: Session = Depends(get_db)
):
    """
    Motor de reglas dinámico: calcula documentos requeridos según contexto
    
    Este endpoint NO persiste, solo calcula y responde
    """
    
    documentos_requeridos = []
    mensajes = []
    
    if tipo == "enfermedad_general":
        documentos_requeridos.append({"doc": "incapacidad_medica", "requerido": True, "aplica": True})
        
        if dias and dias >= 3:
            documentos_requeridos.append({"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True})
            mensajes.append("Enfermedad general ≥3 días requiere epicrisis o resumen clínico")
        else:
            mensajes.append("1-2 días: solo incapacidad médica (salvo validación manual)")
    
    elif tipo == "enfermedad_laboral":
        documentos_requeridos.append({"doc": "incapacidad_medica", "requerido": True, "aplica": True})
        
        if dias and dias >= 3:
            documentos_requeridos.append({"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True})
            mensajes.append("Enfermedad laboral ≥3 días requiere epicrisis o resumen clínico")
    
    elif tipo == "accidente_transito":
        documentos_requeridos.append({"doc": "incapacidad_medica", "requerido": True, "aplica": True})
        documentos_requeridos.append({"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True})
        documentos_requeridos.append({"doc": "furips", "requerido": True, "aplica": True})
        
        if vehiculo_fantasma:
            documentos_requeridos.append({"doc": "soat", "requerido": False, "aplica": False})
            mensajes.append("Vehículo fantasma: no se requiere SOAT")
        else:
            documentos_requeridos.append({"doc": "soat", "requerido": True, "aplica": True})
            mensajes.append("Vehículo identificado: SOAT obligatorio")
    
    elif tipo == "especial":
        documentos_requeridos.append({"doc": "incapacidad_medica", "requerido": True, "aplica": True})
        documentos_requeridos.append({"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True})
    
    elif tipo == "maternidad":
        documentos_requeridos.extend([
            {"doc": "licencia_o_incapacidad", "requerido": True, "aplica": True},
            {"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True},
            {"doc": "nacido_vivo", "requerido": True, "aplica": True},
            {"doc": "registro_civil", "requerido": True, "aplica": True}
        ])
        mensajes.append("Maternidad: 4 documentos básicos obligatorios")
    
    elif tipo == "paternidad":
        documentos_requeridos.extend([
            {"doc": "epicrisis_o_resumen_clinico", "requerido": True, "aplica": True},
            {"doc": "cedula_padre", "requerido": True, "aplica": True},
            {"doc": "nacido_vivo", "requerido": True, "aplica": True},
            {"doc": "registro_civil", "requerido": True, "aplica": True}
        ])
        
        if madre_trabaja:
            documentos_requeridos.append({"doc": "licencia_maternidad", "requerido": True, "aplica": True})
            mensajes.append("Madre trabaja: licencia de maternidad obligatoria")
        else:
            documentos_requeridos.append({"doc": "licencia_maternidad", "requerido": False, "aplica": False})
            mensajes.append("Madre no trabaja: licencia de maternidad no requerida")
    
    return {
        "documentos": documentos_requeridos,
        "mensajes": mensajes
    }

# ==================== BÚSQUEDA RELACIONAL AVANZADA ====================

@router.post("/busqueda-relacional")
async def busqueda_relacional(
    request: BusquedaRelacionalRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    🔍 BÚSQUEDA RELACIONAL AVANZADA
    
    Permite buscar casos por combinaciones flexibles de campos:
    - Cédula, Serial, Nombre, Tipo, EPS, Fechas
    - Soporta filtros globales aplicables a todos los registros
    - Construye WHERE dinámicamente según campos presentes
    """
    
    resultados = []
    filtros_globales = request.filtros_globales or {}
    
    for registro in request.registros:
        query = db.query(Case).join(Employee, Case.employee_id == Employee.id, isouter=True)
        
        # Aplicar filtros del registro individual
        if registro.cedula:
            query = query.filter(Case.cedula == registro.cedula)
        
        if registro.serial:
            query = query.filter(Case.serial == registro.serial)
        
        if registro.nombre:
            query = query.filter(Employee.nombre.ilike(f"%{registro.nombre}%"))
        
        if registro.tipo_incapacidad:
            query = query.filter(Case.tipo == registro.tipo_incapacidad)
        
        if registro.eps:
            query = query.filter(Case.eps.ilike(f"%{registro.eps}%"))
        
        # Filtros de fechas (rango o individual)
        if registro.fecha_inicio and registro.fecha_fin:
            fecha_inicio_dt = datetime.fromisoformat(registro.fecha_inicio)
            fecha_fin_dt = datetime.fromisoformat(registro.fecha_fin)
            query = query.filter(
                and_(
                    Case.fecha_inicio >= fecha_inicio_dt,
                    Case.fecha_fin <= fecha_fin_dt
                )
            )
        elif registro.fecha_inicio:
            fecha_inicio_dt = datetime.fromisoformat(registro.fecha_inicio)
            query = query.filter(Case.fecha_inicio >= fecha_inicio_dt)
        elif registro.fecha_fin:
            fecha_fin_dt = datetime.fromisoformat(registro.fecha_fin)
            query = query.filter(Case.fecha_fin <= fecha_fin_dt)
        
        # Aplicar filtros globales
        if filtros_globales.get("empresa"):
            company = db.query(Company).filter(Company.nombre == filtros_globales["empresa"]).first()
            if company:
                query = query.filter(Case.company_id == company.id)
        
        if filtros_globales.get("tipo_documento"):
            # Buscar casos que tengan al menos uno de los documentos especificados
            tipos_docs = filtros_globales["tipo_documento"]
            query = query.join(CaseDocument).filter(CaseDocument.doc_tipo.in_(tipos_docs))
        
        # Ejecutar query
        casos = query.all()
        
        for caso in casos:
            empleado = caso.empleado
            empresa = caso.empresa
            
            # Obtener documentos del caso
            documentos = db.query(CaseDocument).filter(CaseDocument.case_id == caso.id).all()
            
            resultados.append({
                "cedula": caso.cedula,
                "nombre": empleado.nombre if empleado else "No registrado",
                "serial": caso.serial,
                "tipo_incapacidad": caso.tipo.value if caso.tipo else None,
                "eps": caso.eps,
                "fecha_inicio": caso.fecha_inicio.isoformat() if caso.fecha_inicio else None,
                "fecha_fin": caso.fecha_fin.isoformat() if caso.fecha_fin else None,
                "empresa": empresa.nombre if empresa else None,
                "estado": caso.estado.value,
                "documentos": [
                    {
                        "doc_tipo": doc.doc_tipo,
                        "estado_doc": doc.estado_doc.value,
                        "drive_urls": doc.drive_urls
                    }
                    for doc in documentos
                ]
            })
    
    # Registrar búsqueda en historial para auditoría
    historial = SearchHistory(
        usuario="Validador",  # TODO: Obtener de JWT
        tipo_busqueda="relacional",
        parametros_json={
            "filtros_globales": filtros_globales,
            "total_registros": len(request.registros)
        },
        resultados_count=len(resultados)
    )
    db.add(historial)
    db.commit()
    
    return {
        "resultados": resultados,
        "total_encontrados": len(resultados),
        "registros_buscados": len(request.registros)
    }

@router.post("/busqueda-relacional/excel")
async def busqueda_relacional_desde_excel(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    📊 BÚSQUEDA RELACIONAL DESDE EXCEL
    
    Sube un archivo Excel/CSV con columnas flexibles:
    - Detecta automáticamente columnas por nombre aproximado
    - No requiere plantilla fija
    - Convierte fechas automáticamente
    """
    
    # Leer archivo
    contents = await archivo.read()
    
    try:
        # Intentar leer como Excel
        if archivo.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        elif archivo.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Formato de archivo no soportado. Use .xlsx, .xls o .csv")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo: {str(e)}")
    
    # Mapeo flexible de columnas (insensible a mayúsculas/minúsculas)
    columnas_map = {
        "cedula": ["cedula", "cc", "identificacion", "documento"],
        "serial": ["serial", "numero", "consecutivo", "id"],
        "nombre": ["nombre", "trabajador", "empleado", "persona"],
        "tipo_incapacidad": ["tipo", "tipo_incapacidad", "causa", "categoria"],
        "eps": ["eps", "entidad", "salud", "aseguradora"],
        "fecha_inicio": ["fecha_inicio", "fecha inicio", "inicio", "desde"],
        "fecha_fin": ["fecha_fin", "fecha fin", "fin", "hasta"]
    }
    
    # Detectar columnas presentes
    columnas_detectadas = {}
    for col_objetivo, posibles_nombres in columnas_map.items():
        for col_df in df.columns:
            if col_df.lower().strip() in posibles_nombres:
                columnas_detectadas[col_objetivo] = col_df
                break
    
    # Convertir DataFrame a lista de registros
    registros = []
    for _, row in df.iterrows():
        registro = BusquedaRelacional()
        
        if "cedula" in columnas_detectadas:
            registro.cedula = str(row[columnas_detectadas["cedula"]]) if pd.notna(row[columnas_detectadas["cedula"]]) else None
        
        if "serial" in columnas_detectadas:
            registro.serial = str(row[columnas_detectadas["serial"]]) if pd.notna(row[columnas_detectadas["serial"]]) else None
        
        if "nombre" in columnas_detectadas:
            registro.nombre = str(row[columnas_detectadas["nombre"]]) if pd.notna(row[columnas_detectadas["nombre"]]) else None
        
        if "tipo_incapacidad" in columnas_detectadas:
            registro.tipo_incapacidad = str(row[columnas_detectadas["tipo_incapacidad"]]) if pd.notna(row[columnas_detectadas["tipo_incapacidad"]]) else None
        
        if "eps" in columnas_detectadas:
            registro.eps = str(row[columnas_detectadas["eps"]]) if pd.notna(row[columnas_detectadas["eps"]]) else None
        
        # Fechas: intentar parsear automáticamente
        if "fecha_inicio" in columnas_detectadas:
            try:
                fecha = pd.to_datetime(row[columnas_detectadas["fecha_inicio"]])
                registro.fecha_inicio = fecha.strftime("%Y-%m-%d")
            except:
                registro.fecha_inicio = None
        
        if "fecha_fin" in columnas_detectadas:
            try:
                fecha = pd.to_datetime(row[columnas_detectadas["fecha_fin"]])
                registro.fecha_fin = fecha.strftime("%Y-%m-%d")
            except:
                registro.fecha_fin = None
        
        registros.append(registro)
    
    # Crear request y llamar al endpoint de búsqueda
    request = BusquedaRelacionalRequest(registros=registros)
    
    # Registrar en historial con nombre de archivo
    historial = SearchHistory(
        usuario="Validador",
        tipo_busqueda="relacional_excel",
        parametros_json={
            "archivo": archivo.filename,
            "columnas_detectadas": list(columnas_detectadas.keys()),
            "total_filas": len(registros)
        },
        resultados_count=0,  # Se actualizará después
        archivo_nombre=archivo.filename
    )
    db.add(historial)
    db.commit()
    
    # Ejecutar búsqueda
    resultados_response = await busqueda_relacional(request, db, True)
    
    # Actualizar conteo de resultados
    historial.resultados_count = resultados_response["total_encontrados"]
    db.commit()
    
    return {
        **resultados_response,
        "archivo_procesado": archivo.filename,
        "columnas_detectadas": columnas_detectadas,
        "filas_procesadas": len(registros)
    }

@router.get("/exportar/casos")
async def exportar_casos(
    formato: str = "xlsx",
    empresa: Optional[str] = None,
    estado: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    📥 EXPORTAR CASOS A EXCEL
    
    Genera un archivo Excel con los casos filtrados
    """
    from fastapi.responses import StreamingResponse
    
    query = db.query(Case).join(Employee, Case.employee_id == Employee.id, isouter=True)
    
    # Aplicar filtros
    if empresa and empresa != "all":
        company = db.query(Company).filter(Company.nombre == empresa).first()
        if company:
            query = query.filter(Case.company_id == company.id)
    
    if estado and estado != "all":
        query = query.filter(Case.estado == estado)
    
    if desde:
        fecha_desde = datetime.fromisoformat(desde)
        query = query.filter(Case.created_at >= fecha_desde)
    
    if hasta:
        fecha_hasta = datetime.fromisoformat(hasta)
        query = query.filter(Case.created_at <= fecha_hasta)
    
    casos = query.all()
    
    # Convertir a DataFrame
    data = []
    for caso in casos:
        empleado = caso.empleado
        empresa_obj = caso.empresa
        
        data.append({
            "Serial": caso.serial,
            "Cédula": caso.cedula,
            "Nombre": empleado.nombre if empleado else "No registrado",
            "Empresa": empresa_obj.nombre if empresa_obj else "Otra",
            "Tipo": caso.tipo.value if caso.tipo else None,
            "Días": caso.dias_incapacidad,
            "Estado": caso.estado.value,
            "EPS": caso.eps,
            "Fecha Inicio": caso.fecha_inicio.strftime("%Y-%m-%d") if caso.fecha_inicio else None,
            "Fecha Fin": caso.fecha_fin.strftime("%Y-%m-%d") if caso.fecha_fin else None,
            "Diagnóstico": caso.diagnostico,
            "Link Drive": caso.drive_link,
            "Fecha Registro": caso.created_at.strftime("%Y-%m-%d %H:%M")
        })
    
    df = pd.DataFrame(data)
    
    # Generar archivo
    output = io.BytesIO()
    
    if formato == "xlsx":
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Casos')
        
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=casos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
        )
    
    elif formato == "csv":
        df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=casos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
    
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado. Use 'xlsx' o 'csv'")