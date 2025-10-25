"""
Gestor de Movimientos y Actualizaciones en Google Drive
IncaNeurobaeza - 2024
"""

import os
from pathlib import Path
from googleapiclient.http import MediaFileUpload
from app.drive_uploader import get_authenticated_service, create_folder_if_not_exists

class DriveFileManager:
    """Gestor de archivos en Google Drive"""
    
    def __init__(self):
        self.service = get_authenticated_service()
    
    def get_file_id_by_name(self, filename, parent_folder_id=None):
        """Busca un archivo por nombre en una carpeta específica"""
        query = f"name='{filename}' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, parents)'
        ).execute()
        
        files = results.get('files', [])
        return files[0]['id'] if files else None
    
    def update_file_content(self, file_id, new_file_path):
        """Actualiza el contenido de un archivo existente en Drive"""
        media = MediaFileUpload(str(new_file_path), mimetype='application/pdf', resumable=True)
        
        updated_file = self.service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id, webViewLink, modifiedTime'
        ).execute()
        
        return updated_file
    
    def move_file(self, file_id, new_parent_folder_id):
        """Mueve un archivo a una nueva carpeta"""
        # Obtener los padres actuales
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        
        # Mover archivo
        file = self.service.files().update(
            fileId=file_id,
            addParents=new_parent_folder_id,
            removeParents=previous_parents,
            fields='id, parents, webViewLink'
        ).execute()
        
        return file
    
    def get_or_create_folder_structure(self, empresa, estado):
        """
        Crea/obtiene la estructura de carpetas según el estado del caso
        
        Estructura:
        Mi_Unidad/Incapacidades/
        ├── Incapacidades_por_validar/{Empresa}/{Año}/{Quincena}/{Tipo}/
        ├── Incapacidades_validadas/{Empresa}/{Año}/{Quincena}/{Tipo}/
        ├── Completas/{Empresa}/
        └── Incompletas/{Empresa}/{Motivo}/
        """
        from datetime import datetime
        
        # Carpeta raíz
        main_folder_id = create_folder_if_not_exists(self.service, b'Incapacidades', 'root')
        
        # Determinar la carpeta según el estado
        if estado == 'NUEVO':
            base_folder = b'Incapacidades_por_validar'
        elif estado == 'COMPLETA':
            # Primero va a validadas, luego se copia a completas
            base_folder = b'Incapacidades_validadas'
        elif estado in ['INCOMPLETA', 'ILEGIBLE', 'INCOMPLETA_ILEGIBLE']:
            base_folder = b'Incompletas'
        elif estado == 'EPS_TRANSCRIPCION':
            base_folder = b'Incompletas'
        elif estado == 'DERIVADO_TTHH':
            base_folder = b'Incompletas'
        else:
            base_folder = b'Incapacidades_por_validar'
        
        base_folder_id = create_folder_if_not_exists(self.service, base_folder, main_folder_id)
        
        # Crear/obtener carpeta de empresa
        empresa_folder_id = create_folder_if_not_exists(self.service, empresa.encode(), base_folder_id)
        
        return empresa_folder_id


class CaseFileOrganizer:
    """Organizador de archivos de casos según su estado"""
    
    def __init__(self):
        self.drive_manager = DriveFileManager()
    
    def mover_caso_segun_estado(self, caso, nuevo_estado, motivo=None):
        """
        Mueve el archivo del caso a la carpeta correspondiente según el nuevo estado
        
        Args:
            caso: Objeto Case de la base de datos
            nuevo_estado: EstadoCaso nuevo
            motivo: Motivo del cambio (para carpetas de incompletas)
        """
        if not caso.drive_link:
            print(f"⚠️ Caso {caso.serial} no tiene link de Drive")
            return None
        
        # Extraer file_id del link de Drive
        file_id = self._extract_file_id_from_link(caso.drive_link)
        if not file_id:
            print(f"❌ No se pudo extraer file_id de {caso.drive_link}")
            return None
        
        # Obtener carpeta destino según el estado
        empresa_nombre = caso.empresa.nombre if caso.empresa else "OTRA_EMPRESA"
        
        try:
            if nuevo_estado == 'COMPLETA':
                # Caso COMPLETA: 
                # 1. Mover a Incapacidades_validadas/{Empresa}/
                # 2. Crear COPIA en Completas/{Empresa}/
                validadas_folder = self.drive_manager.get_or_create_folder_structure(
                    empresa_nombre, 'COMPLETA'
                )
                
                # Mover a validadas
                self.drive_manager.move_file(file_id, validadas_folder)
                
                # Crear copia en Completas
                completas_main = create_folder_if_not_exists(
                    self.drive_manager.service, b'Completas', 'root'
                )
                completas_empresa = create_folder_if_not_exists(
                    self.drive_manager.service, 
                    empresa_nombre.encode(), 
                    completas_main
                )
                
                # Copiar archivo
                copied_file = self.drive_manager.service.files().copy(
                    fileId=file_id,
                    body={'parents': [completas_empresa]}
                ).execute()
                
                print(f"✅ Caso {caso.serial} → Validadas + Completas")
                return self._get_file_link(file_id)
            
            elif nuevo_estado in ['INCOMPLETA', 'ILEGIBLE', 'INCOMPLETA_ILEGIBLE']:
                # Mover a Incompletas/{Empresa}/{Motivo}/
                incompletas_main = create_folder_if_not_exists(
                    self.drive_manager.service, b'Incompletas', 'root'
                )
                incompletas_empresa = create_folder_if_not_exists(
                    self.drive_manager.service, 
                    empresa_nombre.encode(), 
                    incompletas_main
                )
                
                # Crear subcarpeta según motivo
                if 'ilegible' in nuevo_estado.lower():
                    subfolder_name = b'Ilegibles'
                else:
                    subfolder_name = b'Faltan_Soportes'
                
                subfolder_id = create_folder_if_not_exists(
                    self.drive_manager.service,
                    subfolder_name,
                    incompletas_empresa
                )
                
                self.drive_manager.move_file(file_id, subfolder_id)
                print(f"✅ Caso {caso.serial} → Incompletas/{subfolder_name.decode()}")
                return self._get_file_link(file_id)
            
            elif nuevo_estado == 'EPS_TRANSCRIPCION':
                # Mover a Incompletas/{Empresa}/EPS_No_Transcritas/
                incompletas_main = create_folder_if_not_exists(
                    self.drive_manager.service, b'Incompletas', 'root'
                )
                incompletas_empresa = create_folder_if_not_exists(
                    self.drive_manager.service, 
                    empresa_nombre.encode(), 
                    incompletas_main
                )
                eps_folder = create_folder_if_not_exists(
                    self.drive_manager.service,
                    b'EPS_No_Transcritas',
                    incompletas_empresa
                )
                
                self.drive_manager.move_file(file_id, eps_folder)
                print(f"✅ Caso {caso.serial} → Incompletas/EPS_No_Transcritas")
                return self._get_file_link(file_id)
            
            elif nuevo_estado == 'DERIVADO_TTHH':
                # Mover a Incompletas/{Empresa}/Falsas/ o THH_Falsas/
                incompletas_main = create_folder_if_not_exists(
                    self.drive_manager.service, b'Incompletas', 'root'
                )
                incompletas_empresa = create_folder_if_not_exists(
                    self.drive_manager.service, 
                    empresa_nombre.encode(), 
                    incompletas_main
                )
                falsas_folder = create_folder_if_not_exists(
                    self.drive_manager.service,
                    b'THH_Falsas',
                    incompletas_empresa
                )
                
                self.drive_manager.move_file(file_id, falsas_folder)
                print(f"✅ Caso {caso.serial} → Incompletas/THH_Falsas")
                return self._get_file_link(file_id)
        
        except Exception as e:
            print(f"❌ Error moviendo caso {caso.serial}: {e}")
            return None
    
    def actualizar_pdf_editado(self, caso, edited_pdf_path):
        """
        Actualiza el PDF en Drive con la versión editada
        
        Args:
            caso: Objeto Case
            edited_pdf_path: Path al PDF editado localmente
        """
        if not caso.drive_link:
            return None
        
        file_id = self._extract_file_id_from_link(caso.drive_link)
        if not file_id:
            return None
        
        try:
            updated_file = self.drive_manager.update_file_content(file_id, edited_pdf_path)
            print(f"✅ PDF actualizado en Drive: {caso.serial}")
            return updated_file.get('webViewLink')
        except Exception as e:
            print(f"❌ Error actualizando PDF {caso.serial}: {e}")
            return None
    
    def _extract_file_id_from_link(self, drive_link):
        """Extrae el file_id de un link de Google Drive"""
        if '/file/d/' in drive_link:
            return drive_link.split('/file/d/')[1].split('/')[0]
        elif 'id=' in drive_link:
            return drive_link.split('id=')[1].split('&')[0]
        return None
    
    def _get_file_link(self, file_id):
        """Obtiene el link de visualización de un archivo"""
        return f"https://drive.google.com/file/d/{file_id}/view"