"""
Módulo para validar la calidad de imágenes adjuntas
Verifica que sean legibles: nitidez, brillo, resolución, ruido
"""

import cv2
import numpy as np
from PIL import Image
import io
from typing import Dict, Tuple
from pathlib import Path

class ImageQualityValidator:
    """Validador de calidad de imágenes para documentos médicos"""
    
    def __init__(self):
        # Umbrales de calidad
        self.MIN_BRIGHTNESS = 30
        self.MAX_BRIGHTNESS = 240
        self.MIN_SHARPNESS = 100  # Varianza del Laplaciano
        self.MIN_RESOLUTION = 300 * 300  # píxeles mínimos
        self.MAX_NOISE_LEVEL = 30
        self.MIN_CONTRAST = 20
        
    def validate_image_quality(self, image_path: Path) -> Dict:
        """
        Valida la calidad de una imagen
        
        Args:
            image_path: Ruta de la imagen a validar
            
        Returns:
            Dict con resultados de validación:
            {
                'is_legible': bool,
                'quality_score': int (0-100),
                'message': str,
                'details': dict con métricas individuales
            }
        """
        try:
            # Cargar imagen
            img = cv2.imread(str(image_path))
            if img is None:
                return self._error_result("No se pudo leer la imagen")
            
            # Convertir a escala de grises para análisis
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. Validar resolución
            height, width = img.shape[:2]
            resolution_pixels = width * height
            resolution_ok = resolution_pixels >= self.MIN_RESOLUTION
            
            # 2. Validar brillo
            brightness = np.mean(gray)
            brightness_ok = self.MIN_BRIGHTNESS < brightness < self.MAX_BRIGHTNESS
            
            # 3. Validar nitidez (usando Laplaciano)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            sharpness_ok = laplacian_var > self.MIN_SHARPNESS
            
            # 4. Validar ruido
            noise_level = self._calculate_noise(gray)
            noise_ok = noise_level < self.MAX_NOISE_LEVEL
            
            # 5. Validar contraste
            contrast = gray.std()
            contrast_ok = contrast > self.MIN_CONTRAST
            
            # Calcular puntuación de calidad
            checks = {
                'resolution': resolution_ok,
                'brightness': brightness_ok,
                'sharpness': sharpness_ok,
                'noise': noise_ok,
                'contrast': contrast_ok
            }
            
            quality_score = sum(checks.values()) / len(checks) * 100
            is_legible = quality_score >= 60
            
            # Generar mensaje
            message = self._generate_message(checks, brightness, laplacian_var, resolution_pixels)
            
            return {
                'is_legible': is_legible,
                'quality_score': int(quality_score),
                'message': message,
                'details': {
                    'brightness': float(brightness),
                    'sharpness': float(laplacian_var),
                    'resolution': f"{width}x{height}",
                    'noise_level': float(noise_level),
                    'contrast': float(contrast),
                    'checks': checks
                }
            }
            
        except Exception as e:
            return self._error_result(f"Error analizando imagen: {str(e)}")
    
    def validate_pdf_quality(self, pdf_path: Path) -> Dict:
        """
        Valida que un PDF sea legible
        Para PDFs, verificamos que sea válido pero no analizamos calidad
        """
        try:
            # Para PDFs solo verificamos que sea válido
            import fitz  # PyMuPDF
            pdf = fitz.open(pdf_path)
            num_pages = pdf.page_count
            pdf.close()
            
            if num_pages > 0:
                return {
                    'is_legible': True,
                    'quality_score': 100,
                    'message': f'PDF válido con {num_pages} página(s)',
                    'details': {'pages': num_pages}
                }
            else:
                return self._error_result("PDF vacío o corrupto")
                
        except Exception as e:
            return self._error_result(f"Error validando PDF: {str(e)}")
    
    def _calculate_noise(self, gray_image: np.ndarray) -> float:
        """Calcula el nivel de ruido usando desviación estándar local"""
        kernel_size = 5
        blur = cv2.GaussianBlur(gray_image, (kernel_size, kernel_size), 0)
        noise = np.std(gray_image - blur)
        return noise
    
    def _generate_message(self, checks: Dict, brightness: float, sharpness: float, resolution: int) -> str:
        """Genera mensaje descriptivo según los resultados"""
        if all(checks.values()):
            return "✓ Calidad aceptable - Imagen legible"
        
        issues = []
        if not checks['brightness']:
            if brightness < self.MIN_BRIGHTNESS:
                issues.append("imagen muy oscura")
            else:
                issues.append("imagen muy clara/sobreexpuesta")
        
        if not checks['sharpness']:
            issues.append("imagen borrosa o desenfocada")
        
        if not checks['resolution']:
            issues.append("resolución muy baja")
        
        if not checks['noise']:
            issues.append("imagen con mucho ruido")
        
        if not checks['contrast']:
            issues.append("bajo contraste")
        
        return f"✗ Problemas detectados: {', '.join(issues)}"
    
    def _error_result(self, message: str) -> Dict:
        """Retorna resultado de error"""
        return {
            'is_legible': False,
            'quality_score': 0,
            'message': message,
            'details': {}
        }

# Instancia global
image_validator = ImageQualityValidator()


def validate_uploaded_file(file_path: Path) -> Tuple[bool, str, Dict]:
    """
    Función helper para validar archivos subidos
    
    Args:
        file_path: Ruta del archivo a validar
        
    Returns:
        Tuple de (is_valid, message, details)
    """
    extension = file_path.suffix.lower()
    
    # Para PDFs
    if extension == '.pdf':
        result = image_validator.validate_pdf_quality(file_path)
        return result['is_legible'], result['message'], result['details']
    
    # Para imágenes
    elif extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']:
        result = image_validator.validate_image_quality(file_path)
        return result['is_legible'], result['message'], result['details']
    
    # Otros archivos se aceptan sin validación
    else:
        return True, "Archivo aceptado", {}