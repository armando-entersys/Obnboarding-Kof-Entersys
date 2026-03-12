# app/utils/pdf_utils.py
"""
Generación de PDF de constancia de capacitación.
Diseño a página completa, profesional y limpio.
"""
import io
import logging
import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

# Colores corporativos
COLOR_RED = HexColor("#D91E18")
COLOR_YELLOW = HexColor("#FFC600")
COLOR_DARK = HexColor("#1a1a1a")
COLOR_GREEN = HexColor("#16a34a")
COLOR_RED_STATUS = HexColor("#dc2626")
COLOR_GRAY = HexColor("#6b7280")
COLOR_GRAY_LIGHT = HexColor("#f5f5f5")
COLOR_GRAY_BORDER = HexColor("#d1d5db")

# Path al logo
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "coca-cola-femsa-logo.png")

# Cached PDF logo in memory
_CACHED_PDF_LOGO = None


def _get_cached_pdf_logo():
    global _CACHED_PDF_LOGO
    if _CACHED_PDF_LOGO is None and os.path.exists(LOGO_PATH):
        _CACHED_PDF_LOGO = ImageReader(LOGO_PATH)
    return _CACHED_PDF_LOGO


def fetch_photo_from_url(url: str) -> Optional[bytes]:
    """Descarga una imagen desde una URL."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.warning(f"Error fetching photo from {url}: {e}")
    return None


def generate_certificate_pdf(
    collaborator_data: Dict[str, Any],
    section_results: Optional[Dict[str, Any]] = None,
    qr_image_bytes: Optional[bytes] = None
) -> bytes:
    """
    Genera un PDF de constancia a página completa.
    """
    buffer = io.BytesIO()

    # Crear canvas
    c = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter

    # Márgenes
    margin_x = 50
    margin_y = 40
    content_width = page_width - (margin_x * 2)

    is_approved = collaborator_data.get("is_approved", False)
    status_color = COLOR_GREEN if is_approved else COLOR_RED_STATUS
    resultado_text = "APROBADO" if is_approved else "NO APROBADO"

    # Extraer datos
    full_name = collaborator_data.get("full_name", collaborator_data.get("nombre_completo", "N/A"))
    rfc = collaborator_data.get("rfc", collaborator_data.get("rfc_colaborador", "N/A"))
    proveedor = collaborator_data.get("proveedor", "") or "N/A"
    tipo_servicio = collaborator_data.get("tipo_servicio", "") or "N/A"
    nss = collaborator_data.get("nss", "") or "N/A"
    rfc_empresa = collaborator_data.get("rfc_empresa", "") or "N/A"
    email = collaborator_data.get("email", "") or "N/A"
    vencimiento = collaborator_data.get("vencimiento", "N/A")
    fecha_emision = collaborator_data.get("fecha_emision", collaborator_data.get("fecha_examen", "N/A"))
    foto_url = collaborator_data.get("foto_url", "")

    # Validar que la foto esté disponible - nunca generar PDF sin foto
    if not foto_url:
        raise ValueError("No se puede generar el PDF sin foto del colaborador (foto_url vacío)")

    photo_bytes = fetch_photo_from_url(foto_url)
    if not photo_bytes:
        raise ValueError(f"No se puede generar el PDF: no se pudo descargar la foto desde {foto_url}")

    # ══════════════════════════════════════════════════════════════════
    # HEADER - Barra roja superior con logo
    # ══════════════════════════════════════════════════════════════════
    header_height = 80
    header_y = page_height - header_height

    # Barra roja
    c.setFillColor(COLOR_RED)
    c.rect(0, header_y, page_width, header_height, fill=1, stroke=0)

    # Logo centrado en el header
    if os.path.exists(LOGO_PATH):
        try:
            logo = _get_cached_pdf_logo()
            logo_w, logo_h = 140, 55
            logo_x = (page_width - logo_w) / 2
            logo_y = header_y + (header_height - logo_h) / 2
            c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 20)
            c.drawCentredString(page_width/2, header_y + 35, "COCA-COLA FEMSA")

    # Línea amarilla debajo del header
    c.setFillColor(COLOR_YELLOW)
    c.rect(0, header_y - 4, page_width, 4, fill=1, stroke=0)

    # ══════════════════════════════════════════════════════════════════
    # TÍTULO PRINCIPAL
    # ══════════════════════════════════════════════════════════════════
    title_y = header_y - 60
    c.setFillColor(COLOR_DARK)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(page_width/2, title_y, "CONSTANCIA DE CAPACITACIÓN")

    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica", 14)
    c.drawCentredString(page_width/2, title_y - 25, "Onboarding Seguridad KOF")

    # ══════════════════════════════════════════════════════════════════
    # SECCIÓN PRINCIPAL: FOTO + DATOS DEL COLABORADOR
    # ══════════════════════════════════════════════════════════════════
    section_y = title_y - 80

    # Foto a la izquierda
    photo_size = 140
    photo_x = margin_x + 30
    photo_y = section_y - photo_size

    # Marco de foto (rectángulo simple)
    c.setStrokeColor(COLOR_GRAY_BORDER)
    c.setLineWidth(2)
    c.rect(photo_x - 3, photo_y - 3, photo_size + 6, photo_size + 6, fill=0, stroke=1)

    # Fondo gris claro para la foto
    c.setFillColor(COLOR_GRAY_LIGHT)
    c.rect(photo_x, photo_y, photo_size, photo_size, fill=1, stroke=0)

    # Dibujar foto (ya validada y descargada arriba)
    photo_buffer = io.BytesIO(photo_bytes)
    photo_img = ImageReader(photo_buffer)
    c.drawImage(photo_img, photo_x, photo_y, width=photo_size, height=photo_size,
               preserveAspectRatio=True, mask='auto')

    # Datos a la derecha de la foto
    info_x = photo_x + photo_size + 40
    info_y = section_y - 10

    # Nombre grande
    c.setFillColor(COLOR_DARK)
    c.setFont("Helvetica-Bold", 20)
    name_display = str(full_name).upper()
    if len(name_display) > 30:
        name_display = name_display[:30] + "..."
    c.drawString(info_x, info_y, name_display)

    # RFC
    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica", 12)
    c.drawString(info_x, info_y - 25, f"RFC: {rfc}")

    # Badge de estado (rectángulo simple)
    badge_y = info_y - 60
    badge_width = 150
    badge_height = 32
    c.setFillColor(status_color)
    c.rect(info_x, badge_y, badge_width, badge_height, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(info_x + badge_width/2, badge_y + 10, resultado_text)

    # Empresa y tipo de servicio
    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(info_x, badge_y - 25, "EMPRESA")
    c.setFillColor(COLOR_DARK)
    c.setFont("Helvetica", 11)
    c.drawString(info_x, badge_y - 38, str(proveedor)[:35])

    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(info_x, badge_y - 60, "TIPO DE SERVICIO")
    c.setFillColor(COLOR_DARK)
    c.setFont("Helvetica", 11)
    c.drawString(info_x, badge_y - 73, str(tipo_servicio)[:35])

    # ══════════════════════════════════════════════════════════════════
    # LÍNEA SEPARADORA
    # ══════════════════════════════════════════════════════════════════
    separator_y = photo_y - 30
    c.setStrokeColor(COLOR_GRAY_BORDER)
    c.setLineWidth(1)
    c.line(margin_x, separator_y, page_width - margin_x, separator_y)

    # ══════════════════════════════════════════════════════════════════
    # INFORMACIÓN ADICIONAL EN 3 COLUMNAS
    # ══════════════════════════════════════════════════════════════════
    details_y = separator_y - 40
    col_width = content_width / 3
    col1_x = margin_x
    col2_x = margin_x + col_width
    col3_x = margin_x + col_width * 2

    def draw_field(x, y, label, value, max_chars=25):
        c.setFillColor(COLOR_GRAY)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, label)
        c.setFillColor(COLOR_DARK)
        c.setFont("Helvetica", 12)
        display_value = str(value)[:max_chars]
        c.drawString(x, y - 15, display_value)

    draw_field(col1_x, details_y, "NSS", nss)
    draw_field(col2_x, details_y, "RFC EMPRESA", rfc_empresa)
    draw_field(col3_x, details_y, "CORREO ELECTRÓNICO", email, 28)

    # ══════════════════════════════════════════════════════════════════
    # FECHAS Y QR
    # ══════════════════════════════════════════════════════════════════
    bottom_y = details_y - 80

    # Fechas a la izquierda
    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col1_x, bottom_y, "FECHA DE EMISIÓN")
    c.setFillColor(COLOR_DARK)
    c.setFont("Helvetica", 14)
    c.drawString(col1_x, bottom_y - 18, str(fecha_emision))

    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col1_x, bottom_y - 45, "VIGENTE HASTA")
    c.setFillColor(status_color)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(col1_x, bottom_y - 65, str(vencimiento))

    # QR a la derecha
    if qr_image_bytes:
        try:
            qr_size = 100
            qr_x = page_width - margin_x - qr_size
            qr_y = bottom_y - 70

            qr_buffer = io.BytesIO(qr_image_bytes)
            qr_img = ImageReader(qr_buffer)
            c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)

            c.setFillColor(COLOR_GRAY)
            c.setFont("Helvetica", 9)
            c.drawCentredString(qr_x + qr_size/2, qr_y - 12, "Escanea para verificar")
        except Exception as e:
            logger.warning(f"Could not draw QR: {e}")

    # ══════════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════════
    footer_y = margin_y + 20

    # Línea gris
    c.setStrokeColor(COLOR_GRAY_BORDER)
    c.setLineWidth(1)
    c.line(margin_x, footer_y + 15, page_width - margin_x, footer_y + 15)

    c.setFillColor(COLOR_GRAY)
    c.setFont("Helvetica", 9)
    footer_text = f"Documento generado el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC"
    c.drawCentredString(page_width/2, footer_y, footer_text)

    c.setFont("Helvetica", 8)
    c.drawCentredString(page_width/2, footer_y - 12, f"© {datetime.utcnow().year} FEMSA - Entersys")

    # Guardar página
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(f"PDF generated successfully, size: {len(pdf_bytes)} bytes")
    return pdf_bytes
