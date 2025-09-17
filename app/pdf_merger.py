import tempfile
import shutil
from pathlib import Path
from typing import List, Tuple
from fastapi import UploadFile
import fitz  # PyMuPDF
from PIL import Image
import io

async def merge_pdfs_from_uploads(archivos: List[UploadFile], cedula: str, tipo: str) -> Tuple[Path, List[str]]:
    """
    Combina múltiples archivos (PDF, imágenes) en un solo PDF
    
    Args:
        archivos: Lista de archivos subidos
        cedula: Cédula del empleado
        tipo: Tipo de incapacidad
        
    Returns:
        Tuple con la ruta del PDF final y lista de nombres originales
    """
    if not archivos:
        raise ValueError("No se proporcionaron archivos")
    
    # Crear PDF de salida
    pdf_output = fitz.open()
    original_filenames = []
    temp_files = []
    
    try:
        for i, archivo in enumerate(archivos):
            if not archivo or not archivo.filename:
                continue
                
            original_filenames.append(archivo.filename)
            
            # Guardar archivo temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(archivo.filename).suffix) as tmp:
                shutil.copyfileobj(archivo.file, tmp)
                temp_path = Path(tmp.name)
                temp_files.append(temp_path)
            
            # Resetear el archivo para próxima lectura si es necesario
            archivo.file.seek(0)
            
            # Procesar según el tipo de archivo
            file_extension = Path(archivo.filename).suffix.lower()
            
            if file_extension == '.pdf':
                # Agregar PDF existente
                pdf_input = fitz.open(temp_path)
                pdf_output.insert_pdf(pdf_input)
                pdf_input.close()
                
            elif file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                # Convertir imagen a PDF
                img_pdf = convert_image_to_pdf(temp_path)
                if img_pdf:
                    pdf_output.insert_pdf(img_pdf)
                    img_pdf.close()
                    
            elif file_extension in ['.doc', '.docx']:
                # Para documentos Word, crear una página indicativa
                page = pdf_output.new_page()
                text = f"Documento Word incluido:\n{archivo.filename}\n\nNota: Para ver el contenido completo, abrir el archivo original."
                page.insert_text((50, 50), text, fontsize=12)
                
            else:
                # Para otros tipos de archivo, crear página informativa
                page = pdf_output.new_page()
                text = f"Archivo adjunto:\n{archivo.filename}\n\nTipo: {file_extension}\nNota: Archivo no soportado para vista previa."
                page.insert_text((50, 50), text, fontsize=12)
    
    except Exception as e:
        # Limpiar archivos temporales en caso de error
        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)
        pdf_output.close()
        raise Exception(f"Error procesando archivos: {e}")
    
    finally:
        # Limpiar archivos temporales
        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)
    
    # Agregar página de portada al inicio
    add_cover_page(pdf_output, cedula, tipo, original_filenames)
    
    # Guardar PDF final
    pdf_final_path = Path(tempfile.mktemp(suffix=f'_{cedula}_{tipo}.pdf'))
    pdf_output.save(pdf_final_path)
    pdf_output.close()
    
    return pdf_final_path, original_filenames


def convert_image_to_pdf(image_path: Path) -> fitz.Document:
    """Convierte una imagen a PDF usando PyMuPDF"""
    try:
        # Abrir imagen con PIL para mejor manejo
        with Image.open(image_path) as img:
            # Convertir a RGB si es necesario
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Guardar como bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PDF')
            img_bytes.seek(0)
            
            # Crear PDF desde bytes
            pdf_doc = fitz.open(stream=img_bytes.getvalue(), filetype="pdf")
            return pdf_doc
            
    except Exception as e:
        print(f"Error convirtiendo imagen {image_path}: {e}")
        return None


def add_cover_page(pdf_doc: fitz.Document, cedula: str, tipo: str, filenames: List[str]):
    """Agrega una página de portada al PDF con logo y QR"""
    from datetime import datetime
    import urllib.request
    
    # Insertar página al inicio
    cover_page = pdf_doc.new_page(0)
    
    # Logo de Neurobaeza (pequeño, esquina superior izquierda)
    try:
        # Crear un rectángulo simple para simular el logo por ahora
        logo_rect = fitz.Rect(50, 50, 120, 90)
        cover_page.draw_rect(logo_rect, color=(0.4, 0.47, 0.92), width=2, fill=(0.95, 0.95, 1))  # Azul claro
        cover_page.insert_text((60, 75), "NEURO", fontsize=12, color=(0.4, 0.47, 0.92))
        cover_page.insert_text((60, 87), "BAEZA", fontsize=8, color=(0.4, 0.47, 0.92))
    except:
        pass
    
    # Título principal (centrado)
    page_width = cover_page.rect.width
    cover_page.insert_text(
        (page_width/2 - 100, 120), 
        "INCAPACIDAD MÉDICA", 
        fontsize=18, 
        color=(0.2, 0.3, 0.8)
    )
    
    # Consecutivo/Radicado (grande y destacado)
    consecutivo = f"Radicado: {cedula}-{datetime.now().strftime('%Y%m%d')}"
    cover_page.insert_text(
        (50, 160), 
        consecutivo, 
        fontsize=14, 
        color=(0.4, 0.4, 0.4)
    )
    
    # Tabla de información (estilo similar al email)
    y_start = 200
    table_data = [
        ("Cédula:", cedula),
        ("Tipo:", tipo),
        ("Fecha recibido:", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Estado:", "En revisión")
    ]
    
    # Dibujar tabla
    for i, (label, value) in enumerate(table_data):
        y_pos = y_start + (i * 25)
        cover_page.insert_text((70, y_pos), label, fontsize=11, color=(0.4, 0.4, 0.4))
        cover_page.insert_text((150, y_pos), value, fontsize=11, color=(0.2, 0.2, 0.2))
    
    # QR Code (lado derecho de la tabla)
    try:
        qr_data = f"INC-{cedula}-{datetime.now().strftime('%Y%m%d')}"
        # Por ahora, dibujar un cuadrado para representar el QR
        qr_rect = fitz.Rect(400, 200, 470, 270)
        cover_page.draw_rect(qr_rect, color=(0.3, 0.3, 0.3), width=1)
        cover_page.insert_text((405, 240), "QR CODE", fontsize=8, color=(0.5, 0.5, 0.5))
        cover_page.insert_text((405, 255), qr_data[:10], fontsize=6, color=(0.5, 0.5, 0.5))
    except:
        pass
    
    # Pasos del proceso (nueva sección)
    y_process = 350
    cover_page.insert_text((50, y_process), "Proceso de radicación:", fontsize=12, color=(0.3, 0.3, 0.3))
    
    process_steps = [
        "1. ✓ Documentos recibidos",
        "2. ⏳ Revisión en curso",
        "3. ⏳ Validación de requisitos", 
        "4. ⏳ Carga al sistema",
        "5. ⏳ Notificación final"
    ]
    
    for i, step in enumerate(process_steps):
        y_pos = y_process + 30 + (i * 20)
        color = (0.2, 0.6, 0.2) if "✓" in step else (0.6, 0.6, 0.6)
        cover_page.insert_text((70, y_pos), step, fontsize=10, color=color)
    
    # Lista de documentos
    y_docs = 500
    cover_page.insert_text((50, y_docs), "Documentos incluidos:", fontsize=12, color=(0.3, 0.3, 0.3))
    
    for i, filename in enumerate(filenames, 1):
        if i <= 8:  # Máximo 8 archivos para que quepa en la página
            y_pos = y_docs + 20 + (i * 18)
            cover_page.insert_text((70, y_pos), f"{i}. {filename}", fontsize=9, color=(0.2, 0.2, 0.2))
    
    if len(filenames) > 8:
        cover_page.insert_text((70, y_docs + 20 + (9 * 18)), f"... y {len(filenames) - 8} archivos más", fontsize=9, color=(0.5, 0.5, 0.5))
    
    # Pie de página con logo y eslogan
    footer_y = 750
    cover_page.insert_text(
        (50, footer_y), 
        "IncaNeurobaeza", 
        fontsize=12, 
        color=(0.4, 0.47, 0.92)
    )
    cover_page.insert_text(
        (50, footer_y + 15), 
        '"Trabajando para ayudarte"', 
        fontsize=10, 
        color=(0.6, 0.6, 0.6)
    )