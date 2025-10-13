"""
Sincronización automática Excel → PostgreSQL
Ejecuta cada 5 minutos para mantener la BD actualizada
"""

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
import pandas as pd
import os
from datetime import datetime

from app.database import SessionLocal, Employee, Company

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

def sincronizar_excel_a_bd():
    """
    Sincroniza el Excel con PostgreSQL
    - Agrega empleados nuevos
    - Actualiza datos modificados
    - Marca empleados inactivos si fueron eliminados del Excel
    """
    
    db = SessionLocal()
    
    try:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Iniciando sincronización Excel → PostgreSQL...")
        
        # Leer Excel
        df = pd.read_excel(DATA_PATH)
        
        # Obtener todas las cédulas del Excel
        cedulas_excel = set(str(row["cedula"]) for _, row in df.iterrows())
        
        # Obtener todas las cédulas de PostgreSQL
        empleados_bd = db.query(Employee).all()
        cedulas_bd = {emp.cedula for emp in empleados_bd}
        
        nuevos = 0
        actualizados = 0
        desactivados = 0
        
        # Procesar cada empleado del Excel
        for _, row in df.iterrows():
            try:
                cedula = str(row["cedula"])
                nombre = row["nombre"]
                correo = row["correo"]
                telefono = row.get("telefono", None)
                eps = row.get("eps", None)
                empresa_nombre = row["empresa"]
                
                # Verificar/crear empresa
                company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                if not company:
                    company = Company(nombre=empresa_nombre, activa=True)
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                    print(f"  ✅ Empresa creada: {empresa_nombre}")
                
                # Verificar si empleado existe
                empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
                
                if not empleado:
                    # NUEVO empleado
                    nuevo_empleado = Employee(
                        cedula=cedula,
                        nombre=nombre,
                        correo=correo,
                        telefono=telefono,
                        company_id=company.id,
                        eps=eps,
                        activo=True
                    )
                    db.add(nuevo_empleado)
                    db.commit()
                    nuevos += 1
                    print(f"  ➕ Nuevo: {nombre} ({cedula})")
                else:
                    # ACTUALIZAR si hay cambios
                    cambios = False
                    
                    if empleado.nombre != nombre:
                        empleado.nombre = nombre
                        cambios = True
                    
                    if empleado.correo != correo:
                        empleado.correo = correo
                        cambios = True
                    
                    if empleado.telefono != telefono:
                        empleado.telefono = telefono
                        cambios = True
                    
                    if empleado.eps != eps:
                        empleado.eps = eps
                        cambios = True
                    
                    if empleado.company_id != company.id:
                        empleado.company_id = company.id
                        cambios = True
                    
                    if not empleado.activo:
                        empleado.activo = True
                        cambios = True
                    
                    if cambios:
                        db.commit()
                        actualizados += 1
                        print(f"  🔄 Actualizado: {nombre} ({cedula})")
                
            except Exception as e:
                print(f"  ❌ Error procesando {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        # Desactivar empleados que ya no están en el Excel
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                db.commit()
                desactivados += 1
                print(f"  ⏸️  Desactivado: {empleado.nombre} ({empleado.cedula})")
        
        print(f"✅ Sincronización completada: {nuevos} nuevos, {actualizados} actualizados, {desactivados} desactivados")
        
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo Excel en {DATA_PATH}")
    except Exception as e:
        print(f"❌ Error en sincronización: {e}")
        db.rollback()
    finally:
        db.close()

def iniciar_sincronizacion_automatica():
    """
    Inicia el scheduler de sincronización automática
    Ejecuta cada 5 minutos
    """
    
    scheduler = BackgroundScheduler()
    
    # Ejecutar cada 5 minutos
    scheduler.add_job(
        sincronizar_excel_a_bd,
        'interval',
        minutes=5,
        id='sync_excel_to_postgresql',
        name='Sincronización Excel → PostgreSQL',
        replace_existing=True
    )
    
    scheduler.start()
    
    print("🔄 Sincronización automática activada cada 5 minutos")
    
    # Ejecutar sincronización inicial inmediatamente
    sincronizar_excel_a_bd()
    
    return scheduler