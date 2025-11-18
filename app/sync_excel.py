"""
Sincronización AUTOMÁTICA Google Sheets → PostgreSQL
✅ SOLUCIÓN DEFINITIVA a todos los problemas
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
        
        df = pd.read_excel(excel_path, sheet_name=0)
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
    ✅ SINCRONIZACIÓN DEFINITIVA
    - Primero sincroniza empresas (Hoja 2) con emails
    - Luego sincroniza empleados (Hoja 1)
    - Elimina/desactiva lo que ya no está en Excel
    """
    db = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print(f"🔄 SYNC Google Sheets → PostgreSQL - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}\n")
        
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel, sync cancelado\n")
            return
        
        # ========== PASO 1: SYNC EMPRESAS (HOJA 2) ==========
        print(f"📊 PASO 1: Sincronizando empresas (Hoja 2)...")
        empresas_actualizadas = 0
        
        try:
            # Intentar leer Hoja 2 con diferentes nombres posibles
            df_empresas = None
            nombres_posibles = ['Hoja 2', 'Empresas', 'Sheet2', 'Hoja2']
            
            for nombre_hoja in nombres_posibles:
                try:
                    df_empresas = pd.read_excel(excel_path, sheet_name=nombre_hoja)
                    print(f"   ✅ Hoja encontrada: '{nombre_hoja}' ({len(df_empresas)} filas)")
                    break
                except:
                    continue
            
            if df_empresas is None:
                print(f"   ⚠️ No se encontró Hoja 2. Nombres intentados: {nombres_posibles}")
                print(f"   ⚠️ Continuando sin sincronizar emails de copia...\n")
            else:
                # Procesar empresas
                for _, row in df_empresas.iterrows():
                    try:
                        # Detectar columna de nombre (puede ser 'nombre' o 'empresa')
                        nombre_col = 'nombre' if 'nombre' in df_empresas.columns else 'empresa'
                        
                        if pd.isna(row.get(nombre_col)) or pd.isna(row.get('email_copia')):
                            continue
                        
                        empresa_nombre = str(row[nombre_col]).strip()
                        email_copia = str(row['email_copia']).strip()
                        
                        # Buscar empresa en BD
                        empresa = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                        
                        if empresa:
                            # Actualizar email de copia
                            if empresa.email_copia != email_copia:
                                empresa.email_copia = email_copia
                                empresa.contacto_email = email_copia
                                empresa.updated_at = datetime.utcnow()
                                db.commit()
                                empresas_actualizadas += 1
                                print(f"   🔄 {empresa_nombre} → {email_copia}")
                        else:
                            # Crear empresa nueva
                            nueva_empresa = Company(
                                nombre=empresa_nombre,
                                email_copia=email_copia,
                                contacto_email=email_copia,
                                activa=True
                            )
                            db.add(nueva_empresa)
                            db.commit()
                            empresas_actualizadas += 1
                            print(f"   ➕ {empresa_nombre} → {email_copia}")
                    
                    except Exception as e:
                        print(f"   ❌ Error en empresa '{row.get(nombre_col, 'N/A')}': {e}")
                        db.rollback()
                
                if empresas_actualizadas > 0:
                    print(f"   ✅ {empresas_actualizadas} empresas actualizadas\n")
                else:
                    print(f"   ℹ️ Sin cambios en empresas\n")
        
        except Exception as e:
            print(f"   ❌ Error leyendo Hoja 2: {e}\n")
        
        # ========== PASO 2: SYNC EMPLEADOS (HOJA 1) ==========
        print(f"📊 PASO 2: Sincronizando empleados (Hoja 1)...")
        
        df = pd.read_excel(excel_path, sheet_name=0)
        print(f"   📋 {len(df)} filas cargadas")
        
        # Obtener cédulas del Excel
        cedulas_excel = set()
        for _, row in df.iterrows():
            if pd.notna(row.get("cedula")):
                try:
                    cedulas_excel.add(str(int(row["cedula"])))
                except:
                    pass
        
        print(f"   📋 {len(cedulas_excel)} cédulas únicas en Excel")
        
        # Obtener empleados actuales de BD
        empleados_bd = db.query(Employee).all()
        print(f"   📋 {len(empleados_bd)} empleados en BD")
        
        nuevos = actualizados = desactivados = 0
        
        # Procesar cada empleado del Excel
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
                
                jefe_nombre = row.get("jefe_nombre", None)
                jefe_email = row.get("jefe_email", None)
                jefe_cargo = row.get("jefe_cargo", None)
                area_trabajo = row.get("area_trabajo", None)
                
                # Buscar o crear empresa
                company = db.query(Company).filter(Company.nombre == empresa_nombre).first()
                if not company:
                    company = Company(nombre=empresa_nombre, activa=True)
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                
                # Buscar empleado por cédula
                empleado = db.query(Employee).filter(Employee.cedula == cedula).first()
                
                if not empleado:
                    # CREAR NUEVO
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
                    # ACTUALIZAR EXISTENTE
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
                        empleado.updated_at = datetime.utcnow()
                        db.commit()
                        actualizados += 1
            
            except Exception as e:
                print(f"   ❌ Error en fila {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        # DESACTIVAR empleados que ya NO están en Excel
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                empleado.updated_at = datetime.utcnow()
                db.commit()
                desactivados += 1
        
        # RESUMEN
        print(f"\n{'='*60}")
        print(f"✅ SYNC COMPLETADO")
        print(f"   • Empresas actualizadas: {empresas_actualizadas}")
        print(f"   • Empleados nuevos: {nuevos}")
        print(f"   • Empleados actualizados: {actualizados}")
        print(f"   • Empleados desactivados: {desactivados}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ ERROR GENERAL EN SYNC: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()