import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

class SimpleTrackingSystem:
    def __init__(self):
        # Archivo JSON para guardar el estado de las incapacidades
        self.data_file = Path("data/tracking_data.json")
        self.data_file.parent.mkdir(exist_ok=True)
        
        # Cargar datos existentes
        self.load_data()

    def load_data(self):
        """Cargar datos del archivo JSON"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.tracking_data = json.load(f)
            else:
                self.tracking_data = {}
        except Exception as e:
            print(f"Error cargando datos de tracking: {e}")
            self.tracking_data = {}

    def save_data(self):
        """Guardar datos al archivo JSON"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracking_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error guardando datos de tracking: {e}")

    def create_tracking(self, consecutivo: str, cedula: str, nombre: str = "", 
                       empresa: str = "", telefono: str = "", email: str = "",
                       archivos: list = None) -> Dict[str, Any]:
        """Crear nuevo registro de seguimiento"""
        
        tracking_info = {
            "consecutivo": consecutivo,
            "cedula": cedula,
            "nombre": nombre,
            "empresa": empresa,
            "telefono": telefono,
            "email": email,
            "archivos": archivos or [],
            "estado_actual": "recibido",
            "fecha_creacion": datetime.now().isoformat(),
            "historial": [
                {
                    "estado": "recibido",
                    "fecha": datetime.now().isoformat(),
                    "descripcion": "Documentación recibida y registrada en el sistema",
                    "usuario": "Sistema"
                }
            ]
        }
        
        self.tracking_data[consecutivo] = tracking_info
        self.save_data()
        
        return tracking_info

    def get_tracking_info(self, consecutivo: str) -> Optional[Dict[str, Any]]:
        """Obtener información de seguimiento"""
        return self.tracking_data.get(consecutivo)

    def get_progress_percentage(self, estado_actual: str) -> int:
        """Obtener porcentaje de progreso según el estado"""
        progress_map = {
            "recibido": 25,
            "en_revision": 50,
            "aprobado": 75,
            "radicado": 100,
            "devuelto": 30,
            "rechazado": 0
        }
        return progress_map.get(estado_actual, 0)

    def get_next_steps(self, estado_actual: str) -> list:
        """Obtener próximos pasos según el estado actual"""
        next_steps = {
            "recibido": [
                "📋 Revisión inicial de documentos",
                "✅ Validación de requisitos",
                "👤 Asignación a especialista revisor"
            ],
            "en_revision": [
                "🔍 Análisis detallado de documentación",
                "📊 Verificación con base de datos",
                "⚖️ Evaluación para aprobación"
            ],
            "aprobado": [
                "📝 Preparación para radicación oficial",
                "💾 Carga en sistema gubernamental",
                "📧 Notificación de finalización"
            ],
            "radicado": [
                "✅ ¡Proceso completado exitosamente!"
            ],
            "devuelto": [
                "📄 Revisar observaciones detalladas",
                "🔄 Corregir documentos según indicaciones",
                "📤 Reenviar documentación corregida"
            ],
            "rechazado": [
                "📋 Revisar motivos específicos de rechazo",
                "📞 Contactar soporte para orientación",
                "🔄 Evaluar nueva solicitud si aplica"
            ]
        }
        return next_steps.get(estado_actual, [])

    def get_status_color(self, estado: str) -> str:
        """Obtener color para el estado"""
        colors = {
            "recibido": "#17a2b8",      # info
            "en_revision": "#ffc107",    # warning  
            "aprobado": "#28a745",      # success
            "radicado": "#28a745",      # success
            "devuelto": "#fd7e14",      # orange
            "rechazado": "#dc3545"      # danger
        }
        return colors.get(estado, "#6c757d")