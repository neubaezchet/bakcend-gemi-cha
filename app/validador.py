"""
Router del Portal de Validadores - IncaNeurobaeza
Endpoints para gestión, validación y búsqueda de casos
"""

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
import requests
import io
import os
import tempfile
import base64
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import pandas as pd
import sib_api_v3_sdk

from app.database import (
    get_db, Case, CaseDocument, CaseEvent, CaseNote, Employee, 
    Company, SearchHistory, EstadoCaso, EstadoDocumento, TipoIncapacidad
)
from app.checks_disponibles import CHECKS_DISPONIBLES, obtener_checks_por_tipo
from app.email_templates import get_email_template_universal
from app.drive_manager import CaseFileOrganizer
from app.n8n_notifier import enviar_a_n8n  # ✅ NUEVO

router = APIRouter(prefix="/validador", tags=["Portal de Validadores"])

# ==================== MODELOS PYDANTIC ====================

class FiltrosCasos(BaseModel):
    empresa: Optional[str] = None
    estado: Optional[str] = None
    tipo: Optional[str] = None
    q: Optional[str] = None
    page: int = 1
    page_size: int = 20

class CambioEstado(BaseModel):
    estado: str
    motivo: Optional[str] = None
    documentos: Optional[List[Dict]] = None
    fecha_limite: Optional[str] = None

class NotaRapida(BaseModel):
    contenido: str
    es_importante: bool = False

class BusquedaRelacional(BaseModel):
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

def enviar_email_con_adjuntos(to_email, subject, html_body, adjuntos_paths=[], caso=None, db=None):
    """
    ✅ NUEVO: Envía email a través de n8n en lugar de Brevo
    """
    import base64
    
    # Convertir adjuntos a base64
    adjuntos_base64 = []
    for path in adjuntos_paths:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
                adjuntos_base64.append({
                    'filename': os.path.basename(path),
                    'content': content,
                    'mimetype': 'application/octet-stream'
                })
    
    # Determinar tipo de notificación desde el subject
    tipo_map = {
        'Confirmación': 'confirmacion',
        'Incompleta': 'incompleta',
        'Ilegible': 'ilegible',
        'Validada': 'completa',
        'EPS': 'eps',
        'TTHH': 'tthh',
        'Extra': 'extra'
    }
    
    tipo_notificacion = 'confirmacion'  # default
    for key, value in tipo_map.items():
        if key in subject:
            tipo_notificacion = value
            break
    
    # Obtener email de copia si existe
    cc_email = None
    if caso and caso.empresa and caso.empresa.email_copia:
        cc_email = caso.empresa.email_copia
        print(f"📧 Email de copia configurado: {cc_email} ({caso.empresa.nombre})")
    
    # Enviar a n8n
    return enviar_a_n8n(
        tipo_notificacion=tipo_notificacion,
        email=to_email,
        serial=caso.serial if caso else 'N/A',
        subject=subject,
        html_content=html_body,
        cc_email=cc_email,
        adjuntos_base64=adjuntos_base64
    )


def send_html_email(to_email, subject, html_body, caso=None):
    """✅ NUEVO: Envía email a través de n8n (wrapper sin adjuntos)"""
    return enviar_email_con_adjuntos(to_email, subject, html_body, [], caso=caso)

def obtener_email_tthh(empresa_nombre):
    """Retorna el email de TTHH según la empresa"""
    emails_tthh = {
        'ABC Corp': 'tthh.abc@example.com',
        'XYZ S.A.S': 'tthh.xyz@example.com',
    }
    return emails_tthh.get(empresa_nombre, 'xoblaxbaezaospino@gmail.com')

# ==================== ENDPOINTS ====================

@router.get("/empresas")
async def listar_empresas(
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Lista todas las empresas activas"""
    try:
        empresas = db.query(Company.nombre).filter(Company.activa == True).distinct().all()
        empresas_list = [e[0] for e in empresas if e[0]]
        
        print(f"✅ Empresas encontradas: {len(empresas_list)}")
        
        return {
            "empresas": sorted(empresas_list)
        }
    except Exception as e:
        print(f"❌ Error en /empresas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """Lista casos con filtros avanzados"""
    
    query = db.query(Case)
    
    if empresa and empresa != "all" and empresa != "undefined":
        company = db.query(Company).filter(Company.nombre == empresa).first()
        if company:
            query = query.filter(Case.company_id == company.id)
    
    if estado and estado != "all" and estado != "undefined":
        try:
            query = query.filter(Case.estado == EstadoCaso[estado])
        except KeyError:
            pass
    
    if tipo and tipo != "all" and tipo != "undefined":
        try:
            query = query.filter(Case.tipo == TipoIncapacidad[tipo])
        except KeyError:
            pass
    
    if q:
        query = query.join(Employee, Case.employee_id == Employee.id, isouter=True)
        query = query.filter(
            or_(
                Case.serial.ilike(f"%{q}%"),
                Case.cedula.ilike(f"%{q}%"),
                Employee.nombre.ilike(f"%{q}%")
            )
        )
    
    total = query.count()
    
    offset = (page - 1) * page_size
    casos = query.order_by(Case.created_at.desc()).offset(offset).limit(page_size).all()
    
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
    """Cambia el estado de un caso y envía notificaciones"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    estado_anterior = caso.estado.value
    nuevo_estado = cambio.estado
    
    try:
        EstadoCaso(nuevo_estado)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {nuevo_estado}")
    
    caso.estado = EstadoCaso(nuevo_estado)
    
    if cambio.documentos:
        for doc_data in cambio.documentos:
            doc = db.query(CaseDocument).filter(
                CaseDocument.case_id == caso.id,
                CaseDocument.doc_tipo == doc_data.get("doc")
            ).first()
            
            if doc:
                doc.estado_doc = EstadoDocumento(doc_data.get("estado_doc", "PENDIENTE"))
                doc.observaciones = cambio.motivo
    
    registrar_evento(
        db, caso.id, "cambio_estado", 
        actor="Validador",
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado,
        motivo=cambio.motivo,
        metadata={"fecha_limite": cambio.fecha_limite} if cambio.fecha_limite else None
    )
    
    if nuevo_estado in ["INCOMPLETA", "ILEGIBLE", "INCOMPLETA_ILEGIBLE"]:
        caso.bloquea_nueva = True
    
    db.commit()
    
    return {
        "status": "ok",
        "serial": serial,
        "estado_anterior": estado_anterior,
        "estado_nuevo": nuevo_estado,
        "mensaje": f"Estado actualizado a {nuevo_estado}"
    }

@router.post("/casos/{serial}/nota")
async def agregar_nota(
    serial: str,
    nota: NotaRapida,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Agrega una nota rápida al caso"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    nueva_nota = CaseNote(
        case_id=caso.id,
        autor="Validador",
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
    
    if empresa and empresa != "all" and empresa != "undefined":
        company = db.query(Company).filter(Company.nombre == empresa).first()
        if company:
            query = query.filter(Case.company_id == company.id)
    
    stats = {
        "total_casos": query.count(),
        "incompletas": query.filter(Case.estado == EstadoCaso.INCOMPLETA).count(),
        "eps": query.filter(Case.estado == EstadoCaso.EPS_TRANSCRIPCION).count(),
        "tthh": query.filter(Case.estado == EstadoCaso.DERIVADO_TTHH).count(),
        "completas": query.filter(Case.estado == EstadoCaso.COMPLETA).count(),
        "nuevos": query.filter(Case.estado == EstadoCaso.NUEVO).count(),
        "causa_extra": query.filter(Case.estado == EstadoCaso.CAUSA_EXTRA).count(),
    }
    
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
    """Motor de reglas dinámico: calcula documentos requeridos según contexto"""
    
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

@router.post("/busqueda-relacional")
async def busqueda_relacional(
    request: BusquedaRelacionalRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Búsqueda relacional avanzada"""
    
    resultados = []
    filtros_globales = request.filtros_globales or {}
    
    for registro in request.registros:
        query = db.query(Case).join(Employee, Case.employee_id == Employee.id, isouter=True)
        
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
        
        if filtros_globales.get("empresa"):
            company = db.query(Company).filter(Company.nombre == filtros_globales["empresa"]).first()
            if company:
                query = query.filter(Case.company_id == company.id)
        
        if filtros_globales.get("tipo_documento"):
            tipos_docs = filtros_globales["tipo_documento"]
            query = query.join(CaseDocument).filter(CaseDocument.doc_tipo.in_(tipos_docs))
        
        casos = query.all()
        
        for caso in casos:
            empleado = caso.empleado
            empresa = caso.empresa
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
    
    historial = SearchHistory(
        usuario="Validador",
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
    """Búsqueda relacional desde Excel"""
    
    contents = await archivo.read()
    
    try:
        if archivo.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        elif archivo.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Formato de archivo no soportado. Use .xlsx, .xls o .csv")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo: {str(e)}")
    
    columnas_map = {
        "cedula": ["cedula", "cc", "identificacion", "documento"],
        "serial": ["serial", "numero", "consecutivo", "id"],
        "nombre": ["nombre", "trabajador", "empleado", "persona"],
        "tipo_incapacidad": ["tipo", "tipo_incapacidad", "causa", "categoria"],
        "eps": ["eps", "entidad", "salud", "aseguradora"],
        "fecha_inicio": ["fecha_inicio", "fecha inicio", "inicio", "desde"],
        "fecha_fin": ["fecha_fin", "fecha fin", "fin", "hasta"]
    }
    
    columnas_detectadas = {}
    for col_objetivo, posibles_nombres in columnas_map.items():
        for col_df in df.columns:
            if col_df.lower().strip() in posibles_nombres:
                columnas_detectadas[col_objetivo] = col_df
                break
    
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
    
    request = BusquedaRelacionalRequest(registros=registros)
    
    historial = SearchHistory(
        usuario="Validador",
        tipo_busqueda="relacional_excel",
        parametros_json={
            "archivo": archivo.filename,
            "columnas_detectadas": list(columnas_detectadas.keys()),
            "total_filas": len(registros)
        },
        resultados_count=0,
        archivo_nombre=archivo.filename
    )
    db.add(historial)
    db.commit()
    
    resultados_response = await busqueda_relacional(request, db, True)
    
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
    """Exportar casos a Excel"""
    
    query = db.query(Case).join(Employee, Case.employee_id == Employee.id, isouter=True)
    
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

@router.get("/casos/{serial}/pdf")
async def obtener_pdf_caso(
    serial: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Devuelve el PDF del caso desde Google Drive"""
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    if not caso.drive_link:
        raise HTTPException(status_code=404, detail="Este caso no tiene PDF asociado")
    
    try:
        drive_id = None
        if "/file/d/" in caso.drive_link:
            drive_id = caso.drive_link.split("/file/d/")[1].split("/")[0]
        elif "id=" in caso.drive_link:
            drive_id = caso.drive_link.split("id=")[1].split("&")[0]
        
        if not drive_id:
            raise HTTPException(status_code=400, detail="Link de Drive inválido")
        
        download_url = f"https://drive.google.com/uc?export=download&id={drive_id}"
        
        response = requests.get(download_url, stream=True)
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Error descargando PDF desde Drive")
        
        return StreamingResponse(
            io.BytesIO(response.content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={serial}.pdf",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error obteniendo PDF para {serial}: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando PDF: {str(e)}")

@router.post("/casos/{serial}/validar")
async def validar_caso_con_checks(
    serial: str,
    accion: str = Form(...),
    checks: List[str] = Form(default=[]),
    observaciones: str = Form(default=""),
    adjuntos: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Endpoint unificado para validaciones con SISTEMA HÍBRIDO IA/PLANTILLAS
    Acciones: 'completa', 'incompleta', 'ilegible', 'eps', 'tthh', 'falsa'
    """
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    empleado = caso.empleado
    
    # ✅ Cambiar estado en BD
    estado_map = {
        'completa': EstadoCaso.COMPLETA,
        'incompleta': EstadoCaso.INCOMPLETA,
        'ilegible': EstadoCaso.ILEGIBLE,
        'eps': EstadoCaso.EPS_TRANSCRIPCION,
        'tthh': EstadoCaso.DERIVADO_TTHH,
        'falsa': EstadoCaso.DERIVADO_TTHH
    }
    nuevo_estado = estado_map[accion]
    caso.estado = nuevo_estado
    db.commit()
    
    # ✅ Mover archivo en Drive según el estado
    organizer = CaseFileOrganizer()
    nuevo_link = organizer.mover_caso_segun_estado(caso, nuevo_estado.value, observaciones)
    if nuevo_link:
        caso.drive_link = nuevo_link
        db.commit()
        print(f"✅ Archivo movido en Drive: {nuevo_link}")
    
    # Procesar adjuntos si los hay
    adjuntos_paths = []
    if adjuntos:
        for i, adjunto in enumerate(adjuntos):
            temp_path = os.path.join(tempfile.gettempdir(), f"{serial}_adjunto_{i}_{adjunto.filename}")
            with open(temp_path, "wb") as f:
                f.write(await adjunto.read())
            adjuntos_paths.append(temp_path)
    
    # ✅ SISTEMA HÍBRIDO: IA vs Plantillas
    from app.ia_redactor import (
        redactar_email_incompleta, 
        redactar_email_ilegible, 
        redactar_alerta_tthh
    )
    
    contenido_ia = None
    
    # ========== LÓGICA HÍBRIDA ==========
    if accion in ['incompleta', 'ilegible']:
        # ✅ USAR IA para casos complejos
        print(f"🤖 Generando email con IA Claude Haiku para {serial}...")
        
        if accion == 'incompleta':
            contenido_ia = redactar_email_incompleta(
                empleado.nombre if empleado else 'Colaborador/a',
                serial,
                checks,
                caso.tipo.value if caso.tipo else 'General'
            )
        elif accion == 'ilegible':
            contenido_ia = redactar_email_ilegible(
                empleado.nombre if empleado else 'Colaborador/a',
                serial,
                checks
            )
        
        # Insertar contenido IA en plantilla
        email_empleada = get_email_template_universal(
            tipo_email=accion,
            nombre=empleado.nombre if empleado else 'Colaborador/a',
            serial=serial,
            empresa=caso.empresa.nombre if caso.empresa else 'N/A',
            tipo_incapacidad=caso.tipo.value if caso.tipo else 'General',
            telefono=caso.telefono_form,
            email=caso.email_form,
            link_drive=caso.drive_link,
            checks_seleccionados=checks,
            contenido_ia=contenido_ia  # ✅ IA aquí
        )
        
        # Enviar con formato de asunto actualizado
        estado_label = 'Incompleta' if accion == 'incompleta' else 'Ilegible'
        asunto = f"CC {caso.cedula} - {serial} - {estado_label} - {empleado.nombre if empleado else 'Colaborador'} - {caso.empresa.nombre if caso.empresa else 'N/A'}"
        enviar_email_con_adjuntos(
            caso.email_form,
            asunto,
            email_empleada,
            adjuntos_paths,
            caso=caso  # ✅ COPIA AUTOMÁTICA
        )
    
    elif accion == 'tthh':
        # ✅ USAR IA para alerta a TTHH
        print(f"🚨 Generando alerta TTHH con IA para {serial}...")
        
        contenido_ia_tthh = redactar_alerta_tthh(
            empleado.nombre if empleado else 'Colaborador/a',
            serial,
            caso.empresa.nombre if caso.empresa else 'N/A',
            checks,
            observaciones
        )
        
        # Email al jefe/TTHH
        email_tthh_destinatario = obtener_email_tthh(caso.empresa.nombre if caso.empresa else 'Default')
        
        email_tthh = get_email_template_universal(
            tipo_email='tthh',
            nombre='Equipo de Talento Humano',
            serial=serial,
            empresa=caso.empresa.nombre if caso.empresa else 'N/A',
            tipo_incapacidad=caso.tipo.value if caso.tipo else 'General',
            telefono=caso.telefono_form,
            email=caso.email_form,
            link_drive=caso.drive_link,
            checks_seleccionados=checks,
            contenido_ia=contenido_ia_tthh,  # ✅ IA aquí
            empleado_nombre=empleado.nombre if empleado else 'Colaborador/a'
        )
        
        asunto_tthh = f"CC {caso.cedula} - {serial} - TTHH - {empleado.nombre if empleado else 'Colaborador'} - {caso.empresa.nombre if caso.empresa else 'N/A'}"
        enviar_email_con_adjuntos(
            email_tthh_destinatario,
            asunto_tthh,
            email_tthh,
            adjuntos_paths
        )
        
        # Email confirmación a la empleada (plantilla estática)
        email_empleada_falsa = get_email_template_universal(
            tipo_email='falsa',
            nombre=empleado.nombre if empleado else 'Colaborador/a',
            serial=serial,
            empresa=caso.empresa.nombre if caso.empresa else 'N/A',
            tipo_incapacidad=caso.tipo.value if caso.tipo else 'General',
            telefono=caso.telefono_form,
            email=caso.email_form,
            link_drive=caso.drive_link
        )
        
        asunto_confirmacion = f"CC {caso.cedula} - {serial} - Confirmación - {empleado.nombre if empleado else 'Colaborador'} - {caso.empresa.nombre if caso.empresa else 'N/A'}"
        send_html_email(
            caso.email_form,
            asunto_confirmacion,
            email_empleada_falsa,
            caso=caso  # ✅ COPIA AUTOMÁTICA
        )
    
    elif accion in ['completa', 'eps', 'falsa']:
        # ✅ PLANTILLAS ESTÁTICAS (Gratis)
        print(f"📄 Usando plantilla estática para {accion}...")
        
        email_empleada = get_email_template_universal(
            tipo_email=accion,
            nombre=empleado.nombre if empleado else 'Colaborador/a',
            serial=serial,
            empresa=caso.empresa.nombre if caso.empresa else 'N/A',
            tipo_incapacidad=caso.tipo.value if caso.tipo else 'General',
            telefono=caso.telefono_form,
            email=caso.email_form,
            link_drive=caso.drive_link
        )
        
        estado_map_asunto = {
            'completa': 'Validada',
            'eps': 'EPS',
            'falsa': 'Confirmación'
        }
        estado_label = estado_map_asunto.get(accion, 'Actualización')
        asunto = f"CC {caso.cedula} - {serial} - {estado_label} - {empleado.nombre if empleado else 'Colaborador'} - {caso.empresa.nombre if caso.empresa else 'N/A'}"
        send_html_email(
            caso.email_form,
            asunto,
            email_empleada,
            caso=caso  # ✅ COPIA AUTOMÁTICA
        )
    
    # Limpiar adjuntos temporales
    for temp_file in adjuntos_paths:
        try:
            os.remove(temp_file)
        except:
            pass
    
    # Registrar evento
    registrar_evento(
        db, caso.id, 
        "validacion_con_ia" if contenido_ia else "validacion_estatica",
        actor="Validador",
        estado_anterior=caso.estado.value,
        estado_nuevo=nuevo_estado.value,
        motivo=observaciones,
        metadata={"checks": checks, "usa_ia": bool(contenido_ia)}
    )
    
    return {
        "status": "ok",
        "serial": serial,
        "accion": accion,
        "checks": checks,
        "nuevo_link": caso.drive_link,
        "usa_ia": bool(contenido_ia),
        "mensaje": f"Caso {accion} correctamente"
    }


# ✅ NUEVO: Endpoint para notificación libre con IA
@router.post("/casos/{serial}/notificar-libre")
async def notificar_libre_con_ia(
    serial: str,
    mensaje_personalizado: str = Form(...),
    adjuntos: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Endpoint para el botón "Extra" - Notificación libre con IA
    El validador escribe un mensaje informal y la IA lo convierte en profesional
    """
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    empleado = caso.empleado
    
    # ✅ Redactar con IA
    from app.ia_redactor import redactar_mensaje_personalizado
    
    print(f"🤖 Redactando mensaje personalizado con IA para {serial}...")
    
    contenido_ia = redactar_mensaje_personalizado(
        empleado.nombre if empleado else 'Colaborador/a',
        serial,
        mensaje_personalizado
    )
    
    # Procesar adjuntos
    adjuntos_paths = []
    if adjuntos:
        for i, adjunto in enumerate(adjuntos):
            temp_path = os.path.join(tempfile.gettempdir(), f"{serial}_extra_{i}_{adjunto.filename}")
            with open(temp_path, "wb") as f:
                f.write(await adjunto.read())
            adjuntos_paths.append(temp_path)
    
    # Insertar en plantilla
    email_personalizado = get_email_template_universal(
        tipo_email='extra',
        nombre=empleado.nombre if empleado else 'Colaborador/a',
        serial=serial,
        empresa=caso.empresa.nombre if caso.empresa else 'N/A',
        tipo_incapacidad=caso.tipo.value if caso.tipo else 'General',
        telefono=caso.telefono_form,
        email=caso.email_form,
        link_drive=caso.drive_link,
        contenido_ia=contenido_ia
    )
    
    # Enviar con formato de asunto actualizado
    asunto = f"CC {caso.cedula} - {serial} - Extra - {empleado.nombre if empleado else 'Colaborador'} - {caso.empresa.nombre if caso.empresa else 'N/A'}"
    enviar_email_con_adjuntos(
        caso.email_form,
        asunto,
        email_personalizado,
        adjuntos_paths,
        caso=caso  # ✅ COPIA AUTOMÁTICA
    )
    
    # Limpiar adjuntos
    for temp_file in adjuntos_paths:
        try:
            os.remove(temp_file)
        except:
            pass
    
    # Registrar evento
    registrar_evento(
        db, caso.id, 
        "notificacion_libre_ia",
        actor="Validador",
        motivo=mensaje_personalizado[:200],  # Primeros 200 caracteres
        metadata={"mensaje_original": mensaje_personalizado}
    )
    
    return {
        "status": "ok",
        "serial": serial,
        "mensaje": "Notificación enviada correctamente"
    }

@router.get("/checks-disponibles/{tipo_incapacidad}")
async def obtener_checks_disponibles_endpoint(
    tipo_incapacidad: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """Endpoint para obtener los checks disponibles según tipo de incapacidad"""
    checks = obtener_checks_por_tipo(tipo_incapacidad)
    
    return {
        "tipo_incapacidad": tipo_incapacidad,
        "checks": checks
    }

@router.post("/casos/{serial}/editar-pdf")
async def editar_pdf_caso(
    serial: str,
    operaciones: dict,
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Edita el PDF de un caso con múltiples operaciones
    
    Operaciones soportadas:
    - enhance_quality: {page_num: int}
    - rotate: {page_num: int, angle: int}
    - crop_auto: {page_num: int, margin: int}
    - crop_custom: {page_num: int, x: int, y: int, width: int, height: int}
    - reorder: {new_order: [1, 0, 2, ...]}
    - annotate: {page_num: int, type: str, coords: [x1,y1,x2,y2], text: str, color: [r,g,b]}
    - delete_page: {pages: [0, 2, 5]}
    """
    from app.pdf_editor import PDFEditor
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso or not caso.drive_link:
        raise HTTPException(status_code=404, detail="Caso o PDF no encontrado")
    
    # Extraer file_id y descargar PDF
    if '/file/d/' in caso.drive_link:
        file_id = caso.drive_link.split('/file/d/')[1].split('/')[0]
    elif 'id=' in caso.drive_link:
        file_id = caso.drive_link.split('id=')[1].split('&')[0]
    else:
        raise HTTPException(status_code=400, detail="Link de Drive inválido")
    
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(download_url)
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Error descargando PDF")
    
    temp_input = os.path.join(tempfile.gettempdir(), f"{serial}_original.pdf")
    temp_output = os.path.join(tempfile.gettempdir(), f"{serial}_edited.pdf")
    
    with open(temp_input, 'wb') as f:
        f.write(response.content)
    
    try:
        editor = PDFEditor(temp_input)
        
        for op_type, op_data in operaciones.items():
            if op_type == 'enhance_quality':
                for page_num in op_data.get('pages', []):
                    editor.enhance_page_quality(page_num)
            
            elif op_type == 'rotate':
                for item in op_data:
                    editor.rotate_page(item['page_num'], item['angle'])
            
            elif op_type == 'crop_auto':
                for item in op_data:
                    editor.auto_crop_page(item['page_num'], item.get('margin', 10))
            
            elif op_type == 'crop_custom':
                for item in op_data:
                    editor.crop_page_custom(
                        item['page_num'],
                        item['x'], item['y'],
                        item['width'], item['height']
                    )
            
            elif op_type == 'reorder':
                editor.reorder_pages(op_data['new_order'])
            
            elif op_type == 'annotate':
                for item in op_data:
                    color_tuple = tuple(item.get('color', [1, 0, 0]))
                    editor.add_annotation(
                        item['page_num'],
                        item['type'],
                        tuple(item['coords']),
                        item.get('text', ''),
                        color_tuple
                    )
            
            elif op_type == 'delete_page':
                for page_num in sorted(op_data['pages'], reverse=True):
                    editor.delete_page(page_num)
        
        editor.save_changes(temp_output)
        
        # Subir a Drive
        organizer = CaseFileOrganizer()
        nuevo_link = organizer.actualizar_pdf_editado(caso, temp_output)
        
        if nuevo_link:
            caso.drive_link = nuevo_link
            db.commit()
        
        os.remove(temp_input)
        os.remove(temp_output)
        
        return {
            "status": "ok",
            "serial": serial,
            "nuevo_link": nuevo_link,
            "modificaciones": editor.get_modifications_log(),
            "mensaje": "PDF editado y actualizado en Drive"
        }
    
    except Exception as e:
        if os.path.exists(temp_input):
            os.remove(temp_input)
        if os.path.exists(temp_output):
            os.remove(temp_output)
        raise HTTPException(status_code=500, detail=f"Error editando PDF: {str(e)}")

@router.post("/casos/{serial}/crear-adjunto")
async def crear_adjunto_desde_pdf(
    serial: str,
    page_num: int,
    coords: List[int],
    tipo: str = "highlight",
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Crea una imagen recortada del PDF para adjuntar al email
    Tipos: "highlight" o "preview"
    """
    from app.pdf_editor import PDFAttachmentManager
    
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso or not caso.drive_link:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    if '/file/d/' in caso.drive_link:
        file_id = caso.drive_link.split('/file/d/')[1].split('/')[0]
    else:
        raise HTTPException(status_code=400, detail="Link inválido")
    
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(download_url)
    
    temp_pdf = os.path.join(tempfile.gettempdir(), f"{serial}_temp.pdf")
    temp_img = os.path.join(tempfile.gettempdir(), f"{serial}_adjunto_{page_num}.png")
    
    with open(temp_pdf, 'wb') as f:
        f.write(response.content)
    
    try:
        manager = PDFAttachmentManager()
        
        if tipo == "highlight":
            manager.create_highlight_image(temp_pdf, page_num, coords, temp_img)
        else:
            manager.create_page_preview(temp_pdf, page_num, temp_img, [coords])
        
        with open(temp_img, 'rb') as f:
            img_data = f.read()
        
        os.remove(temp_pdf)
        os.remove(temp_img)
        
        return StreamingResponse(
            io.BytesIO(img_data),
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename={serial}_adjunto.png"}

@router.post("/casos/{serial}/guardar-pdf-editado")
async def guardar_pdf_editado(
    serial: str,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: bool = Depends(verificar_token_admin)
):
    """
    Guarda un PDF editado en Drive reemplazando el original
    """
    caso = db.query(Case).filter(Case.serial == serial).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    # Guardar archivo temporal
    temp_path = os.path.join(tempfile.gettempdir(), f"{serial}_edited.pdf")
    
    try:
        # Guardar archivo subido
        with open(temp_path, 'wb') as f:
            shutil.copyfileobj(archivo.file, f)
        
        # Actualizar en Drive
        organizer = CaseFileOrganizer()
        nuevo_link = organizer.actualizar_pdf_editado(caso, temp_path)
        
        if nuevo_link:
            caso.drive_link = nuevo_link
            db.commit()
            
            # Registrar evento
            registrar_evento(
                db, caso.id,
                "pdf_editado",
                actor="Validador",
                motivo="PDF editado con herramientas de anotación"
            )
            
            os.remove(temp_path)
            
            return {
                "status": "ok",
                "serial": serial,
                "nuevo_link": nuevo_link,
                "mensaje": "PDF actualizado exitosamente en Drive"
            }
        else:
            raise HTTPException(status_code=500, detail="Error actualizando PDF en Drive")
    
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")