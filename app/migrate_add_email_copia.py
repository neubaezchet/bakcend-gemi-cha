"""
Script de migración: Agregar columna email_copia a companies
Ejecutar: python migrate_add_email_copia.py
"""

from sqlalchemy import text
from database import engine, SessionLocal

def migrar_agregar_email_copia():
    """Agrega columna email_copia a la tabla companies"""
    
    print("🔄 Agregando columna email_copia a tabla companies...\n")
    
    db = SessionLocal()
    
    try:
        # Agregar columna
        sql = "ALTER TABLE companies ADD COLUMN IF NOT EXISTS email_copia VARCHAR(500);"
        
        db.execute(text(sql))
        db.commit()
        print("✅ Columna email_copia agregada")
        
        # Verificar
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='companies' 
            AND column_name='email_copia';
        """))
        
        if result.fetchone():
            print("✅ Verificación exitosa: columna existe\n")
        else:
            print("⚠️ Advertencia: columna no encontrada\n")
        
        # Mostrar estructura actual
        print("📋 Estructura actual de 'companies':")
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='companies'
            ORDER BY ordinal_position;
        """))
        
        for row in result:
            print(f"  • {row[0]}: {row[1]}")
        
        print("\n✅ Migración completada\n")
        
    except Exception as e:
        print(f"❌ Error en migración: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════╗
║     MIGRACIÓN: Agregar email_copia a companies       ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    migrar_agregar_email_copia()
    
    print("""
╔═══════════════════════════════════════════════════════╗
║  ✅ Listo. Ahora actualiza los emails en cada empresa ║
╚═══════════════════════════════════════════════════════╝
    """)