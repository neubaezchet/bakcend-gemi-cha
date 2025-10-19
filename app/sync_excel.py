"""
Sincronización AUTOMÁTICA desde Google Sheets → PostgreSQL
✅ Descarga el Excel cada 60 segundos desde Google Drive
✅ No requiere hacer push a Git
"""

import os
import pandas as pd
import requests
from datetime import datetime
from app.database import SessionLocal, Employee, Company
from io import BytesIO

# ==================== CONFIGURACIÓN ====================
# ID del archivo de Google Drive (extraído de tu enlace)
GOOGLE_DRIVE_FILE_ID = "1POt2ytSN61XbSpXUSUPyHdOVy2g7CRas"
EXCEL_DOWNLOAD_URL = f"https://docs.google.com/spreadsheets/d/1POt2ytSN61XbSpXUSUPyHdOVy2g7CRas/edit?usp=sharing&ouid=109080049357282633841&rtpof=true&sd=true"

# Caché local (Render usa /tmp)
LOCAL_CACHE_PATH = "/tmp/base_empleados_cache.xlsx"

# ==================== FUNCIONES ====================

def descargar_excel_desde_drive():
    """Descarga el Excel desde Google Drive"""
    try:
        print(f"📥 [{datetime.now().strftime('%H:%M:%S')}] Descargando Excel desde Google Sheets...")
        
        response = requests.get(EXCEL_DOWNLOAD_URL, timeout=30)
        
        if response.status_code == 200:
            # Guardar en caché local
            with open(LOCAL_CACHE_PATH, 'wb') as f:
                f.write(response.content)
            print(f"✅ Excel descargado correctamente ({len(response.content)} bytes)")
            return LOCAL_CACHE_PATH
        else:
            print(f"❌ Error descargando Excel: HTTP {response.status_code}")
            # Si falla, usar caché anterior si existe
            if os.path.exists(LOCAL_CACHE_PATH):
                print(f"⚠️  Usando caché anterior")
                return LOCAL_CACHE_PATH
            return None
            
    except Exception as e:
        print(f"❌ Error descargando Excel: {e}")
        # Usar caché si existe
        if os.path.exists(LOCAL_CACHE_PATH):
            print(f"⚠️  Usando caché anterior")
            return LOCAL_CACHE_PATH
        return None

def sincronizar_empleado_desde_excel(cedula: str):
    """Sincroniza UN empleado específico (sync instantánea)"""
    db = SessionLocal()
    
    try:
        # Verificar si existe en BD
        empleado_bd = db.query(Employee).filter(Employee.cedula == cedula).first()
        
        if empleado_bd:
            print(f"✅ Empleado {cedula} ya está en BD")
            return empleado_bd
        
        # Descargar Excel desde Drive
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel")
            return None
        
        df = pd.read_excel(excel_path)
        
        # Convertir cedula a int para comparar
        try:
            cedula_int = int(cedula)
        except ValueError:
            print(f"❌ Cédula inválida: {cedula}")
            return None
        
        empleado_excel = df[df["cedula"] == cedula_int]
        
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
            telefono=str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None,
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
    """Sincroniza TODO el Excel a PostgreSQL (desde Google Sheets)"""
    db = SessionLocal()
    
    try:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Iniciando sync Google Sheets → PostgreSQL...")
        
        # Descargar Excel desde Drive
        excel_path = descargar_excel_desde_drive()
        if not excel_path:
            print(f"❌ No se pudo descargar el Excel, sync cancelado")
            return
        
        df = pd.read_excel(excel_path)
        print(f"📊 Excel cargado: {len(df)} filas")
        
        cedulas_excel = set(str(int(row["cedula"])) for _, row in df.iterrows() if pd.notna(row["cedula"]))
        empleados_bd = db.query(Employee).all()
        cedulas_bd = {emp.cedula for emp in empleados_bd}
        
        nuevos = actualizados = desactivados = 0
        
        for _, row in df.iterrows():
            try:
                # Validar que la fila tenga datos
                if pd.isna(row.get("cedula")) or pd.isna(row.get("nombre")):
                    continue
                
                cedula = str(int(row["cedula"]))
                nombre = row["nombre"]
                correo = row.get("correo", "")
                telefono = str(row.get("telefono", "")) if pd.notna(row.get("telefono")) else None
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
                print(f"  ❌ Error en fila {row.get('cedula', 'N/A')}: {e}")
                db.rollback()
        
        # Desactivar eliminados
        for empleado in empleados_bd:
            if empleado.cedula not in cedulas_excel and empleado.activo:
                empleado.activo = False
                db.commit()
                desactivados += 1
        
        if nuevos > 0 or actualizados > 0 or desactivados > 0:
            print(f"✅ Sync completado: {nuevos} nuevos, {actualizados} actualizados, {desactivados} desactivados")
        else:
            print(f"ℹ️  Sync: Sin cambios detectados")
        
    except Exception as e:
        print(f"❌ Error en sync: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()
```

---

## 🔒 **PASO 2: Hacer el Google Sheets PÚBLICO**

**IMPORTANTE**: El enlace que me diste requiere autenticación. Necesitas hacerlo público.

### **2.1 Ir a tu Google Sheet:**
```
https://docs.google.com/spreadsheets/d/1POt2ytSN61XbSpXUSUPyHdOVy2g7CRas/edit?usp=sharing&ouid=109080049357282633841&rtpof=true&sd=true
```

### **2.2 Click en "Compartir" (arriba derecha)**

### **2.3 En "Acceso general", cambiar a:**
```
✅ Cualquier persona con el enlace → Lector
```

### **2.4 Click en "Copiar enlace" y verifica que sea así:**
```
https://docs.google.com/spreadsheets/d/1POt2ytSN61XbSpXUSUPyHdOVy2g7CRas/edit?usp=sharing&ouid=109080049357282633841&rtpof=true&sd=true