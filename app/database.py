"""
Sistema de Base de Datos - IncaNeurobaeza
Modelos SQLAlchemy para gestión de casos de incapacidades
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import enum

# Base para modelos
Base = declarative_base()

# Enums para estados
class EstadoCaso(str, enum.Enum):
    NUEVO = "NUEVO"
    EN_REVISION = "EN_REVISION"
    INCOMPLETA = "INCOMPLETA"
    ILEGIBLE = "ILEGIBLE"
    INCOMPLETA_ILEGIBLE = "INCOMPLETA_ILEGIBLE"
    EPS_TRANSCRIPCION = "EPS_TRANSCRIPCION"
    DERIVADO_TTHH = "DERIVADO_TTHH"
    CAUSA_EXTRA = "CAUSA_EXTRA"
    COMPLETA = "COMPLETA"
    EN_RADICACION = "EN_RADICACION"

class EstadoDocumento(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    OK = "OK"
    INCOMPLETO = "INCOMPLETO"
    ILEGIBLE = "ILEGIBLE"

class TipoIncapacidad(str, enum.Enum):
    ENFERMEDAD_GENERAL = "enfermedad_general"
    ENFERMEDAD_LABORAL = "enfermedad_laboral"
    ACCIDENTE_TRANSITO = "accidente_transito"
    ENFERMEDAD_ESPECIAL = "especial"
    MATERNIDAD = "maternidad"
    PATERNIDAD = "paternidad"

# ==================== MODELOS ====================

class Company(Base):
    """Empresas registradas en el sistema"""
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False, unique=True, index=True)
    nit = Column(String(50), unique=True)
    contacto_email = Column(String(200))
    contacto_telefono = Column(String(50))
    activa = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    empleados = relationship("Employee", back_populates="empresa")
    casos = relationship("Case", back_populates="empresa")

class Employee(Base):
    """Empleados registrados (Base de datos Excel)"""
    __tablename__ = 'employees'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    cedula = Column(String(50), nullable=False, unique=True, index=True)
    nombre = Column(String(200), nullable=False, index=True)
    correo = Column(String(200))
    telefono = Column(String(50))
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    eps = Column(String(100))
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    empresa = relationship("Company", back_populates="empleados")
    casos = relationship("Case", back_populates="empleado")

class Case(Base):
    """Casos de incapacidad registrados"""
    __tablename__ = 'cases'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    serial = Column(String(50), nullable=False, unique=True, index=True)
    cedula = Column(String(50), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=True)  # Puede ser NULL si no está en BD
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    
    # Datos del caso
    tipo = Column(Enum(TipoIncapacidad), nullable=False)
    subtipo = Column(String(100))  # Para casos "other" del frontend
    dias_incapacidad = Column(Integer)
    estado = Column(Enum(EstadoCaso), default=EstadoCaso.NUEVO, index=True)
    
    # Metadata adicional (JSON para flexibilidad)
    metadata_form = Column(JSON)  # births, motherWorks, isPhantomVehicle, etc.
    
    # Campos adicionales de búsqueda
    eps = Column(String(100), index=True)
    fecha_inicio = Column(DateTime, index=True)
    fecha_fin = Column(DateTime, index=True)
    diagnostico = Column(Text)
    
    # Control de flujo
    bloquea_nueva = Column(Boolean, default=False)  # Bloqueo híbrido
    drive_link = Column(String(500))
    email_form = Column(String(200))
    telefono_form = Column(String(50))
    
    # Auditoría
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    empleado = relationship("Employee", back_populates="casos")
    empresa = relationship("Company", back_populates="casos")
    documentos = relationship("CaseDocument", back_populates="caso", cascade="all, delete-orphan")
    eventos = relationship("CaseEvent", back_populates="caso", cascade="all, delete-orphan")
    notas = relationship("CaseNote", back_populates="caso", cascade="all, delete-orphan")

class CaseDocument(Base):
    """Documentos asociados a un caso"""
    __tablename__ = 'case_documents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey('cases.id'), nullable=False)
    
    doc_tipo = Column(String(100), nullable=False)  # "incapacidad_medica", "epicrisis", etc.
    requerido = Column(Boolean, default=True)
    estado_doc = Column(Enum(EstadoDocumento), default=EstadoDocumento.PENDIENTE)
    
    # Múltiples versiones (array de URLs)
    drive_urls = Column(JSON)  # ["url_v1", "url_v2", ...]
    version_actual = Column(Integer, default=1)
    
    observaciones = Column(Text)
    calidad_validada = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    caso = relationship("Case", back_populates="documentos")

class CaseEvent(Base):
    """Historial de eventos/cambios de un caso"""
    __tablename__ = 'case_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey('cases.id'), nullable=False)
    
    actor = Column(String(200))  # Usuario/Sistema que hizo el cambio
    accion = Column(String(100), nullable=False)  # "cambio_estado", "subida_doc", "nota", etc.
    estado_anterior = Column(String(50))
    estado_nuevo = Column(String(50))
    motivo = Column(Text)
    metadata_json = Column(JSON)  # Datos adicionales del evento
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relaciones
    caso = relationship("Case", back_populates="eventos")

class CaseNote(Base):
    """Notas rápidas en casos (Mejora: Quick notes)"""
    __tablename__ = 'case_notes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey('cases.id'), nullable=False)
    
    autor = Column(String(200))
    contenido = Column(Text, nullable=False)
    es_importante = Column(Boolean, default=False)  # Para destacar
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relaciones
    caso = relationship("Case", back_populates="notas")

class SearchHistory(Base):
    """Historial de búsquedas relacionales (Auditoría)"""
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(String(200))
    tipo_busqueda = Column(String(50))  # "relacional", "avanzada", "simple"
    parametros_json = Column(JSON)  # Filtros usados
    resultados_count = Column(Integer)
    archivo_nombre = Column(String(200))  # Si fue desde Excel
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

# ==================== FUNCIONES DE INICIALIZACIÓN ====================

def get_database_url():
    """Obtiene la URL de la base de datos desde variables de entorno"""
    # En producción usará PostgreSQL, en desarrollo SQLite
    database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        # SQLite por defecto para desarrollo
        database_url = "sqlite:///./incapacidades.db"
    
    # Render usa postgres:// pero SQLAlchemy necesita postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    return database_url

# Motor de base de datos
engine = create_engine(
    get_database_url(),
    echo=False,  # True para debug SQL
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Crea todas las tablas en la base de datos"""
    Base.metadata.create_all(bind=engine)
    print("✅ Base de datos inicializada correctamente")

def get_db():
    """Dependency para FastAPI - Obtiene sesión de BD"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()