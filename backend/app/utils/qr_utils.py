# app/utils/qr_utils.py
import qrcode
from qrcode.image.pil import PilImage
from io import BytesIO
import base64
import logging
from typing import Optional
from PIL import Image
import os

logger = logging.getLogger(__name__)

# Path to Entersys black symbol logo
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "entersys_symbol_black.png")

# Cached logo in memory
_CACHED_LOGO = None


def _get_cached_logo():
    global _CACHED_LOGO
    if _CACHED_LOGO is None and os.path.exists(LOGO_PATH):
        _CACHED_LOGO = Image.open(LOGO_PATH).convert('RGBA')
    return _CACHED_LOGO.copy() if _CACHED_LOGO else None


def add_logo_to_qr(qr_img: Image.Image, logo_path: str, logo_size_ratio: float = 0.22) -> Image.Image:
    """
    Agrega un logo en el centro del código QR con diseño profesional.

    Args:
        qr_img: Imagen del QR code
        logo_path: Ruta al archivo del logo
        logo_size_ratio: Ratio del tamaño del logo respecto al QR (default 0.22 = 22%)

    Returns:
        Imagen QR con logo en el centro
    """
    try:
        # Usar logo cacheado en memoria, fallback a disco
        logo = _get_cached_logo()
        if logo is None:
            logo = Image.open(logo_path)
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')

        # Calcular tamaño del logo
        qr_width, qr_height = qr_img.size
        logo_max_size = int(min(qr_width, qr_height) * logo_size_ratio)

        # Redimensionar logo manteniendo aspect ratio
        logo.thumbnail((logo_max_size, logo_max_size), Image.Resampling.LANCZOS)

        # Crear fondo blanco circular con borde para el logo (estilo profesional)
        # Tamaño del fondo: 15% más grande que el logo
        bg_size = int(logo_max_size * 1.15)

        # Crear máscara circular
        mask = Image.new('L', (bg_size, bg_size), 0)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, bg_size, bg_size), fill=255)

        # Crear fondo blanco circular
        logo_bg = Image.new('RGBA', (bg_size, bg_size), (255, 255, 255, 0))
        white_circle = Image.new('RGBA', (bg_size, bg_size), (255, 255, 255, 255))
        logo_bg.paste(white_circle, (0, 0), mask)

        # Calcular posición centrada del logo en el background
        logo_pos_x = (bg_size - logo.size[0]) // 2
        logo_pos_y = (bg_size - logo.size[1]) // 2

        # Pegar logo en el fondo blanco
        logo_bg.paste(logo, (logo_pos_x, logo_pos_y), logo if logo.mode == 'RGBA' else None)

        # Convertir QR a RGBA para composición
        if qr_img.mode != 'RGBA':
            qr_img = qr_img.convert('RGBA')

        # Calcular posición centrada en el QR
        qr_pos_x = (qr_width - bg_size) // 2
        qr_pos_y = (qr_height - bg_size) // 2

        # Pegar logo+background en el centro del QR
        qr_img.paste(logo_bg, (qr_pos_x, qr_pos_y), logo_bg)

        # Convertir de vuelta a RGB para PNG
        qr_img = qr_img.convert('RGB')

        logger.info(f"Logo added to QR successfully with professional styling")
        return qr_img

    except Exception as e:
        logger.warning(f"Could not add logo to QR: {str(e)}. Returning QR without logo.")
        return qr_img


def generate_qr_code(
    data: str,
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
    add_logo: bool = True
) -> bytes:
    """
    Genera un código QR como imagen PNG en bytes.

    Args:
        data: Datos a codificar en el QR (URL, texto, etc.)
        box_size: Tamaño de cada caja del QR en píxeles
        border: Tamaño del borde en cajas
        fill_color: Color de los módulos del QR
        back_color: Color de fondo del QR
        add_logo: Si debe agregar el logo de Entersys en el centro

    Returns:
        Imagen PNG del QR en bytes

    Raises:
        ValueError: Si los datos están vacíos
        Exception: Si hay un error generando el QR
    """
    if not data:
        raise ValueError("QR data cannot be empty")

    try:
        # Crear instancia del QR con configuración
        # Usar ERROR_CORRECT_H para permitir logo sin perder legibilidad
        qr = qrcode.QRCode(
            version=1,  # Auto-ajusta basado en datos
            error_correction=qrcode.constants.ERROR_CORRECT_H if add_logo else qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )

        # Agregar datos al QR
        qr.add_data(data)
        qr.make(fit=True)

        # Generar imagen
        img: PilImage = qr.make_image(fill_color=fill_color, back_color=back_color)

        # Convertir a PIL Image para manipulación
        img = img.convert('RGB')

        # Agregar logo si está habilitado y el archivo existe
        if add_logo and os.path.exists(LOGO_PATH):
            img = add_logo_to_qr(img, LOGO_PATH)

        # Convertir a bytes
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        qr_bytes = buffer.getvalue()
        logger.info(f"QR code generated successfully, size: {len(qr_bytes)} bytes")

        return qr_bytes

    except Exception as e:
        logger.error(f"Error generating QR code: {str(e)}")
        raise


def generate_qr_code_base64(
    data: str,
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
    add_logo: bool = True
) -> str:
    """
    Genera un código QR y lo retorna como string base64.

    Args:
        data: Datos a codificar en el QR
        box_size: Tamaño de cada caja del QR en píxeles
        border: Tamaño del borde en cajas
        fill_color: Color de los módulos del QR
        back_color: Color de fondo del QR
        add_logo: Si debe agregar el logo de Entersys en el centro

    Returns:
        String base64 de la imagen PNG del QR
    """
    qr_bytes = generate_qr_code(
        data=data,
        box_size=box_size,
        border=border,
        fill_color=fill_color,
        back_color=back_color,
        add_logo=add_logo
    )

    return base64.b64encode(qr_bytes).decode('utf-8')


def generate_validation_url(uuid: str) -> str:
    """
    Genera la URL de validación para el código QR.

    Apunta directamente al frontend que hará la llamada al API.

    Args:
        uuid: UUID del certificado

    Returns:
        URL completa de validación (frontend)
    """
    return f"https://entersys.mx/certificacion-seguridad/{uuid}"


def generate_certificate_qr(uuid: str, base_url: str = "https://api.entersys.mx") -> bytes:
    """
    Genera el código QR para un certificado de onboarding.

    Función de conveniencia que combina la generación de URL y QR.
    El QR apunta directamente al frontend.

    Args:
        uuid: UUID del certificado
        base_url: URL base (no usado, mantenido por compatibilidad)

    Returns:
        Imagen PNG del QR en bytes
    """
    validation_url = generate_validation_url(uuid)

    # Usar colores corporativos de Entersys
    return generate_qr_code(
        data=validation_url,
        box_size=10,
        border=4,
        fill_color="#093D53",  # Color primario de Entersys
        back_color="white"
    )
