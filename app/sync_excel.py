"""
Sincronizacion AUTOMATICA desde Google Sheets a PostgreSQL
Ahora incluye Pestaña 2: Empresas con emails de copia
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
        print(f"📥 Descargando Excel desde Google Sheets...")
        response = requests.get(EXCEL_DOWNLOAD_URL, timeout=30)
        
        if response.status_code == 200:
            with open(LOCAL_CACHE_PATH, 'wb') as f:
                f.write(response.content)
            print(f"✅ Excel descargado correctamente ({len(response.content)} bytes)")
            return LOCAL_CACHE_PATH
        else:
            print(f"❌ Error descargando Excel: HTTP {response.status_code}")
            if os.path.exists(LOCAL_CACHE_PATH):
                print(f"⚠️ Usando cache anterior")
                return LOCAL_CACHE_PATH
            return None
    except Exception as e:
        print(f"❌ Error descargando Excel: {e}")
        if os.path.exists(LOCAL_CACHE_PATH):
            print(f"⚠️ Usando cache anterior")
            return LOCAL_CACHE_PATH
        return None


# ✅ NUEVA FUNCIÓN: Sincronizar empresas desde Pestaña 2
def sincronizar_empresas_desde_excel():
    """
    Sincroniza la Pestaña 2: Empresas desde Google Sheets
    Actualiza los emails de copia automáticamente
    """
    db = SessionLocal()
    try:
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel para sync de empresas")
            return
        
        # ✅ Leer la Pestaña 2: "Empresas"
        try:
            df_empresas = pd.read_excel(excel_path, sheet_name='Empresas')
            print(f"📊 Pestaña 'Empresas' cargada: {len(df_empresas)} filas")
        except Exception as e:
            print(f"⚠️ No se encontró la pestaña 'Empresas': {e}")
            print(f"   Verifica que el Excel tenga una pestaña llamada 'Empresas'")
            return
        
        actualizados = creados = 0
        
        for _, row in df_empresas.iterrows():
            try:
                if pd.isna(row.get('empresa')) or pd.isna(row.get('email_copia')):
                    continue
                
                empresa_nombre = str(row['empresa']).strip()
                email_copia = str(row['email_copia']).strip()
                contacto_principal = row.get('contacto_principal', None)
                
                # Buscar o crear empresa en BD
                empresa = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                
                if not empresa:
                    # Crear nueva empresa
                    empresa = Company(
                        nombre=empresa_nombre,
                        email_copia=email_copia,
                        contacto_email=email_copia,  # También como contacto principal
                        activa=True
                    )
                    db.add(empresa)
                    db.commit()
                    creados += 1
                    print(f"  ✅ Empresa creada: {empresa_nombre} → {email_copia}")
                else:
                    # Actualizar email de copia si cambió
                    if empresa.email_copia != email_copia:
                        empresa.email_copia = email_copia
                        db.commit()
                        actualizados += 1
                        print(f"  🔄 Email actualizado: {empresa_nombre} → {email_copia}")
            
            except Exception as e:
                print(f"❌ Error en fila empresa '{row.get('empresa', 'N/A')}': {e}")
                db.rollback()
        
        if creados > 0 or actualizados > 0:
            print(f"✅ Sync empresas completado: {creados} nuevas, {actualizados} actualizadas")
        else:
            print(f"ℹ️ Sync empresas: Sin cambios detectados")
    
    except Exception as e:
        print(f"❌ Error en sync empresas: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def sincronizar_empleado_desde_excel(cedula: str):
    """Sincroniza UN empleado especifico (sync instantanea)"""
    db = SessionLocal()
    try:
        empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
        if empleado_bd:
            print(f"✅ Empleado {cedula} ya esta en BD")
            return empleado_bd
        
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel")
            return None
        
        df = pd.read_excel(excel_path, sheet_name=0)  # Primera pestaña
        try:
            cedula_int = int(cedula)
        except ValueError:
            print(f"❌ Cedula invalida: {cedula}")
            return None
        
        empleado_excel = df[df["cedula"] == cedula_int]
        if empleado_excel.empty:
            print(f"❌ Empleado {cedula} no encontrado en Excel")
            return None
        
        row = empleado_excel.iloc[0]
        empresa_nombre = row["empresa"]
        company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
        if not company:
            company = Company(nombre=empresa_nombre, activa=True)
            db.add(company)
            db.commit()
            db.refresh(company)
            print(f"✅ Empresa creada: {empresa_nombre}")
        
        # Incluir información de jefes
        nuevo_empleado = Employee(
            cedula=str(row["cedula"]),
            nombre=row["nombre"],
            correo=row["correo"],
            telefono=str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None,
            company_id=company.id,
            eps=row.get("eps", None),
            jefe_nombre=row.get("jefe_nombre", None),
            jefe_email=row.get("jefe_email", None),
            jefe_cargo=row.get("jefe_cargo", None),
            area_trabajo=row.get("area_trabajo", None),
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
    """
    Sincroniza TODO el Excel a PostgreSQL (desde Google Sheets)
    Incluye ambas pestañas: Empleados y Empresas
    """
    db = SessionLocal()
    try:
        print(f"🔄 Iniciando sync Google Sheets a PostgreSQL...")
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel, sync cancelado")
            return
        
        # ========== SYNC PESTAÑA 1: EMPLEADOS ==========
        df = pd.read_excel(excel_path, sheet_name=0)  # Primera pestaña
        print(f"📊 Pestaña 'Empleados' cargada: {len(df)} filas")
        
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
                
                # Extraer datos de jefes
                jefe_nombre = row.get("jefe_nombre", None)
                jefe_email = row.get("jefe_email", None)
                jefe_cargo = row.get("jefe_cargo", None)
                area_trabajo = row.get("area_trabajo", None)
                
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
                        jefe_nombre=jefe_nombre,
                        jefe_email=jefe_email,
                        jefe_cargo=jefe_cargo,
                        area_trabajo=area_trabajo,
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
                    
                    # Actualizar datos de jefes
                    if empleado.jefe_nombre != jefe_nombre:
                        empleado.jefe_nombre = jefe_nombre
                        cambios = True
                    if empleado.jefe_email != jefe_email:
                        empleado.jefe_email = jefe_email
                        cambios = True
                    if empleado.jefe_cargo != jefe_cargo:
                        empleado.jefe_cargo = jefe_cargo
                        cambios = True
                    if empleado.area_trabajo != area_trabajo:
                        empleado.area_trabajo = area_trabajo
                        cambios = True
                    
                    if not empleado.activo: 
                        empleado.activo = True
                        cambios = True
                    if cambios:
                        db.commit()
                        actualizados += 1
            except Exception as e:
                print(f"❌ Error en fila {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                db.commit()
                desactivados += 1
        
        if nuevos > 0 or actualizados > 0 or desactivados > 0:
            print(f"✅ Sync empleados: {nuevos} nuevos, {actualizados} actualizados, {desactivados} desactivados")
        else:
            print(f"ℹ️ Sync empleados: Sin cambios detectados")
        
        # ========== SYNC PESTAÑA 2: EMPRESAS ==========
        sincronizar_empresas_desde_excel()
        
    except Exception as e:
        print(f"❌ Error en sync: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()