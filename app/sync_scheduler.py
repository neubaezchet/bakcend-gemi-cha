"""
Sincronización automática Excel → PostgreSQL
Ejecuta cada 1 MINUTO para mantener BD actualizada
"""

from apscheduler.schedulers.background import BackgroundScheduler
from app.sync_excel import sincronizar_excel_completo

def iniciar_sincronizacion_automatica():
    """
    Inicia scheduler de sincronización automática
    ⏱️ Ejecuta cada 1 MINUTO
    """
    
    scheduler = BackgroundScheduler()
    
    # ✅ Ejecutar cada 1 MINUTO (60 segundos)
    scheduler.add_job(
        sincronizar_excel_completo,
        'interval',
        seconds=60,  # ← 1 minuto
        id='sync_excel_to_postgresql',
        name='Sincronización Excel → PostgreSQL',
        replace_existing=True
    )
    
    scheduler.start()
    
    print("🔄 Sincronización automática activada cada 1 minuto")
    
    # Ejecutar sync inicial inmediatamente
    sincronizar_excel_completo()
    
    return scheduler