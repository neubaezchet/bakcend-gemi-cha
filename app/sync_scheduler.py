"""
Sincronización automática Excel → PostgreSQL + Verificación de Drive
Ejecuta cada 1 MINUTO (Excel) y cada 5 MINUTOS (Drive token)
"""

from apscheduler.schedulers.background import BackgroundScheduler
from app.sync_excel import sincronizar_excel_completo
import datetime

def verificar_drive_token():
    """Verifica el estado del token de Drive cada 5 minutos"""
    try:
        from app.drive_uploader import get_authenticated_service
        
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 Verificando token de Drive...")
        service = get_authenticated_service()
        
        # Si llegamos aquí, el token está OK
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Token de Drive verificado")
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️ Error verificando token: {e}")

def iniciar_sincronizacion_automatica():
    """
    Inicia scheduler de sincronización automática
    ⏱️ Excel: Ejecuta cada 1 MINUTO
    ⏱️ Drive: Verifica cada 5 MINUTOS
    """
    
    scheduler = BackgroundScheduler()
    
    # ✅ Sincronización de Excel (cada 60 segundos)
    scheduler.add_job(
        sincronizar_excel_completo,
        'interval',
        seconds=60,
        id='sync_excel_to_postgresql',
        name='Sincronización Excel → PostgreSQL',
        replace_existing=True
    )
    
    # ✅ Verificación de Drive token (cada 5 minutos)
    scheduler.add_job(
        verificar_drive_token,
        'interval',
        minutes=5,
        id='verificar_drive_token',
        name='Verificación de Token de Google Drive',
        replace_existing=True
    )
    
    scheduler.start()
    
    print("🔄 Sincronización automática activada:")
    print("   • Excel → PostgreSQL: cada 1 minuto")
    print("   • Token de Drive: cada 5 minutos")
    
    # Ejecutar sync inicial inmediatamente
    sincronizar_excel_completo()
    verificar_drive_token()
    
    return scheduler