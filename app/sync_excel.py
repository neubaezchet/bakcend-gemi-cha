"""
Sincronizacion AUTOMATICA desde Google Sheets a PostgreSQL
Descarga el Excel cada 60 segundos desde Google Drive
No requiere hacer push a Git
"""

import os
import pandas as pd
import requests
from datetime import datetime
from app.database import SessionLocal, Employee, Company
from io import BytesIO

GOOGLE_DRIVE_FILE_ID = "1POt2ytSN61XbSpXUSUPyHdOVy2g7CRas"
EXCEL_DOWNLOAD_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_DRIVE_FILE_ID}/export?format=xlsx"
LOCAL_CACHE_PATH = "/tmp/base_empleados_cache.xlsx"

def descargar_excel_desde_drive():
    """Descarga el Excel desde Google Drive"""
    try:
        print(f"Descargando Excel desde Google Sheets...")
        response = requests.get(EXCEL_DOWNLOAD_URL, timeout=30)
        
        if response.status_code == 200:
            with open(LOCAL_CACHE_PATH, 'wb') as f:
                f.write(response.content)
            print(f"Excel descargado correctamente ({len(response.content)} bytes)")
            return LOCAL_CACHE_PATH
        else:
            print(f"Error descargando Excel: HTTP {response.status_code}")
            if os.path.exists(LOCAL_CACHE_PATH):
                print(f"Usando cache anterior")
                return LOCAL_CACHE_PATH
            return None
    except Exception as e:
        print(f"Error descargando Excel: {e}")
        if os.path.exists(LOCAL_CACHE_PATH):
            print(f"Usando cache anterior")
            return LOCAL_CACHE_PATH
        return None

def sincronizar_empleado_desde_excel(cedula: str):
    """Sincroniza UN empleado especifico (sync instantanea)"""
    db = SessionLocal()
    try:
        empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
        if empleado_bd:
            print(f"Empleado {cedula} ya esta en BD")
            return empleado_bd
        
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"No se pudo descargar el Excel")
            return None
        
        df = pd.read_excel(excel_path)
        try:
            cedula_int = int(cedula)
        except ValueError:
            print(f"Cedula invalida: {cedula}")
            return None
        
        empleado_excel = df[df["cedula"] == cedula_int]
        if empleado_excel.empty:
            print(f"Empleado {cedula} no encontrado en Excel")
            return None
        
        row = empleado_excel.iloc[0]
        empresa_nombre = row["empresa"]
        company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
        if not company:
            company = Company(nombre=empresa_nombre, activa=True)
            db.add(company)
            db.commit()
            db.refresh(company)
            print(f"Empresa creada: {empresa_nombre}")
        
        nuevo_empleado = Employee(
            cedula=str(row["cedula"]),
            nombre=row["nombre"],
            correo=row["correo"],
            telefono=str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None,
            company_id=company.id,
            eps=row.get("eps", None),
            activo=True
        )
        db.add(nuevo_empleado)
        db.commit()
        db.refresh(nuevo_empleado)
        print(f"Empleado {cedula} sincronizado: {nuevo_empleado.nombre}")
        return nuevo_empleado
    except Exception as e:
        print(f"Error sincronizando {cedula}: {e}")
        db.rollback()
        return None
    finally:
        db.close()

def sincronizar_excel_completo():
    """Sincroniza TODO el Excel a PostgreSQL (desde Google Sheets)"""
    db = SessionLocal()
    try:
        print(f"Iniciando sync Google Sheets a PostgreSQL...")
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"No se pudo descargar el Excel, sync cancelado")
            return
        
        df = pd.read_excel(excel_path)
        print(f"Excel cargado: {len(df)} filas")
        cedulas_excel = set(str(int(row["cedula"])) for _, row in df.iterrows() if pd.notna(row["cedula"]))
        empleados_bd = db.query(Employee).all()
        cedulas_bd = {emp.cedula for emp in empleados_bd}
        nuevos = actualizados = desactivados = 0
        
        for _, row in df.iterrows():
            try:
                if pd.isna(row.get("cedula")) or pd.isna(row.get("nombre")):
                    continue
                
                cedula = str(int(row["cedula"]))
                nombre = row["nombre"]
                correo = row.get("correo", "")
                telefono = str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None
                eps = row.get("eps", None)
                empresa_nombre = row["empresa"]
                company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                if not company:
                    company = Company(nombre=empresa_nombre, activa=True)
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                
                empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
                if not empleado:
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
            except Exception as e:
                print(f"Error en fila {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                db.commit()
                desactivados += 1
        
        if nuevos > 0 or actualizados > 0 or desactivados > 0:
            print(f"Sync completado: {nuevos} nuevos, {actualizados} actualizados, {desactivados} desactivados")
        else:
            print(f"Sync: Sin cambios detectados")
    except Exception as e:
        print(f"Error en sync: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()