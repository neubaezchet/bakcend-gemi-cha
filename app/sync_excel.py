"""
Sincronización INSTANTÁNEA Excel → PostgreSQL
"""

import os
import pandas as pd
from datetime import datetime
from app.database import SessionLocal, Employee, Company

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

def sincronizar_empleado_desde_excel(cedula: str):
    """Sincroniza UN empleado específico (sync instantánea)"""
    db = SessionLocal()
    
    try:
        # Verificar si existe en BD
        empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
        
        if empleado_bd:
            print(f"✅ Empleado {cedula} ya está en BD")
            return empleado_bd
        
        # Buscar en Excel
        if not os.path.exists(DATA_PATH):
            print(f"⚠️ Excel no encontrado: {DATA_PATH}")
            return None
        
        df = pd.read_excel(DATA_PATH)
        empleado_excel = df[df["cedula"] == int(cedula)]
        
        if empleado_excel.empty:
            print(f"❌ Empleado {cedula} no encontrado en Excel")
            return None
        
        # Crear empleado en BD
        row = empleado_excel.iloc[0]
        empresa_nombre = row["empresa"]
        
        # Verificar/crear empresa
        company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
        if not company:
            company = Company(nombre=empresa_nombre, activa=True)
            db.add(company)
            db.commit()
            db.refresh(company)
            print(f"  ✅ Empresa creada: {empresa_nombre}")
        
        # Crear empleado
        nuevo_empleado = Employee(
            cedula=str(row["cedula"]),
            nombre=row["nombre"],
            correo=row["correo"],
            telefono=row.get("telefono", None),
            company_id=company.id,
            eps=row.get("eps", None),
            activo=True
        )
        db.add(nuevo_empleado)
        db.commit()
        db.refresh(nuevo_empleado)
        
        print(f"✅ Empleado {cedula} sincronizado: {nuevo_empleado.nombre}")
        return nuevo_empleado
        
    except Exception as e:
        print(f"❌ Error sincronizando {cedula}: {e}")
        db.rollback()
        return None
    finally:
        db.close()

def sincronizar_excel_completo():
    """Sincroniza TODO el Excel a PostgreSQL"""
    db = SessionLocal()
    
    try:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Iniciando sync Excel → PostgreSQL...")
        
        if not os.path.exists(DATA_PATH):
            print(f"❌ Excel no encontrado: {DATA_PATH}")
            return
        
        df = pd.read_excel(DATA_PATH)
        cedulas_excel = set(str(row["cedula"]) for _, row in df.iterrows())
        empleados_bd = db.query(Employee).all()
        cedulas_bd = {emp.cedula for emp in empleados_bd}
        
        nuevos = actualizados = desactivados = 0
        
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
                
                empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
                
                if not empleado:
                    # NUEVO
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
                else:
                    # ACTUALIZAR
                    cambios = False
                    if empleado.nombre != nombre: empleado.nombre, cambios = nombre, True
                    if empleado.correo != correo: empleado.correo, cambios = correo, True
                    if empleado.telefono != telefono: empleado.telefono, cambios = telefono, True
                    if empleado.eps != eps: empleado.eps, cambios = eps, True
                    if empleado.company_id != company.id: empleado.company_id, cambios = company.id, True
                    if not empleado.activo: empleado.activo, cambios = True, True
                    
                    if cambios:
                        db.commit()
                        actualizados += 1
                
            except Exception as e:
                print(f"  ❌ Error en {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        # Desactivar eliminados
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                db.commit()
                desactivados += 1
        
        if nuevos > 0 or actualizados > 0 or desactivados > 0:
            print(f"✅ Sync: {nuevos} nuevos, {actualizados} actualizados, {desactivados} desactivados")
        
    except Exception as e:
        print(f"❌ Error en sync: {e}")
        db.rollback()
    finally:
        db.close()