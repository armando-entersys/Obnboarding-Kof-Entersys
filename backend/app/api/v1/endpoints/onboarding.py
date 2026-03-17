# app/api/v1/endpoints/onboarding.py
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, status, UploadFile, File, Form, Depends, Header
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import random
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
from urllib.parse import quote
import os
import io
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from sqlalchemy.orm import Session, selectinload

# Gmail API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build

import time
import traceback
from threading import Lock

from pydantic import BaseModel, Field, field_validator
from google.cloud import storage
from app.core.config import settings
from app.schemas.onboarding_schemas import (
    OnboardingGenerateRequest,
    OnboardingGenerateResponse,
    OnboardingGenerateData,
    OnboardingErrorResponse,
    ExamSubmitRequest,
    ExamSubmitResponse,
    ExamStatusResponse,
    SectionResult,
    ResendCertificateRequest,
    ResendCertificateResponse,
    ExamCategoryOut,
    ExamQuestionOut,
    ExamConfigResponse,
)
from app.models.exam import ExamCategory, ExamQuestion
from app.db.session import get_db


class CertificateInfoResponse(BaseModel):
    """Response model for certificate info endpoint"""
    success: bool
    status: str  # 'approved', 'not_approved', 'expired', 'not_found'
    nombre: str
    vencimiento: str
    score: float
    is_expired: bool
    message: str
    url_imagen: Optional[str] = None  # URL de la foto de credencial


class CredentialResponse(BaseModel):
    """Response model for virtual credential endpoint"""
    success: bool
    status: str  # 'approved', 'not_approved', 'expired', 'not_found'
    nombre: str
    rfc: str
    proveedor: Optional[str] = None
    tipo_servicio: Optional[str] = None
    nss: Optional[str] = None
    rfc_empresa: Optional[str] = None  # RFC de la empresa
    email: Optional[str] = None
    cert_uuid: Optional[str] = None
    vencimiento: Optional[str] = None
    fecha_emision: Optional[str] = None
    url_imagen: Optional[str] = None  # URL de la foto de credencial en GCS
    is_expired: bool = False
    message: str
    # Campos de alto riesgo (hoja 6.3 Biblioteca de Personal Terceros)
    alto_riesgo: bool = False
    edad: Optional[str] = None
    alto_riesgo_data: Optional[dict] = None  # Ficha técnica extendida
from app.services.onboarding_smartsheet_service import (
    OnboardingSmartsheetService,
    OnboardingSmartsheetServiceError,
    get_onboarding_service_singleton,
)
from app.utils.pdf_utils import generate_certificate_pdf
from app.utils.qr_utils import generate_certificate_qr
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Constantes
MINIMUM_SCORE = 80.0
CERTIFICATE_VALIDITY_DAYS = 365
MAX_ATTEMPTS = 3
API_BASE_URL = "https://api.entersys.mx"
REDIRECT_VALID = "https://entersys.mx/certificacion-seguridad"
REDIRECT_INVALID = "https://entersys.mx/access-denied"

# ============================================================
# TRACKING: Contador de usuarios concurrentes en examen
# ============================================================
_exam_concurrent_lock = Lock()
_exam_concurrent_count = 0
_exam_concurrent_peak = 0
_cert_generation_count = 0


def get_onboarding_service() -> OnboardingSmartsheetService:
    """Dependency para obtener instancia del servicio"""
    return get_onboarding_service_singleton()


def send_email_via_gmail_api(
    to_emails: List[str],
    subject: str,
    html_content: str,
    attachments: List[dict] = None
) -> bool:
    """
    Envía un email usando el servicio centralizado de Gmail.
    Wrapper de compatibilidad sobre GmailService.
    """
    from app.services.gmail_service import gmail_service
    success, _, _ = gmail_service.send_email(
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        attachments=attachments,
    )
    return success


def send_email_via_smtp(
    to_emails: List[str],
    subject: str,
    html_content: str,
    attachments: List[dict] = None
) -> bool:
    """Wrapper que usa Gmail API. Mantiene nombre por compatibilidad."""
    return send_email_via_gmail_api(to_emails, subject, html_content, attachments)


def send_email_via_resend(
    to_emails: List[str],
    subject: str,
    html_content: str,
    attachments: List[dict] = None
) -> bool:
    """Wrapper que usa Gmail API. Mantiene nombre por compatibilidad."""
    return send_email_via_gmail_api(to_emails, subject, html_content, attachments)


def send_qr_email(
    email_to: str,
    full_name: str,
    qr_image: bytes,
    expiration_date: datetime,
    cert_uuid: str,
    is_valid: bool = True,
    score: float = 0.0,
    collaborator_data: dict = None,
    section_results: dict = None
) -> bool:
    """
    Envía el email con el código QR y PDF del certificado adjuntos.

    Args:
        email_to: Email del destinatario
        full_name: Nombre completo del usuario
        qr_image: Imagen del QR en bytes
        expiration_date: Fecha de vencimiento del certificado
        cert_uuid: UUID del certificado
        is_valid: Si el certificado es válido (score >= 80)
        score: Puntuación obtenida
        collaborator_data: Datos adicionales del colaborador para el PDF (opcional)
        section_results: Resultados por sección para el PDF (opcional)

    Returns:
        True si el email se envió exitosamente
    """
    try:
        # Definir asunto según resultado
        if is_valid:
            subject = f"Onboarding Aprobado - {full_name}"
        else:
            subject = f"Onboarding No Aprobado - {full_name}"

        # Contenido HTML del email - diferente según si aprobó o no
        if is_valid:
            # Email para certificado aprobado - Branding FEMSA
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        background-color: #f9fafb;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 8px;
                        padding: 30px;
                        margin: 20px 0;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        text-align: center;
                        margin-bottom: 30px;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #FFC600;
                    }}
                    .logo {{
                        max-height: 80px;
                        margin-bottom: 15px;
                    }}
                    h1 {{
                        color: #1f2937;
                        font-size: 24px;
                        margin: 0;
                    }}
                    .certificate-info {{
                        background-color: #f0fdf4;
                        border-left: 4px solid #16a34a;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 4px;
                    }}
                    .qr-section {{
                        text-align: center;
                        margin: 30px 0;
                        padding: 20px;
                        background-color: #f9fafb;
                        border-radius: 8px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid #e5e7eb;
                        font-size: 12px;
                        color: #6b7280;
                    }}
                    .highlight {{
                        color: #16a34a;
                        font-weight: bold;
                    }}
                    .accent {{
                        color: #D91E18;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="https://entersys.mx/images/coca-cola-femsa-logo.png" alt="FEMSA" class="logo">
                        <h1>Onboarding Aprobado</h1>
                    </div>

                    <p>Estimado/a <strong>{full_name}</strong>,</p>

                    <p>Tu certificación de Seguridad Industrial ha sido validada correctamente. Has cumplido con todos los requisitos del curso y tu información ha sido aprobada conforme a los estándares de seguridad establecidos.</p>

                    <div class="certificate-info">
                        <p><strong>Detalles de la Certificación:</strong></p>
                        <ul>
                            <li>Calificación: <span class="highlight">{score:.2f}%</span></li>
                            <li>Estado: <span class="highlight">APROBADO</span></li>
                            <li>Fecha de Emisión: <span class="highlight">{datetime.utcnow().strftime('%d/%m/%Y')}</span></li>
                            <li>Válido hasta: <span class="highlight">{expiration_date.strftime('%d/%m/%Y')}</span></li>
                        </ul>
                    </div>

                    <div class="qr-section">
                        <p><strong>Tu código QR de acceso está adjunto a este correo.</strong></p>
                        <p>Preséntalo al personal de seguridad en cada ingreso a las instalaciones.</p>
                    </div>

                    <p><strong>Instrucciones:</strong></p>
                    <ol>
                        <li>Guarda este correo y el código QR adjunto.</li>
                        <li>Puedes imprimir el QR o mostrarlo desde tu dispositivo móvil.</li>
                        <li>El personal de seguridad escaneará tu código para verificar tu certificación.</li>
                    </ol>

                    <div class="footer">
                        <p>Este es un correo automático, por favor no respondas a este mensaje.</p>
                        <p>&copy; {datetime.utcnow().year} FEMSA - Entersys. Todos los derechos reservados.</p>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # Email para certificado NO aprobado - Branding FEMSA
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        background-color: #f9fafb;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 8px;
                        padding: 30px;
                        margin: 20px 0;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        text-align: center;
                        margin-bottom: 30px;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #FFC600;
                    }}
                    .logo {{
                        max-height: 80px;
                        margin-bottom: 15px;
                    }}
                    h1 {{
                        color: #1f2937;
                        font-size: 24px;
                        margin: 0;
                    }}
                    .result-info {{
                        background-color: #FEE2E2;
                        border-left: 4px solid #D91E18;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 4px;
                    }}
                    .qr-section {{
                        text-align: center;
                        margin: 30px 0;
                        padding: 20px;
                        background-color: #f9fafb;
                        border-radius: 8px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid #e5e7eb;
                        font-size: 12px;
                        color: #6b7280;
                    }}
                    .highlight-fail {{
                        color: #D91E18;
                        font-weight: bold;
                    }}
                    .next-steps {{
                        background-color: #FEF3C7;
                        border-left: 4px solid #F59E0B;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 4px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="https://entersys.mx/images/coca-cola-femsa-logo.png" alt="FEMSA" class="logo">
                        <h1>Onboarding No Aprobado</h1>
                    </div>

                    <p>Estimado/a <strong>{full_name}</strong>,</p>

                    <p>Tu certificación de Seguridad Industrial no pudo ser validada. La información proporcionada o los requisitos del curso no cumplen con los estándares mínimos de seguridad establecidos.</p>

                    <div class="result-info">
                        <p><strong>Resultado de la Evaluación:</strong></p>
                        <ul>
                            <li>Calificación Obtenida: <span class="highlight-fail">{score:.2f}%</span></li>
                            <li>Calificación Mínima Requerida: <span class="highlight-fail">80%</span></li>
                            <li>Estado: <span class="highlight-fail">NO APROBADO</span></li>
                        </ul>
                    </div>

                    <div class="next-steps">
                        <p><strong>Próximos Pasos:</strong></p>
                        <p>Por favor revisa las observaciones enviadas, corrige la información o completa los requisitos faltantes para volver a enviar tu solicitud de validación:</p>
                        <ol>
                            <li>Revisar el material de capacitación nuevamente</li>
                            <li>Solicitar una nueva evaluación a su supervisor</li>
                            <li>Obtener una calificación mínima de 80%</li>
                        </ol>
                    </div>

                    <div class="qr-section">
                        <p><strong>Se adjunta un código QR de referencia.</strong></p>
                        <p>Este código NO es válido para acceso a las instalaciones.</p>
                    </div>

                    <p>Si tiene preguntas sobre el proceso de re-evaluación, contacte a su supervisor o al departamento de seguridad.</p>

                    <div class="footer">
                        <p>Este es un correo automático, por favor no respondas a este mensaje.</p>
                        <p>&copy; {datetime.utcnow().year} FEMSA - Entersys. Todos los derechos reservados.</p>
                    </div>
                </div>
            </body>
            </html>
            """

        # Preparar adjuntos
        attachments = []

        # Adjunto QR
        qr_attachment = {
            "filename": f"certificado_qr_{cert_uuid[:8]}.png",
            "content": base64.b64encode(qr_image).decode('utf-8')
        }
        attachments.append(qr_attachment)

        # Generar y adjuntar PDF si está aprobado
        if is_valid:
            try:
                # Preparar datos para el PDF
                pdf_data = collaborator_data.copy() if collaborator_data else {}
                pdf_data.update({
                    "full_name": full_name,
                    "email": email_to,
                    "cert_uuid": cert_uuid,
                    "vencimiento": expiration_date.strftime('%d/%m/%Y'),
                    "fecha_emision": datetime.utcnow().strftime('%d/%m/%Y'),
                    "is_approved": True,
                })
                # Map url_imagen -> foto_url for PDF generation
                if "foto_url" not in pdf_data and "url_imagen" in pdf_data:
                    pdf_data["foto_url"] = pdf_data["url_imagen"]

                # Generar PDF (will raise ValueError if photo is not available)
                pdf_bytes = generate_certificate_pdf(
                    collaborator_data=pdf_data,
                    section_results=section_results,
                    qr_image_bytes=qr_image
                )

                pdf_attachment = {
                    "filename": f"certificado_{cert_uuid[:8]}.pdf",
                    "content": base64.b64encode(pdf_bytes).decode('utf-8')
                }
                attachments.append(pdf_attachment)
                logger.info(f"PDF attachment generated for {email_to}")
            except Exception as e:
                logger.warning(f"Could not generate PDF attachment: {e}")

        # Enviar email via SMTP
        result = send_email_via_resend(
            to_emails=[email_to],
            subject=subject,
            html_content=html_content,
            attachments=attachments
        )

        if result:
            logger.info(f"QR email sent successfully to {email_to}")
        return result

    except Exception as e:
        logger.error(f"Error sending QR email to {email_to}: {str(e)}")
        return False


async def update_last_validation_background(
    sheet_id: int,
    row_id: int
) -> None:
    """
    Tarea en background para actualizar la última validación.

    Args:
        sheet_id: ID de la hoja
        row_id: ID de la fila
    """
    try:
        service = get_onboarding_service_singleton()
        await service.update_last_validation(sheet_id, row_id)
        logger.info(f"Background task completed: updated last validation for row {row_id}")
    except Exception as e:
        logger.error(f"Background task failed: {str(e)}")


def send_third_attempt_alert_email(
    colaborador_data: dict,
    attempts_info: dict
) -> bool:
    """
    Envía un correo de alerta cuando un colaborador alcanza su tercer intento fallido.

    Args:
        colaborador_data: Datos del colaborador (nombre, rfc, email, proveedor, etc.)
        attempts_info: Información de los intentos (total, aprobados, fallidos, registros)

    Returns:
        True si el email se envió exitosamente
    """
    try:
        # Definir asunto y destinatarios
        subject = f"⚠️ ALERTA: Tercer Intento Fallido - {colaborador_data.get('nombre_completo', 'Colaborador')}"
        to_emails = [
            "rodrigo.dalay@entersys.mx",
            "mario.dominguez@entersys.mx",
            "armando.cortes@entersys.mx",
            "giovvani.melchor@entersys.mx"
        ]

        # Generar tabla de historial de intentos
        historial_html = ""
        for i, registro in enumerate(attempts_info.get('registros', []), 1):
            estado_class = "approved" if registro.get('is_approved') else "failed"
            estado_text = "Aprobado" if registro.get('is_approved') else "No Aprobado"
            historial_html += f"""
            <tr class="{estado_class}">
                <td>{i}</td>
                <td>{registro.get('score', 'N/A')}</td>
                <td>{estado_text}</td>
            </tr>
            """

        # Generar tabla de resultados por seccion del intento actual
        secciones_html = ""
        for s in colaborador_data.get('section_results', []):
            sec_class = "approved" if s.get('approved') else "failed"
            sec_estado = "Aprobado" if s.get('approved') else "No Aprobado"
            secciones_html += f"""
                        <tr class="{sec_class}">
                            <td>{s.get('section_name', 'N/A')}</td>
                            <td>{s.get('correct_count', 0)}/{s.get('total_questions', 10)}</td>
                            <td>{s.get('score', 0)}%</td>
                            <td>{sec_estado}</td>
                        </tr>"""

        # Score promedio general
        promedio_general = colaborador_data.get('overall_score', 0)

        # Contenido HTML del email
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 700px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9fafb;
                }}
                .container {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    padding: 30px;
                    margin: 20px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 3px solid #DC2626;
                }}
                .alert-icon {{
                    font-size: 48px;
                    margin-bottom: 10px;
                }}
                h1 {{
                    color: #DC2626;
                    font-size: 24px;
                    margin: 0;
                }}
                .info-box {{
                    background-color: #FEF2F2;
                    border-left: 4px solid #DC2626;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .colaborador-info {{
                    background-color: #F3F4F6;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .colaborador-info h3 {{
                    margin-top: 0;
                    color: #374151;
                    border-bottom: 2px solid #D1D5DB;
                    padding-bottom: 10px;
                }}
                .colaborador-info p {{
                    margin: 8px 0;
                }}
                .colaborador-info strong {{
                    display: inline-block;
                    width: 150px;
                    color: #6B7280;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                th, td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #E5E7EB;
                }}
                th {{
                    background-color: #F3F4F6;
                    font-weight: 600;
                    color: #374151;
                }}
                tr.approved td {{
                    color: #059669;
                }}
                tr.failed td {{
                    color: #DC2626;
                }}
                .summary {{
                    display: flex;
                    justify-content: space-around;
                    margin: 20px 0;
                    text-align: center;
                }}
                .summary-item {{
                    padding: 15px 25px;
                    border-radius: 8px;
                }}
                .summary-item.total {{
                    background-color: #EFF6FF;
                    color: #1D4ED8;
                }}
                .summary-item.approved {{
                    background-color: #ECFDF5;
                    color: #059669;
                }}
                .summary-item.failed {{
                    background-color: #FEF2F2;
                    color: #DC2626;
                }}
                .summary-item .number {{
                    font-size: 32px;
                    font-weight: bold;
                }}
                .summary-item .label {{
                    font-size: 12px;
                    text-transform: uppercase;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    font-size: 12px;
                    color: #6b7280;
                }}
                .action-needed {{
                    background-color: #FEF3C7;
                    border-left: 4px solid #F59E0B;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="alert-icon">⚠️</div>
                    <h1>Alerta: Tercer Intento Fallido</h1>
                </div>

                <div class="info-box">
                    <p><strong>El siguiente colaborador ha alcanzado su tercer intento fallido</strong> en el examen de certificación de Seguridad Industrial.</p>
                </div>

                <div class="colaborador-info">
                    <h3>Datos del Colaborador</h3>
                    <p><strong>Nombre:</strong> {colaborador_data.get('nombre_completo', 'N/A')}</p>
                    <p><strong>RFC:</strong> {colaborador_data.get('rfc_colaborador', 'N/A')}</p>
                    <p><strong>Email:</strong> {colaborador_data.get('email', 'N/A')}</p>
                    <p><strong>Proveedor:</strong> {colaborador_data.get('proveedor', 'N/A')}</p>
                    <p><strong>Tipo de Servicio:</strong> {colaborador_data.get('tipo_servicio', 'N/A')}</p>
                    <p><strong>RFC Empresa:</strong> {colaborador_data.get('rfc_empresa', 'N/A')}</p>
                    <p><strong>NSS:</strong> {colaborador_data.get('nss', 'N/A')}</p>
                </div>

                <h3>Resumen de Intentos</h3>
                <div class="summary">
                    <div class="summary-item total">
                        <div class="number">{attempts_info.get('total', 0)}</div>
                        <div class="label">Total Intentos</div>
                    </div>
                    <div class="summary-item approved">
                        <div class="number">{attempts_info.get('aprobados', 0)}</div>
                        <div class="label">Aprobados</div>
                    </div>
                    <div class="summary-item failed">
                        <div class="number">{attempts_info.get('fallidos', 0)}</div>
                        <div class="label">Fallidos</div>
                    </div>
                </div>

                <h3>Resultado del Tercer Intento</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Sección</th>
                            <th>Correctas</th>
                            <th>Puntaje</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {secciones_html}
                    </tbody>
                </table>
                
                <p style="text-align: center; margin-top: 15px; font-size: 16px;">
                    <strong>Promedio General: {promedio_general:.1f}%</strong>
                </p>

                <div class="action-needed">
                    <p><strong>Acción Requerida:</strong></p>
                    <p>Se recomienda contactar al colaborador o su supervisor para determinar los siguientes pasos, ya que ha fallado el examen en múltiples ocasiones.</p>
                </div>

                <div class="footer">
                    <p>Este es un correo automático generado por el sistema de Onboarding de Seguridad.</p>
                    <p>&copy; {datetime.utcnow().year} FEMSA - Entersys. Todos los derechos reservados.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Enviar email via Resend
        result = send_email_via_resend(
            to_emails=to_emails,
            subject=subject,
            html_content=html_content
        )

        if result:
            logger.info(f"Third attempt alert email sent for RFC {colaborador_data.get('rfc_colaborador')}")
        return result

    except Exception as e:
        logger.error(f"Error sending third attempt alert email: {str(e)}")
        return False


async def update_smartsheet_certificate_background(
    sheet_id: int,
    row_id: int,
    cert_uuid: str,
    expiration_date: datetime,
    is_valid: bool,
    score: float
) -> None:
    """
    Tarea en background para actualizar Smartsheet con datos del certificado.

    Args:
        sheet_id: ID de la hoja
        row_id: ID de la fila
        cert_uuid: UUID del certificado
        expiration_date: Fecha de vencimiento
        is_valid: Si el certificado es válido
        score: Puntuación obtenida
    """
    try:
        service = get_onboarding_service_singleton()
        result = await asyncio.wait_for(
            service.update_row_with_certificate(
                sheet_id=sheet_id,
                row_id=row_id,
                cert_uuid=cert_uuid,
                expiration_date=expiration_date,
                is_valid=is_valid,
                score=score
            ),
            timeout=30.0  # 30 second timeout
        )
        if result:
            logger.info(f"Background task completed: updated Smartsheet for row {row_id}")
        else:
            logger.warning(f"Background task: Smartsheet update returned False for row {row_id}")
    except asyncio.TimeoutError:
        logger.error(f"Background task timeout: Smartsheet update for row {row_id} took too long")
    except Exception as e:
        logger.error(f"Background task failed for row {row_id}: {str(e)}")


async def generate_certificate_internal(
    row_id: int,
    full_name: str,
    email: str,
    score: float,
    background_tasks: BackgroundTasks,
    collaborator_data: dict = None,
    section_results: dict = None
) -> dict:
    """
    Función interna para generar certificado QR.
    Llamada desde submit-exam cuando el colaborador aprueba.

    Args:
        row_id: ID de la fila en Smartsheet
        full_name: Nombre completo del usuario
        email: Email del usuario
        score: Puntuación obtenida
        background_tasks: BackgroundTasks para envío de email
        collaborator_data: Datos adicionales del colaborador para el PDF (opcional)
        section_results: Resultados por sección para el PDF (opcional)

    Returns:
        Dict con success, cert_uuid, error
    """
    logger.info(
        f"generate_certificate_internal - "
        f"row_id={row_id}, email={email}, score={score}"
    )

    try:
        global _cert_generation_count
        _cert_generation_count += 1
        cert_start_time = time.time()

        # 1. Generar UUID seguro
        cert_uuid = str(uuid.uuid4())
        logger.info(f"Generated certificate UUID: {cert_uuid}")

        # 2. Calcular fecha de vencimiento
        expiration_date = datetime.utcnow() + timedelta(days=CERTIFICATE_VALIDITY_DAYS)

        # 3. Generar código QR
        qr_start = time.time()
        qr_image = await asyncio.to_thread(generate_certificate_qr, cert_uuid, API_BASE_URL)
        qr_duration = time.time() - qr_start
        logger.info(f"CERT_TRACKING: qr_generated uuid={cert_uuid} duration={qr_duration:.2f}s pid={os.getpid()}")

        # 4. Actualizar Smartsheet con UUID y fecha de vencimiento
        smartsheet_start = time.time()
        service = get_onboarding_service_singleton()
        try:
            await service.update_certificate_data(
                row_id=row_id,
                cert_uuid=cert_uuid,
                expiration_date=expiration_date
            )
            smartsheet_duration = time.time() - smartsheet_start
            logger.info(
                f"CERT_TRACKING: uuid_saved row_id={row_id} uuid={cert_uuid} "
                f"email={email} smartsheet_duration={smartsheet_duration:.2f}s"
            )
            cert_ref_code = None  # Smartsheet update OK
        except Exception as e:
            smartsheet_duration = time.time() - smartsheet_start
            logger.error(
                f"CRITICAL_UUID_NOT_SAVED: row_id={row_id} uuid={cert_uuid} "
                f"email={email} nombre={full_name} score={score} "
                f"expiration={expiration_date.strftime('%Y-%m-%d')} "
                f"smartsheet_duration={smartsheet_duration:.2f}s "
                f"error_type={type(e).__name__} error={str(e)} "
                f"pid={os.getpid()} traceback={traceback.format_exc()}"
            )
            cert_ref_code = "REF-C201"  # UUID no guardado en Smartsheet
            # Continuar de todas formas para enviar el email

        # 5. Enviar email con QR y PDF en background
        background_tasks.add_task(
            send_qr_email,
            email,
            full_name,
            qr_image,
            expiration_date,
            cert_uuid,
            True,  # is_valid (siempre True porque solo se llama cuando aprueba)
            score,
            collaborator_data,
            section_results
        )

        total_duration = time.time() - cert_start_time
        logger.info(
            f"CERT_TRACKING: complete uuid={cert_uuid} email={email} "
            f"total_duration={total_duration:.2f}s "
            f"active_certs={_cert_generation_count} pid={os.getpid()}"
        )
        _cert_generation_count -= 1

        result = {
            "success": True,
            "cert_uuid": cert_uuid,
            "expiration_date": expiration_date.strftime('%Y-%m-%d'),
            "email_scheduled": True
        }
        if cert_ref_code:
            result["ref_code"] = cert_ref_code
        return result

    except Exception as e:
        _cert_generation_count -= 1
        # Determinar ref_code específico según tipo de fallo
        # Si el error ocurrió en QR generation (paso 3), cert_uuid no existiría aún
        error_ref = "REF-C200" if "qr" in str(e).lower() else "REF-C202"
        logger.error(
            f"CERT_GENERATION_FAILED: row_id={row_id} email={email} "
            f"nombre={full_name} score={score} ref_code={error_ref} "
            f"error_type={type(e).__name__} error={str(e)} "
            f"pid={os.getpid()} traceback={traceback.format_exc()}"
        )
        return {
            "success": False,
            "error": str(e),
            "ref_code": error_ref
        }


@router.post(
    "/generate",
    response_model=OnboardingGenerateResponse,
    responses={
        400: {"model": OnboardingErrorResponse, "description": "Score too low or invalid data"},
        500: {"model": OnboardingErrorResponse, "description": "Internal server error"},
        502: {"model": OnboardingErrorResponse, "description": "Smartsheet API error"}
    },
    summary="Generate QR Code Certificate",
    description="""
    Generates a QR code certificate for a user who passed the onboarding evaluation.

    **Triggered by Smartsheet Bridge**

    This endpoint:
    1. Validates that the score is >= 80
    2. Generates a unique UUIDv4 certificate ID
    3. Creates a QR code with the validation URL
    4. Sends the QR code via email to the user
    5. Updates the Smartsheet row with certificate data

    **Required fields:**
    - `row_id`: Smartsheet row ID
    - `full_name`: User's full name
    - `email`: User's email address
    - `score`: Evaluation score (must be >= 80)
    """
)
async def generate_qr_certificate(
    request: OnboardingGenerateRequest,
    background_tasks: BackgroundTasks
):
    """
    Endpoint para generar un certificado QR de onboarding.
    """
    logger.info(
        f"POST /onboarding/generate - "
        f"row_id={request.row_id}, email={request.email}, score={request.score}"
    )

    # 1. Determinar si el certificado es válido basado en el score
    is_valid = request.score >= MINIMUM_SCORE
    if not is_valid:
        logger.info(
            f"Score below minimum for row {request.row_id}: {request.score} < {MINIMUM_SCORE}. "
            f"Certificate will be generated but marked as invalid."
        )

    try:
        # 2. Generar UUID seguro
        cert_uuid = str(uuid.uuid4())
        logger.info(f"Generated certificate UUID: {cert_uuid}")

        # 3. Calcular fecha de vencimiento
        expiration_date = datetime.utcnow() + timedelta(days=CERTIFICATE_VALIDITY_DAYS)

        # 4. Generar código QR
        qr_image = await asyncio.to_thread(generate_certificate_qr, cert_uuid, API_BASE_URL)

        # 5. Enviar email con QR adjunto
        email_sent = await asyncio.to_thread(
            send_qr_email,
            request.email,
            request.full_name,
            qr_image,
            expiration_date,
            cert_uuid,
            is_valid,
            request.score
        )

        if not email_sent:
            logger.error(f"Failed to send email to {request.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "success": False,
                    "error": "EMAIL_SEND_FAILED",
                    "message": f"Failed to send email to {request.email}"
                }
            )

        # 6. Actualizar Smartsheet en background (no bloquear la respuesta)
        # Obtener SHEET_ID del environment o usar el proporcionado
        sheet_id = getattr(settings, 'SHEET_ID', None)

        if not sheet_id:
            logger.warning("SHEET_ID not configured, skipping Smartsheet update")
            smartsheet_updated = False
        else:
            # Agregar tarea en background para actualizar Smartsheet
            background_tasks.add_task(
                update_smartsheet_certificate_background,
                int(sheet_id),
                request.row_id,
                cert_uuid,
                expiration_date,
                is_valid,
                request.score
            )
            smartsheet_updated = True  # Se actualizará en background
            logger.info(f"Smartsheet update scheduled in background for row {request.row_id}")

        # 7. Construir respuesta exitosa
        response_data = OnboardingGenerateData(
            cert_uuid=cert_uuid,
            expiration_date=expiration_date.strftime('%Y-%m-%d'),
            email_sent=email_sent,
            smartsheet_updated=smartsheet_updated
        )

        logger.info(
            f"Successfully generated certificate for row {request.row_id}: "
            f"uuid={cert_uuid}, email_sent={email_sent}, smartsheet_updated={smartsheet_updated}"
        )

        return OnboardingGenerateResponse(
            success=True,
            message="QR code generated and sent successfully",
            data=response_data
        )

    except HTTPException:
        raise
    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "success": False,
                "error": "SMARTSHEET_ERROR",
                "message": f"Smartsheet service error: {str(e)}"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error generating certificate: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}"
            }
        )


@router.get(
    "/validate",
    response_class=RedirectResponse,
    summary="Validate QR Code Certificate",
    description="""
    Validates a QR code certificate by its UUID.

    **Scanned by Security Personnel**

    This endpoint:
    1. Searches for the certificate in Smartsheet
    2. Checks if the certificate exists and is not expired
    3. If VALID: Updates 'Última Validación' in background, redirects to success page
    4. If INVALID: Redirects to access denied page

    **Response:**
    - HTTP 302 redirect to success or access denied page
    """,
    responses={
        302: {"description": "Redirect to validation result page"}
    }
)
async def validate_qr_certificate(
    background_tasks: BackgroundTasks,
    id: str = Query(..., description="Certificate UUID to validate", min_length=36, max_length=36)
):
    """
    Endpoint para validar un certificado QR de onboarding.
    """
    logger.info(f"GET /onboarding/validate - id={id}")

    # Validar formato UUID
    try:
        uuid.UUID(id)
    except ValueError:
        logger.warning(f"Invalid UUID format: {id}")
        return RedirectResponse(
            url=REDIRECT_INVALID,
            status_code=status.HTTP_302_FOUND
        )

    # Obtener SHEET_ID del environment
    sheet_id = getattr(settings, 'SHEET_ID', None)

    if not sheet_id:
        logger.error("SHEET_ID not configured")
        return RedirectResponse(
            url=REDIRECT_INVALID,
            status_code=status.HTTP_302_FOUND
        )

    try:
        service = get_onboarding_service()

        # Buscar certificado en Smartsheet
        certificate = await service.get_certificate_by_uuid(
            sheet_id=int(sheet_id),
            cert_uuid=id
        )

        if not certificate:
            logger.warning(f"Certificate not found: {id}")
            return RedirectResponse(
                url=REDIRECT_INVALID,
                status_code=status.HTTP_302_FOUND
            )

        # Obtener datos del certificado para mostrarlos en la página
        full_name = certificate.get('Nombre Colaborador', 'Usuario')
        expiration = certificate.get('Vencimiento', '')
        encoded_name = quote(str(full_name))
        encoded_expiration = quote(str(expiration))

        # Actualizar última validación en background (siempre que se escanee)
        row_id = certificate.get('row_id')
        if row_id:
            background_tasks.add_task(
                update_last_validation_background,
                int(sheet_id),
                row_id
            )

        # Verificar si el certificado es válido (score >= 80 y no expirado)
        if not service.is_certificate_valid(certificate):
            logger.warning(f"Certificate invalid or expired: {id}")
            redirect_url = f"{REDIRECT_INVALID}?nombre={encoded_name}&vencimiento={encoded_expiration}"
            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_302_FOUND
            )

        # Redirigir a página de certificación válida
        redirect_url = f"{REDIRECT_VALID}/{id}?nombre={encoded_name}&vencimiento={encoded_expiration}"
        logger.info(f"Certificate {id} validated successfully, redirecting to {redirect_url}")

        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_302_FOUND
        )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error during validation: {str(e)}")
        return RedirectResponse(
            url=REDIRECT_INVALID,
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Unexpected error validating certificate: {str(e)}")
        return RedirectResponse(
            url=REDIRECT_INVALID,
            status_code=status.HTTP_302_FOUND
        )


@router.get(
    "/certificate/{cert_uuid}",
    response_model=CertificateInfoResponse,
    summary="Get Certificate Information",
    description="""
    Returns certificate information for dynamic frontend display.

    **Called by Frontend Page**

    This endpoint:
    1. Searches for the certificate in Smartsheet by UUID
    2. Returns all certificate data as JSON
    3. Updates 'Última Validación' timestamp
    4. Determines status: approved, not_approved, or expired

    **Status Logic:**
    - approved: Score >= 80 AND not expired
    - not_approved: Score < 80
    - expired: Past expiration date
    - not_found: Certificate doesn't exist
    """
)
async def get_certificate_info(
    background_tasks: BackgroundTasks,
    cert_uuid: str
):
    """
    Endpoint para obtener información del certificado de forma dinámica.
    """
    logger.info(f"GET /onboarding/certificate/{cert_uuid}")

    # Validar formato UUID
    try:
        uuid.UUID(cert_uuid)
    except ValueError:
        logger.warning(f"Invalid UUID format: {cert_uuid}")
        return CertificateInfoResponse(
            success=False,
            status="not_found",
            nombre="",
            vencimiento="",
            score=0,
            is_expired=False,
            message="UUID inválido"
        )

    # Obtener SHEET_ID del environment
    sheet_id = getattr(settings, 'SHEET_ID', None)

    if not sheet_id:
        logger.error("SHEET_ID not configured")
        return CertificateInfoResponse(
            success=False,
            status="not_found",
            nombre="",
            vencimiento="",
            score=0,
            is_expired=False,
            message="Configuración del servidor incompleta"
        )

    try:
        service = get_onboarding_service()

        # Buscar certificado en Smartsheet
        certificate = await service.get_certificate_by_uuid(
            sheet_id=int(sheet_id),
            cert_uuid=cert_uuid
        )

        if not certificate:
            logger.warning(f"Certificate not found: {cert_uuid}")
            return CertificateInfoResponse(
                success=False,
                status="not_found",
                nombre="",
                vencimiento="",
                score=0,
                is_expired=False,
                message="Certificado no encontrado"
            )

        # Extraer datos del certificado
        full_name = certificate.get('Nombre Colaborador', 'Usuario')
        expiration_str = certificate.get('Vencimiento', '')
        url_imagen = certificate.get('url_imagen', None)  # URL de foto de credencial

        # Obtener el campo "Resultado Examen" (Aprobado/Reprobado) - este es el campo que determina si está aprobado
        resultado_examen = certificate.get('Resultado Examen', '')
        resultado_str = str(resultado_examen).strip().lower() if resultado_examen else ''
        is_approved_result = resultado_str == 'aprobado'

        logger.info(f"Certificate {cert_uuid} - Resultado Examen: '{resultado_examen}', is_approved: {is_approved_result}")

        # Score es solo para mostrar, no para validar
        score_value = certificate.get('Score', 0)
        try:
            score = float(str(score_value).replace('%', '').strip()) if score_value else 0
        except (ValueError, TypeError):
            score = 0

        # Parsear fecha de vencimiento y verificar si expiró
        is_expired = False
        formatted_expiration = expiration_str

        if expiration_str:
            expiration_date = None
            for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%d/%m/%y']:
                try:
                    expiration_date = datetime.strptime(str(expiration_str), date_format)
                    # Handle 2-digit years
                    if expiration_date.year < 100:
                        expiration_date = expiration_date.replace(year=expiration_date.year + 2000)
                    break
                except ValueError:
                    continue

            if expiration_date:
                is_expired = expiration_date.date() < datetime.utcnow().date()
                formatted_expiration = expiration_date.strftime('%d/%m/%Y')

        # Actualizar última validación en background
        row_id = certificate.get('row_id')
        if row_id:
            background_tasks.add_task(
                update_last_validation_background,
                int(sheet_id),
                row_id
            )
            logger.info(f"Scheduled last validation update for row {row_id}")

        # Determinar estado del certificado basado en "Resultado Examen" y fecha de vencimiento
        if is_expired:
            status_str = "expired"
            message = "Tu certificación de Seguridad Industrial ha expirado y NO está autorizado para ingresar a las instalaciones. Por favor contacta a tu supervisor para renovar tu certificación."
        elif not is_approved_result:
            status_str = "not_approved"
            message = "Tu certificación de Seguridad Industrial no pudo ser validada. La información proporcionada o los requisitos del curso no cumplen con los estándares mínimos de seguridad establecidos."
        else:
            status_str = "approved"
            message = "Tu certificación de Seguridad Industrial ha sido validada correctamente. Has cumplido con todos los requisitos del curso y tu información ha sido aprobada conforme a los estándares de seguridad establecidos."

        logger.info(f"Certificate {cert_uuid} info retrieved: status={status_str}, resultado_examen={resultado_examen}, expired={is_expired}")

        return CertificateInfoResponse(
            success=True,
            status=status_str,
            nombre=str(full_name),
            vencimiento=formatted_expiration,
            score=score,
            is_expired=is_expired,
            message=message,
            url_imagen=url_imagen
        )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error getting certificate info: {str(e)}")
        return CertificateInfoResponse(
            success=False,
            status="not_found",
            nombre="",
            vencimiento="",
            score=0,
            is_expired=False,
            message=f"Error de Smartsheet: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting certificate info: {str(e)}")
        return CertificateInfoResponse(
            success=False,
            status="not_found",
            nombre="",
            vencimiento="",
            score=0,
            is_expired=False,
            message=f"Error interno: {str(e)}"
        )


# ============================================
# Endpoint para el formulario público de examen
# ============================================


def resend_approved_certificate_email(
    email_to: str,
    full_name: str,
    cert_uuid: str,
    expiration_date_str: str,
    collaborator_data: dict = None,
    section_results: dict = None
) -> bool:
    """
    Reenvía el correo de certificado aprobado cuando el colaborador ya tiene certificación vigente.

    Args:
        email_to: Email del destinatario
        full_name: Nombre completo del usuario
        cert_uuid: UUID del certificado existente
        expiration_date_str: Fecha de vencimiento como string
        collaborator_data: Datos adicionales del colaborador para el PDF (opcional)
        section_results: Resultados por sección para el PDF (opcional)

    Returns:
        True si el email se envió exitosamente
    """
    try:
        # Generar QR para el certificado existente
        qr_image = generate_certificate_qr(cert_uuid, API_BASE_URL)

        # Parsear fecha de vencimiento
        expiration_date = None
        for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%d/%m/%y']:
            try:
                expiration_date = datetime.strptime(str(expiration_date_str), date_format)
                if expiration_date.year < 100:
                    expiration_date = expiration_date.replace(year=expiration_date.year + 2000)
                break
            except ValueError:
                continue

        if not expiration_date:
            expiration_date = datetime.utcnow() + timedelta(days=365)

        # Definir asunto
        subject = f"Recordatorio: Tu Certificación de Seguridad - {full_name}"

        # Contenido HTML del email recordatorio
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9fafb;
                }}
                .container {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    padding: 30px;
                    margin: 20px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 3px solid #FFC600;
                }}
                .logo {{
                    max-height: 80px;
                    margin-bottom: 15px;
                }}
                h1 {{
                    color: #1f2937;
                    font-size: 24px;
                    margin: 0;
                }}
                .certificate-info {{
                    background-color: #f0fdf4;
                    border-left: 4px solid #16a34a;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .reminder-box {{
                    background-color: #EFF6FF;
                    border-left: 4px solid #3B82F6;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .qr-section {{
                    text-align: center;
                    margin: 30px 0;
                    padding: 20px;
                    background-color: #f9fafb;
                    border-radius: 8px;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    font-size: 12px;
                    color: #6b7280;
                }}
                .highlight {{
                    color: #16a34a;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="https://entersys.mx/images/coca-cola-femsa-logo.png" alt="FEMSA" class="logo">
                    <h1>Tu Certificación de Seguridad</h1>
                </div>

                <p>Estimado/a <strong>{full_name}</strong>,</p>

                <div class="reminder-box">
                    <p><strong>Ya cuentas con una certificación de seguridad vigente.</strong></p>
                    <p>Este es un recordatorio de tu certificación activa. Te reenviamos tu código QR de acceso.</p>
                </div>

                <div class="certificate-info">
                    <p><strong>Detalles de tu Certificación:</strong></p>
                    <ul>
                        <li>Estado: <span class="highlight">VIGENTE</span></li>
                        <li>Válido hasta: <span class="highlight">{expiration_date.strftime('%d/%m/%Y')}</span></li>
                    </ul>
                </div>

                <div class="qr-section">
                    <p><strong>Tu código QR de acceso está adjunto a este correo.</strong></p>
                    <p>Preséntalo al personal de seguridad en cada ingreso a las instalaciones.</p>
                </div>

                <p><strong>Importante:</strong></p>
                <ul>
                    <li>No es necesario volver a realizar el examen mientras tu certificación esté vigente.</li>
                    <li>Recibirás un recordatorio antes de que expire tu certificación.</li>
                    <li>Guarda este correo o el código QR para acceder a las instalaciones.</li>
                </ul>

                <div class="footer">
                    <p>Este es un correo automático, por favor no respondas a este mensaje.</p>
                    <p>&copy; {datetime.utcnow().year} FEMSA - Entersys. Todos los derechos reservados.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Preparar adjuntos
        attachments = []

        # Adjunto QR
        qr_attachment = {
            "filename": f"certificado_qr_{cert_uuid[:8]}.png",
            "content": base64.b64encode(qr_image).decode('utf-8')
        }
        attachments.append(qr_attachment)

        # Generar y adjuntar PDF si se tienen los datos
        if collaborator_data or section_results:
            try:
                # Preparar datos para el PDF
                pdf_data = collaborator_data.copy() if collaborator_data else {}
                pdf_data.update({
                    "full_name": full_name,
                    "email": email_to,
                    "cert_uuid": cert_uuid,
                    "vencimiento": expiration_date.strftime('%d/%m/%Y'),
                    "fecha_emision": datetime.utcnow().strftime('%d/%m/%Y'),
                    "is_approved": True,
                })
                # Map url_imagen -> foto_url for PDF generation
                if "foto_url" not in pdf_data and "url_imagen" in pdf_data:
                    pdf_data["foto_url"] = pdf_data["url_imagen"]

                # Generar PDF (will raise ValueError if photo is not available)
                pdf_bytes = generate_certificate_pdf(
                    collaborator_data=pdf_data,
                    section_results=section_results,
                    qr_image_bytes=qr_image
                )

                pdf_attachment = {
                    "filename": f"certificado_{cert_uuid[:8]}.pdf",
                    "content": base64.b64encode(pdf_bytes).decode('utf-8')
                }
                attachments.append(pdf_attachment)
                logger.info(f"PDF attachment generated for resend to {email_to}")
            except Exception as e:
                logger.warning(f"Could not generate PDF attachment for resend: {e}")

        # Enviar email via SMTP
        result = send_email_via_resend(
            to_emails=[email_to],
            subject=subject,
            html_content=html_content,
            attachments=attachments
        )

        if result:
            logger.info(f"Certificate reminder email sent successfully to {email_to}")
        return result

    except Exception as e:
        logger.error(f"Error sending certificate reminder email to {email_to}: {str(e)}")
        return False


@router.get(
    "/lookup-rfc",
    summary="Buscar RFC existente por NSS y correo electrónico",
    description="Busca en Smartsheet si ya existe un registro con el NSS y correo proporcionados. Retorna el RFC completo si existe.",
)
async def lookup_rfc_by_nss_email(nss: str = Query(...), email: str = Query(...)):
    """Busca un RFC existente por NSS + email en Smartsheet."""
    logger.info(f"GET /onboarding/lookup-rfc - nss={nss}, email={email}")

    try:
        service = get_onboarding_service_singleton()
        result = await service.lookup_by_nss_email(nss=nss, email=email)

        if result:
            return {
                "found": True,
                "rfc": result["rfc"],
                "full_name": result.get("full_name"),
            }

        return {"found": False, "rfc": None, "full_name": None}

    except Exception as e:
        logger.error(f"Error en lookup-rfc: {str(e)}")
        # Si Smartsheet falla, retornar no encontrado en vez de error
        return {"found": False, "rfc": None, "full_name": None}


@router.get(
    "/check-exam-status/{rfc}",
    response_model=ExamStatusResponse,
    summary="Verificar estatus del examen por RFC",
    description="""
    Verifica si un colaborador puede realizar el examen de seguridad.

    **Criterios para poder hacer el examen:**
    - Estatus Examen = 1 en la hoja de Registros
    - No estar ya aprobado con certificación vigente
    - Tener menos de 3 intentos

    **Comportamiento especial:**
    - Si ya está APROBADO y vigente: NO puede hacer examen, se reenvía su certificado por correo
    - Si ya está APROBADO pero expiró (pasó 1 año): SI puede hacer examen para renovar

    **Retorna:**
    - can_take_exam: Si puede hacer el examen
    - attempts_used: Intentos utilizados
    - attempts_remaining: Intentos restantes
    - is_approved: Si ya está aprobado
    - is_expired: Si el certificado aprobado ya expiró
    - certificate_resent: Si se reenvió el certificado por correo
    """
)
async def check_exam_status(rfc: str, background_tasks: BackgroundTasks):
    """
    Verifica el estatus del examen para un RFC.
    Si el colaborador ya tiene certificación vigente, reenvía el certificado por correo.
    """
    logger.info(f"GET /onboarding/check-exam-status/{rfc}")

    if not rfc or len(rfc) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFC inválido. Debe tener al menos 10 caracteres."
        )

    try:
        service = get_onboarding_service_singleton()
        status_info = await service.check_exam_status(rfc)

        certificate_resent = False

        # Construir mensaje descriptivo
        if status_info["is_approved"] and not status_info.get("is_expired", False):
            # Ya está aprobado y vigente - reenviar certificado
            message = "Ya tienes una certificación de seguridad vigente. Te hemos reenviado tu certificado por correo."

            # Reenviar certificado si tiene los datos necesarios
            cert_uuid = status_info.get("cert_uuid")
            email = status_info.get("email")
            full_name = status_info.get("full_name")
            expiration_date = status_info.get("expiration_date")
            row_id = status_info.get("row_id")

            # Si aprobó pero no tiene UUID, generar uno y guardarlo
            if not cert_uuid and row_id:
                logger.warning(f"RFC {rfc}: aprobado sin UUID, generando uno nuevo...")
                cert_uuid = str(uuid.uuid4())
                exp_date = datetime.utcnow() + timedelta(days=CERTIFICATE_VALIDITY_DAYS)
                try:
                    await service.update_certificate_data(
                        row_id=row_id,
                        cert_uuid=cert_uuid,
                        expiration_date=exp_date
                    )
                    expiration_date = exp_date.strftime('%Y-%m-%d')
                    logger.info(f"UUID generado y guardado para RFC {rfc}: {cert_uuid}")
                except Exception as e:
                    logger.error(f"Error guardando UUID generado para RFC {rfc}: {e}")
                    cert_uuid = None

            if cert_uuid and email and full_name:
                # Reenviar en background para no bloquear la respuesta
                background_tasks.add_task(
                    resend_approved_certificate_email,
                    email,
                    full_name,
                    cert_uuid,
                    expiration_date or ""
                )
                certificate_resent = True
                logger.info(f"Certificate resend scheduled for RFC {rfc} to {email}")
            else:
                logger.warning(f"Cannot resend certificate for RFC {rfc}: missing data (uuid={cert_uuid}, email={email})")
                message = "Ya tienes una certificación de seguridad vigente. No es necesario volver a realizar el examen."

        elif status_info["is_approved"] and status_info.get("is_expired", False):
            # Aprobado pero expiró - puede renovar
            message = "Tu certificación anterior expiró. Puedes realizar el examen nuevamente para renovarla."

        elif not status_info["can_take_exam"]:
            if status_info["attempts_used"] >= MAX_ATTEMPTS:
                message = f"Has agotado tus {MAX_ATTEMPTS} intentos. Contacta al administrador."
            else:
                message = "No tienes autorización para realizar el examen. Verifica tu estatus."
        else:
            remaining = status_info["attempts_remaining"]
            message = f"Puedes realizar el examen. Te quedan {remaining} intento(s)."

        return ExamStatusResponse(
            can_take_exam=status_info["can_take_exam"],
            rfc=rfc.upper(),
            attempts_used=status_info["attempts_used"],
            attempts_remaining=status_info["attempts_remaining"],
            is_approved=status_info["is_approved"],
            is_expired=status_info.get("is_expired", False),
            last_attempt_date=status_info["last_attempt_date"],
            expiration_date=status_info.get("expiration_date"),
            message=message,
            section_results=status_info["section_results"],
            certificate_resent=certificate_resent
        )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error checking exam status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al verificar estatus: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error checking exam status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.get(
    "/exam-questions",
    response_model=ExamConfigResponse,
    summary="Obtener preguntas del examen (dinámico)",
    description="""
    Retorna las categorías activas y un subconjunto aleatorio de preguntas
    por categoría. Las opciones de cada pregunta también se aleatorizan.
    **No incluye la respuesta correcta.**
    """,
)
def get_exam_questions(db: Session = Depends(get_db)):
    """Endpoint público que entrega preguntas aleatorias sin respuesta correcta."""
    # 1. Categorías activas ordenadas (eager load questions to avoid N+1)
    categories = (
        db.query(ExamCategory)
        .options(selectinload(ExamCategory.questions))
        .filter(ExamCategory.is_active.is_(True))
        .order_by(ExamCategory.display_order)
        .all()
    )
    if not categories:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No hay categorías de examen configuradas.",
        )

    all_questions: list[ExamQuestionOut] = []
    for cat in categories:
        pool = [q for q in cat.questions if q.is_active]
        # Seleccionar questions_to_show aleatorias (o todas si el pool es menor)
        sample_size = min(cat.questions_to_show, len(pool))
        selected = random.sample(pool, sample_size)

        for q in selected:
            shuffled_options = list(q.options)
            random.shuffle(shuffled_options)
            all_questions.append(
                ExamQuestionOut(
                    id=q.id,
                    category_id=q.category_id,
                    question_text=q.question_text,
                    options=shuffled_options,
                )
            )

    return ExamConfigResponse(
        categories=[ExamCategoryOut.model_validate(c) for c in categories],
        questions=all_questions,
    )


def calculate_section_results(answers: list, db: Session) -> tuple:
    """
    Calcula los resultados por sección del examen, validando contra la BD.

    Args:
        answers: Lista de respuestas con question_id y answer
        db: Sesión de base de datos

    Returns:
        Tuple de (section_results: list[SectionResult], section_scores: dict,
                  is_approved: bool, answers_results: list[dict])
    """
    # Obtener los IDs de preguntas del request
    question_ids = [a.question_id for a in answers]

    # Cargar preguntas de la BD en una sola query
    questions_db = (
        db.query(ExamQuestion)
        .filter(ExamQuestion.id.in_(question_ids))
        .all()
    )
    question_map = {q.id: q for q in questions_db}

    # Cargar categorías activas para construir secciones dinámicamente
    categories = (
        db.query(ExamCategory)
        .filter(ExamCategory.is_active.is_(True))
        .order_by(ExamCategory.display_order)
        .all()
    )

    section_results = []
    section_scores = {}
    all_sections_approved = True
    answers_results = []

    for idx, cat in enumerate(categories, start=1):
        correct_in_section = 0
        total_in_section = 0

        for answer in answers:
            q = question_map.get(answer.question_id)
            if q is None:
                continue
            if q.category_id != cat.id:
                continue

            total_in_section += 1
            is_correct = answer.answer == q.correct_answer
            if is_correct:
                correct_in_section += 1
            answers_results.append({
                "question_id": answer.question_id,
                "is_correct": is_correct,
            })

        # Evitar división por cero
        if total_in_section == 0:
            section_score = 0.0
        else:
            section_score = (correct_in_section / total_in_section) * 100

        section_approved = section_score >= cat.min_score_percent

        if not section_approved:
            all_sections_approved = False

        section_results.append(SectionResult(
            section_name=cat.name,
            section_number=idx,
            correct_count=correct_in_section,
            total_questions=total_in_section,
            score=section_score,
            approved=section_approved,
        ))

        section_scores[f"Seccion{idx}"] = section_score

    return section_results, section_scores, all_sections_approved, answers_results


@router.post(
    "/submit-exam",
    response_model=ExamSubmitResponse,
    summary="Enviar examen de seguridad (3 secciones)",
    description="""
    Endpoint para enviar el examen de certificación de seguridad.

    **Estructura del examen (30 preguntas, 3 secciones):**
    - Sección 1 (Seguridad): Preguntas 1-10
    - Sección 2 (Inocuidad): Preguntas 11-20
    - Sección 3 (Ambiental): Preguntas 21-30

    **Criterios de aprobación:**
    - Cada sección debe tener mínimo 80% (8/10 correctas)
    - Si falla cualquier sección = Reprobado
    - Máximo 3 intentos por RFC

    **Flujo:**
    1. Verifica que el RFC puede hacer el examen (Estatus Examen = 1)
    2. Calcula score por sección
    3. Guarda resultados en hoja de Registros
    4. Guarda respuestas (Correcto/Incorrecto) en hoja de Respuestas (Bitácora)
    5. Si es el 3er intento fallido, envía alerta y bloquea
    """
)
async def submit_exam(request: ExamSubmitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Endpoint para enviar el examen de seguridad con 3 secciones.
    """
    global _exam_concurrent_count, _exam_concurrent_peak

    # Tracking de concurrencia
    with _exam_concurrent_lock:
        _exam_concurrent_count += 1
        if _exam_concurrent_count > _exam_concurrent_peak:
            _exam_concurrent_peak = _exam_concurrent_count
        current_concurrent = _exam_concurrent_count

    exam_start_time = time.time()
    process_mem_start = os.popen(f'ps -o rss= -p {os.getpid()}').read().strip()

    logger.info(
        f"EXAM_START: rfc={request.rfc_colaborador} email={request.email} "
        f"concurrent_users={current_concurrent} peak={_exam_concurrent_peak} "
        f"pid={os.getpid()} mem_rss={process_mem_start}KB"
    )

    try:
        service = get_onboarding_service_singleton()

        # 1. Verificar estatus del examen antes de procesar
        status_info = await service.check_exam_status(request.rfc_colaborador)

        if not status_info["can_take_exam"]:
            # Construir mensaje de error apropiado y asignar ref_code
            if status_info["is_approved"]:
                msg = "Ya aprobaste el examen. No necesitas volver a realizarlo."
                ref_code = "REF-E100"
            elif status_info["attempts_used"] >= MAX_ATTEMPTS:
                msg = f"Has agotado tus {MAX_ATTEMPTS} intentos. Contacta al administrador."
                ref_code = "REF-E101"
            else:
                msg = "No tienes autorización para realizar el examen (Estatus Examen != 1)."
                ref_code = "REF-E102"

            return ExamSubmitResponse(
                success=False,
                approved=False,
                sections=[],
                overall_score=0,
                message=msg,
                attempts_used=status_info["attempts_used"],
                attempts_remaining=status_info["attempts_remaining"],
                can_retry=False,
                ref_code=ref_code
            )

        # 2. Calcular resultados por sección (server-side validation contra BD)
        section_results, section_scores, is_approved, answers_results = calculate_section_results(
            request.answers, db
        )

        # Calcular score promedio general
        num_sections = len(section_results)
        overall_score = sum(s.score for s in section_results) / num_sections if num_sections else 0

        logger.info(
            f"RFC {request.rfc_colaborador}: "
            + ", ".join(f"{k}={v}%" for k, v in section_scores.items())
            + f", Aprobado={is_approved}"
        )

        # 4. Guardar resultados en Smartsheet
        # Preparar datos del colaborador para guardar en Smartsheet
        colaborador_data = {
            "nombre_completo": request.nombre_completo,
            "rfc_empresa": request.rfc_empresa,
            "nss": request.nss,
            "tipo_servicio": request.tipo_servicio,
            "proveedor": request.proveedor,
            "email": request.email,
            "url_imagen": request.url_imagen  # URL de la foto de credencial
        }

        save_result = await service.save_exam_results(
            rfc=request.rfc_colaborador,
            section_scores=section_scores,
            is_approved=is_approved,
            answers_results=answers_results,
            existing_row_id=status_info.get("row_id"),
            current_attempts=status_info["attempts_used"],
            colaborador_data=colaborador_data
        )

        new_attempts = save_result["new_attempts"]
        attempts_remaining = max(0, MAX_ATTEMPTS - new_attempts)
        can_retry = not is_approved and attempts_remaining > 0

        # 5. Si APROBÓ: Llamar a la lógica de /generate para crear certificado
        cert_uuid = None
        cert_ref_code = None
        if is_approved:
            row_id = save_result.get("registros_row_id") or status_info.get("row_id")

            if row_id:
                logger.info(f"Examen APROBADO para RFC {request.rfc_colaborador} - Generando certificado...")

                # Llamar a la lógica de generación de certificado
                # Preparar section_results como dict para el PDF
                section_results_for_pdf = {
                    sr.section_name: sr.score
                    for sr in section_results
                }
                try:
                    generate_result = await generate_certificate_internal(
                        row_id=row_id,
                        full_name=request.nombre_completo,
                        email=request.email,
                        score=overall_score,
                        background_tasks=background_tasks,
                        collaborator_data=colaborador_data,
                        section_results=section_results_for_pdf
                    )

                    if generate_result.get("success"):
                        cert_uuid = generate_result.get("cert_uuid")
                        logger.info(f"Certificado generado exitosamente: UUID={cert_uuid}")
                    else:
                        logger.error(f"Error generando certificado: {generate_result.get('error')}")

                    # Capturar ref_code del certificado (None si todo OK)
                    cert_ref_code = generate_result.get("ref_code")

                except Exception as e:
                    logger.error(f"Error llamando a generate_certificate_internal: {str(e)}")
                    cert_ref_code = "REF-C202"
            else:
                logger.error(
                    f"CRITICAL_NO_ROW_ID: rfc={request.rfc_colaborador} "
                    f"email={request.email} nombre={request.nombre_completo} "
                    f"score={overall_score} "
                    f"save_result={save_result} "
                    f"status_info_row_id={status_info.get('row_id') if status_info else 'N/A'}"
                )
                cert_ref_code = "REF-C203"

        # 6. Verificar si es el tercer intento fallido
        if not is_approved and new_attempts >= MAX_ATTEMPTS:
            logger.warning(
                f"⚠️ TERCER INTENTO FALLIDO detectado para RFC {request.rfc_colaborador}"
            )

            # Preparar datos para alerta
            colaborador_data = {
                "nombre_completo": request.nombre_completo,
                "rfc_colaborador": request.rfc_colaborador,
                "email": request.email,
                "proveedor": request.proveedor,
                "tipo_servicio": request.tipo_servicio or "",
                "rfc_empresa": request.rfc_empresa or "",
                "nss": request.nss or "",
                "section_scores": section_scores,
                "section_results": [s.model_dump() for s in section_results],  # Para mostrar en email
                "overall_score": overall_score
            }

            attempts_info = {
                "total": new_attempts,
                "fallidos": new_attempts,  # Todos fueron fallidos si llegamos al 3er intento
                "registros": []
            }

            # Enviar alerta en background
            background_tasks.add_task(
                send_third_attempt_alert_email,
                colaborador_data,
                attempts_info
            )
            logger.info(f"Alerta de tercer intento programada para RFC {request.rfc_colaborador}")

        # 7. Construir mensaje de respuesta
        if is_approved:
            message = "¡Felicidades! Has aprobado el examen. Recibirás tu certificación por correo."
        else:
            # Identificar secciones reprobadas
            failed_sections = [s.section_name for s in section_results if not s.approved]
            if can_retry:
                message = f"No aprobaste. Sección(es) reprobada(s): {', '.join(failed_sections)}. Te quedan {attempts_remaining} intento(s)."
            else:
                message = f"No aprobaste y has agotado tus {MAX_ATTEMPTS} intentos. Contacta al administrador."

        return ExamSubmitResponse(
            success=True,
            approved=is_approved,
            sections=section_results,
            overall_score=round(overall_score, 2),
            message=message,
            attempts_used=new_attempts,
            attempts_remaining=attempts_remaining,
            can_retry=can_retry,
            ref_code=cert_ref_code
        )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error in submit-exam: {str(e)}")
        return ExamSubmitResponse(
            success=False,
            approved=False,
            sections=[],
            overall_score=0,
            message=f"Error al guardar en el sistema: {str(e)}",
            attempts_used=0,
            attempts_remaining=0,
            can_retry=False,
            ref_code="REF-E103"
        )
    except Exception as e:
        logger.error(f"Unexpected error in submit-exam: {str(e)}")
        return ExamSubmitResponse(
            success=False,
            approved=False,
            sections=[],
            overall_score=0,
            message=f"Error interno: {str(e)}",
            attempts_used=0,
            attempts_remaining=0,
            can_retry=False,
            ref_code="REF-E104"
        )
    finally:
        with _exam_concurrent_lock:
            _exam_concurrent_count -= 1

        exam_duration = time.time() - exam_start_time
        process_mem_end = os.popen(f'ps -o rss= -p {os.getpid()}').read().strip()

        logger.info(
            f"EXAM_END: rfc={request.rfc_colaborador} "
            f"duration={exam_duration:.1f}s "
            f"concurrent_users={_exam_concurrent_count} "
            f"mem_start={process_mem_start}KB mem_end={process_mem_end}KB "
            f"pid={os.getpid()}"
        )


@router.post(
    "/upload-photo",
    summary="Subir foto de credencial a GCS",
    description="Sube una foto de credencial a Google Cloud Storage y retorna la URL pública"
)
async def upload_photo(
    file: UploadFile = File(...),
    rfc: str = Form(...)
):
    """
    Sube una foto de credencial a Google Cloud Storage.

    - **file**: Imagen JPG/PNG (máx 5MB)
    - **rfc**: RFC del colaborador (usado para nombrar el archivo)

    Retorna la URL pública de la imagen.
    """
    logger.info(f"POST /onboarding/upload-photo - Subiendo foto para RFC: {rfc}")

    # Validar tipo de archivo
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no permitido. Solo se aceptan JPG y PNG."
        )

    # Validar tamaño (5MB máximo)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo excede el tamaño máximo de 5MB."
        )

    try:
        # Generar nombre único para el archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"credentials/{rfc.upper()}_{timestamp}.{extension}"

        # Inicializar cliente de GCS
        storage_client = storage.Client(project=settings.GCS_PROJECT_ID)
        bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(filename)

        # Subir archivo
        blob.upload_from_string(
            contents,
            content_type=file.content_type
        )

        # El bucket ya tiene acceso público configurado via IAM (uniform bucket-level access)
        # No necesitamos blob.make_public() - construimos la URL directamente
        public_url = f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{filename}"

        logger.info(f"Foto subida exitosamente: {public_url}")

        return {
            "success": True,
            "url": public_url,
            "filename": filename
        }

    except Exception as e:
        logger.error(f"Error subiendo foto a GCS: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir la foto: {str(e)}"
        )


@router.get(
    "/registros",
    summary="Listar todos los registros de la hoja de Smartsheet",
    description="Obtiene todos los registros de la hoja de Registros_OnBoarding"
)
async def list_all_registros():
    """
    Lista todos los registros de la hoja de Smartsheet.
    """
    logger.info("GET /onboarding/registros - Listando todos los registros")

    try:
        service = get_onboarding_service_singleton()
        registros = await service.get_all_registros()

        return {
            "success": True,
            "total": len(registros),
            "registros": registros
        }

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error listing registros: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar Smartsheet: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error listing registros: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


def mask_email(email: str) -> str:
    """Censura un email para mostrar solo los primeros 3 caracteres y el dominio."""
    if not email or '@' not in email:
        return "***"
    local, domain = email.split('@', 1)
    if len(local) <= 3:
        masked = local[0] + '***'
    else:
        masked = local[:3] + '***'
    return f"{masked}@{domain}"


@router.post(
    "/resend-certificate",
    response_model=ResendCertificateResponse,
    summary="Reenviar certificado por RFC y NSS (soporte)",
    description="""
    Endpoint para que soporte reenvíe el certificado a un colaborador.

    **Flujo:**
    1. Recibe RFC + NSS
    2. Busca al colaborador en Smartsheet por RFC
    3. Valida que el NSS coincida (doble verificación de identidad)
    4. Lee el email actual de Smartsheet (el corregido por soporte)
    5. Si resultado = Aprobado → reenvía email con QR
    6. Si resultado = Reprobado → reenvía email de reprobado
    7. Retorna confirmación con email censurado
    """
)
async def resend_certificate(request: ResendCertificateRequest):
    """
    Reenvía el certificado de un colaborador buscando por RFC y validando NSS.
    """
    logger.info(f"POST /onboarding/resend-certificate - RFC={request.rfc}")

    try:
        service = get_onboarding_service_singleton()

        # Buscar colaborador por RFC y validar NSS
        collaborator = await service.get_collaborator_by_rfc_and_nss(request.rfc, request.nss)

        if not collaborator:
            return ResendCertificateResponse(
                success=False,
                message="No se encontró un colaborador con ese RFC y NSS. Verifica los datos."
            )

        email = collaborator.get("email")
        full_name = collaborator.get("full_name", "Colaborador")
        cert_uuid = collaborator.get("cert_uuid")
        vencimiento = collaborator.get("vencimiento", "")
        resultado = str(collaborator.get("resultado", "")).strip()
        is_approved = collaborator.get("is_approved", False)

        if not email:
            return ResendCertificateResponse(
                success=False,
                message="El colaborador no tiene un correo electrónico registrado."
            )

        email_masked = mask_email(email)

        # Si aprobó pero no tiene UUID, generar uno y guardarlo
        if is_approved and not cert_uuid:
            logger.warning(f"RFC {request.rfc}: aprobado sin UUID en resend-certificate, generando uno nuevo...")
            cert_uuid = str(uuid.uuid4())
            exp_date = datetime.utcnow() + timedelta(days=CERTIFICATE_VALIDITY_DAYS)
            row_id = collaborator.get("row_id")
            if row_id:
                try:
                    await service.update_certificate_data(
                        row_id=row_id,
                        cert_uuid=cert_uuid,
                        expiration_date=exp_date
                    )
                    vencimiento = exp_date.strftime('%Y-%m-%d')
                    logger.info(f"UUID generado y guardado para RFC {request.rfc}: {cert_uuid}")
                except Exception as e:
                    logger.error(f"Error guardando UUID generado para RFC {request.rfc}: {e}")
                    cert_uuid = None

        if is_approved and cert_uuid:
            # Reenviar certificado aprobado con QR
            sent = await asyncio.to_thread(
                resend_approved_certificate_email,
                email,
                full_name,
                cert_uuid,
                str(vencimiento) if vencimiento else ""
            )

            if sent:
                return ResendCertificateResponse(
                    success=True,
                    message=f"Certificado aprobado reenviado exitosamente a {email_masked}",
                    email_masked=email_masked,
                    resultado="Aprobado"
                )
            else:
                return ResendCertificateResponse(
                    success=False,
                    message="Error al enviar el correo. Intenta de nuevo."
                )

        else:
            # Reenviar email de reprobado
            # Generar QR de referencia
            qr_image = await asyncio.to_thread(generate_certificate_qr, cert_uuid or str(uuid.uuid4()), API_BASE_URL)

            # Calcular score promedio de secciones
            s1 = float(str(collaborator.get("seccion1", 0) or 0).replace('%', '').strip() or 0)
            s2 = float(str(collaborator.get("seccion2", 0) or 0).replace('%', '').strip() or 0)
            s3 = float(str(collaborator.get("seccion3", 0) or 0).replace('%', '').strip() or 0)
            overall_score = (s1 + s2 + s3) / 3 if (s1 or s2 or s3) else 0

            # Parsear fecha de vencimiento
            exp_date = datetime.utcnow() + timedelta(days=365)
            if vencimiento:
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        exp_date = datetime.strptime(str(vencimiento), fmt)
                        break
                    except ValueError:
                        continue

            sent = await asyncio.to_thread(
                send_qr_email,
                email,
                full_name,
                qr_image,
                exp_date,
                cert_uuid or "N/A",
                False,
                overall_score
            )

            if sent:
                return ResendCertificateResponse(
                    success=True,
                    message=f"Resultado de examen reenviado exitosamente a {email_masked}",
                    email_masked=email_masked,
                    resultado="Reprobado"
                )
            else:
                return ResendCertificateResponse(
                    success=False,
                    message="Error al enviar el correo. Intenta de nuevo."
                )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error in resend-certificate: {str(e)}")
        return ResendCertificateResponse(
            success=False,
            message=f"Error al consultar el sistema: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in resend-certificate: {str(e)}")
        return ResendCertificateResponse(
            success=False,
            message="Error interno del servidor"
        )


@router.get(
    "/download-certificate/{rfc}",
    summary="Descargar certificado PDF por RFC",
    description="""
    Genera y descarga un certificado PDF para un colaborador aprobado.

    **Flujo:**
    1. Obtiene datos del colaborador por RFC
    2. Obtiene scores por sección
    3. Genera QR del certificado
    4. Genera PDF con datos, resultados y QR
    5. Retorna como descarga directa
    """
)
async def download_certificate_pdf(rfc: str):
    """
    Genera y descarga un certificado PDF para un RFC.
    """
    logger.info(f"GET /onboarding/download-certificate/{rfc}")

    if not rfc or len(rfc) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFC inválido"
        )

    try:
        service = get_onboarding_service_singleton()

        # Obtener datos del colaborador (incluye section_results)
        credential_data = await service.get_credential_data_by_rfc(rfc)
        if not credential_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró registro para este RFC"
            )

        section_results = credential_data.get("section_results")

        # Generar QR si tiene cert_uuid
        qr_bytes = None
        cert_uuid = credential_data.get("cert_uuid")
        if cert_uuid:
            try:
                qr_bytes = await asyncio.to_thread(generate_certificate_qr, cert_uuid, API_BASE_URL)
            except Exception as e:
                logger.warning(f"Could not generate QR for PDF: {e}")

        # Preparar datos del colaborador para el PDF
        pdf_data = {
            "full_name": credential_data.get("full_name", ""),
            "rfc": rfc.upper(),
            "proveedor": credential_data.get("proveedor"),
            "tipo_servicio": credential_data.get("tipo_servicio"),
            "nss": credential_data.get("nss"),
            "rfc_empresa": credential_data.get("rfc_empresa"),
            "email": credential_data.get("email"),
            "cert_uuid": cert_uuid,
            "vencimiento": credential_data.get("vencimiento"),
            "fecha_emision": credential_data.get("fecha_emision"),
            "is_approved": credential_data.get("is_approved", False),
            "foto_url": credential_data.get("url_imagen", ""),
        }

        # Generar PDF
        pdf_bytes = await asyncio.to_thread(
            generate_certificate_pdf,
            collaborator_data=pdf_data,
            section_results=section_results,
            qr_image_bytes=qr_bytes
        )

        # Retornar como descarga directa
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="certificado_{rfc.upper()}.pdf"'
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Cannot generate PDF for RFC {rfc}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede generar el certificado PDF porque el colaborador no tiene foto registrada."
        )
    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error downloading certificate: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar Smartsheet: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error downloading certificate: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


# ============================================
# Helper: Consulta hoja 6.3 Biblioteca de Personal Terceros
# ============================================
SHEET_BIBLIOTECA_TERCEROS_ID = 4439674366939012

async def _lookup_high_risk_by_nss(nss: str) -> Optional[dict]:
    """
    Busca un colaborador por NSS en la hoja 6.3 Biblioteca de Personal Terceros.
    Retorna dict con datos de alto riesgo si existe, None si no se encuentra.
    """
    try:
        from app.services.smartsheet_service import get_smartsheet_service_singleton
        smartsheet_svc = get_smartsheet_service_singleton()

        result = await smartsheet_svc.get_sheet_rows(
            sheet_id=SHEET_BIBLIOTECA_TERCEROS_ID,
            limit=5,
            offset=0,
            fields="No IMSS,Nombre del Colaborador,Empresa Contratista,RFC Empresa,RFC Colaborador,Edad,Funciones,Cargo,Validación de cargo,Trabajos permitidos,Proyectos ejecutados,Proyectos en Ejecución,Proyectos Programados,Estatus de Aprobación",
            include_attachments=False,
            query_string=f"No IMSS:equals:{nss}",
        )

        # Verificar si se encontraron resultados
        from app.models.smartsheet import SmartsheetRowsResponse
        if isinstance(result, SmartsheetRowsResponse) and result.data.returned_rows > 0:
            row = result.data.rows[0]
            cells = row.cells
            return {
                "nss": cells.get("No IMSS"),
                "nombre": cells.get("Nombre del Colaborador"),
                "empresa_contratista": cells.get("Empresa Contratista"),
                "rfc_empresa": cells.get("RFC Empresa"),
                "rfc_colaborador": cells.get("RFC Colaborador"),
                "edad": cells.get("Edad"),
                "funciones": cells.get("Funciones"),
                "cargo": cells.get("Cargo"),
                "validacion_cargo": cells.get("Validación de cargo"),
                "trabajos_permitidos": cells.get("Trabajos permitidos"),
                "proyectos_ejecutados": cells.get("Proyectos ejecutados"),
                "proyectos_en_ejecucion": cells.get("Proyectos en Ejecución"),
                "proyectos_programados": cells.get("Proyectos Programados"),
                "estatus_aprobacion": cells.get("Estatus de Aprobación"),
            }

        return None

    except Exception as e:
        logger.error(f"Error looking up high risk data for NSS {nss}: {e}")
        return None


@router.get(
    "/credential/{rfc}",
    response_model=CredentialResponse,
    summary="Obtener datos de credencial virtual por RFC",
    description="""
    Obtiene los datos necesarios para generar una credencial virtual.

    **Usado por la página de credencial virtual**

    Retorna:
    - Nombre del colaborador
    - RFC
    - Proveedor/Empresa
    - Tipo de servicio
    - UUID del certificado (para generar QR)
    - Fecha de vencimiento
    - Estado de la certificación
    """
)
async def get_credential_by_rfc(rfc: str):
    """
    Obtiene los datos de credencial virtual para un RFC.
    """
    logger.info(f"GET /onboarding/credential/{rfc}")

    if not rfc or len(rfc) < 10:
        return CredentialResponse(
            success=False,
            status="not_found",
            nombre="",
            rfc=rfc,
            is_expired=False,
            message="RFC inválido"
        )

    try:
        service = get_onboarding_service_singleton()

        # Obtener datos del colaborador por RFC
        credential_data = await service.get_credential_data_by_rfc(rfc)

        if not credential_data:
            return CredentialResponse(
                success=False,
                status="not_found",
                nombre="",
                rfc=rfc.upper(),
                is_expired=False,
                message="No se encontró registro para este RFC"
            )

        # Determinar estado
        is_approved = credential_data.get("is_approved", False)
        is_expired = credential_data.get("is_expired", False)

        if is_approved and not is_expired:
            status = "approved"
            message = "Certificación vigente"
        elif is_approved and is_expired:
            status = "expired"
            message = "Certificación expirada"
        else:
            status = "not_approved"
            message = "Sin certificación aprobada"

        # Consultar hoja 6.3 Biblioteca de Personal Terceros para alto riesgo
        alto_riesgo = False
        alto_riesgo_data = None
        edad = None
        nss_value = credential_data.get("nss")

        if nss_value:
            try:
                alto_riesgo_data = await _lookup_high_risk_by_nss(nss_value)
                if alto_riesgo_data:
                    alto_riesgo = True
                    edad = alto_riesgo_data.get("edad")
            except Exception as hr_err:
                logger.warning(f"Error consultando alto riesgo para NSS {nss_value}: {hr_err}")

        return CredentialResponse(
            success=True,
            status=status,
            nombre=credential_data.get("full_name", ""),
            rfc=rfc.upper(),
            proveedor=credential_data.get("proveedor"),
            tipo_servicio=credential_data.get("tipo_servicio"),
            nss=credential_data.get("nss"),
            rfc_empresa=credential_data.get("rfc_empresa"),
            email=credential_data.get("email"),
            cert_uuid=credential_data.get("cert_uuid"),
            vencimiento=credential_data.get("vencimiento"),
            fecha_emision=credential_data.get("fecha_emision"),
            url_imagen=credential_data.get("url_imagen"),
            is_expired=is_expired,
            message=message,
            alto_riesgo=alto_riesgo,
            edad=edad,
            alto_riesgo_data=alto_riesgo_data,
        )

    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error getting credential: {str(e)}")
        return CredentialResponse(
            success=False,
            status="not_found",
            nombre="",
            rfc=rfc.upper(),
            is_expired=False,
            message=f"Error al consultar: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting credential: {str(e)}")
        return CredentialResponse(
            success=False,
            status="not_found",
            nombre="",
            rfc=rfc.upper(),
            is_expired=False,
            message="Error interno del servidor"
        )


# ============================================
# Endpoints para actualización de perfil del colaborador
# ============================================

class ProfileVerifyRequest(BaseModel):
    """Schema para verificación de identidad del colaborador."""
    rfc: str = Field(..., description="RFC del colaborador", min_length=10, max_length=13)
    nss: str = Field(..., description="NSS del colaborador", min_length=11, max_length=11)

    @field_validator('rfc')
    @classmethod
    def validate_rfc(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator('nss')
    @classmethod
    def validate_nss(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('El NSS debe contener solo dígitos')
        return v


class ProfileUpdateRequest(BaseModel):
    """Schema para actualización de perfil del colaborador."""
    row_id: int = Field(..., description="ID de la fila en Smartsheet", gt=0)
    rfc: str = Field(..., description="RFC del colaborador (para re-verificación)", min_length=10, max_length=13)
    nss_original: str = Field(..., description="NSS original para re-verificar identidad", min_length=11, max_length=11)
    nombre: Optional[str] = Field(None, description="Nuevo nombre del colaborador")
    rfc_empresa: Optional[str] = Field(None, description="Nuevo RFC de la empresa", max_length=13)
    email: Optional[str] = Field(None, description="Nuevo correo electrónico")
    proveedor: Optional[str] = Field(None, description="Nuevo proveedor / empresa")
    tipo_servicio: Optional[str] = Field(None, description="Nuevo tipo de servicio")
    url_imagen: Optional[str] = Field(None, description="Nueva URL de foto de credencial")

    @field_validator('rfc')
    @classmethod
    def validate_rfc(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator('nss_original')
    @classmethod
    def validate_nss(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('El NSS debe contener solo dígitos')
        return v


@router.post(
    "/profile/verify",
    summary="Verificar identidad del colaborador para actualización de perfil",
    description="""
    Verifica la identidad del colaborador usando RFC + NSS.
    Si los datos coinciden, retorna la información actual del perfil.
    """
)
async def verify_profile(request: ProfileVerifyRequest):
    """
    Verifica RFC + NSS y retorna datos actuales del colaborador.
    """
    logger.info(f"POST /onboarding/profile/verify - RFC={request.rfc}")

    try:
        service = get_onboarding_service_singleton()
        collaborator = await service.get_collaborator_by_rfc_and_nss(request.rfc, request.nss)

        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Datos incorrectos. Verifica tu RFC y NSS."
            )

        return {
            "success": True,
            "row_id": collaborator.get("row_id"),
            "nombre": collaborator.get("full_name", ""),
            "rfc": collaborator.get("rfc", ""),
            "rfc_empresa": collaborator.get("rfc_empresa", ""),
            "email": collaborator.get("email", ""),
            "nss": collaborator.get("nss", ""),
            "proveedor": collaborator.get("proveedor", ""),
            "tipo_servicio": collaborator.get("tipo_servicio", ""),
            "url_imagen": collaborator.get("url_imagen", ""),
        }

    except HTTPException:
        raise
    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error in profile/verify: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al consultar el sistema"
        )
    except Exception as e:
        logger.error(f"Unexpected error in profile/verify: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


@router.put(
    "/profile/update",
    summary="Actualizar perfil del colaborador",
    description="""
    Actualiza los datos editables del perfil de un colaborador.
    Re-verifica identidad con RFC + NSS original antes de aplicar cambios.

    Campos actualizables: nombre, RFC empresa, email, proveedor/empresa, tipo de servicio, foto.
    Campos NO editables (por seguridad): RFC colaborador, NSS.
    """
)
async def update_profile(request: ProfileUpdateRequest):
    """
    Actualiza datos del perfil del colaborador en Smartsheet.
    """
    logger.info(f"PUT /onboarding/profile/update - RFC={request.rfc}, row_id={request.row_id}")

    try:
        service = get_onboarding_service_singleton()

        # Re-verificar identidad con RFC + NSS original
        collaborator = await service.get_collaborator_by_rfc_and_nss(request.rfc, request.nss_original)

        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No se pudo verificar tu identidad. Verifica tus datos."
            )

        if collaborator.get("row_id") != request.row_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Error de verificación. Los datos no coinciden."
            )

        # Construir dict de campos a actualizar (solo los que se enviaron)
        # NOTA: RFC colaborador y NSS NO son editables por seguridad
        fields_to_update = {}
        if request.nombre is not None:
            fields_to_update["nombre"] = request.nombre
        if request.rfc_empresa is not None:
            fields_to_update["rfc_empresa"] = request.rfc_empresa
        if request.email is not None:
            fields_to_update["email"] = request.email
        if request.proveedor is not None:
            fields_to_update["proveedor"] = request.proveedor
        if request.tipo_servicio is not None:
            fields_to_update["tipo_servicio"] = request.tipo_servicio
        if request.url_imagen is not None:
            fields_to_update["url_imagen"] = request.url_imagen

        if not fields_to_update:
            return {
                "success": True,
                "message": "No hay cambios que aplicar",
                "updated_fields": []
            }

        # Actualizar en Smartsheet
        updated = await service.update_collaborator_profile(request.row_id, fields_to_update)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al actualizar los datos en el sistema"
            )

        logger.info(f"Profile updated for RFC={request.rfc}, fields: {list(fields_to_update.keys())}")

        # Merge local: aplicar campos actualizados sin re-descargar la hoja
        email_sent = False
        email_masked = None
        try:
            updated_collaborator = collaborator.copy()
            if request.nombre is not None:
                updated_collaborator["full_name"] = request.nombre
            if request.rfc_empresa is not None:
                updated_collaborator["rfc_empresa"] = request.rfc_empresa
            if request.email is not None:
                updated_collaborator["email"] = request.email
            if request.proveedor is not None:
                updated_collaborator["proveedor"] = request.proveedor
            if request.tipo_servicio is not None:
                updated_collaborator["tipo_servicio"] = request.tipo_servicio
            if request.url_imagen is not None:
                updated_collaborator["url_imagen"] = request.url_imagen
            if updated_collaborator:
                email = updated_collaborator.get("email")
                full_name = updated_collaborator.get("full_name", "Colaborador")
                cert_uuid = updated_collaborator.get("cert_uuid")
                vencimiento = updated_collaborator.get("vencimiento", "")
                is_approved = updated_collaborator.get("is_approved", False)

                if email:
                    email_masked = mask_email(email)

                    if is_approved and cert_uuid:
                        # Build section results for PDF generation
                        s1 = float(str(updated_collaborator.get("seccion1", 0) or 0).replace('%', '').strip() or 0)
                        s2 = float(str(updated_collaborator.get("seccion2", 0) or 0).replace('%', '').strip() or 0)
                        s3 = float(str(updated_collaborator.get("seccion3", 0) or 0).replace('%', '').strip() or 0)
                        section_results = {
                            "seccion1": s1,
                            "seccion2": s2,
                            "seccion3": s3,
                        }

                        # Map url_imagen -> foto_url for PDF generation
                        pdf_collaborator_data = updated_collaborator.copy()
                        pdf_collaborator_data["foto_url"] = updated_collaborator.get("url_imagen", "")

                        # Resend approved certificate with updated data and PDF
                        email_sent = await asyncio.to_thread(
                            resend_approved_certificate_email,
                            email,
                            full_name,
                            cert_uuid,
                            str(vencimiento) if vencimiento else "",
                            pdf_collaborator_data,
                            section_results
                        )
                    else:
                        # Resend exam result email (rejected or no cert_uuid)
                        qr_image = await asyncio.to_thread(generate_certificate_qr, cert_uuid or str(uuid.uuid4()), API_BASE_URL)

                        s1 = float(str(updated_collaborator.get("seccion1", 0) or 0).replace('%', '').strip() or 0)
                        s2 = float(str(updated_collaborator.get("seccion2", 0) or 0).replace('%', '').strip() or 0)
                        s3 = float(str(updated_collaborator.get("seccion3", 0) or 0).replace('%', '').strip() or 0)
                        overall_score = (s1 + s2 + s3) / 3 if (s1 or s2 or s3) else 0

                        exp_date = datetime.utcnow() + timedelta(days=365)
                        if vencimiento:
                            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                                try:
                                    exp_date = datetime.strptime(str(vencimiento), fmt)
                                    break
                                except ValueError:
                                    continue

                        email_sent = await asyncio.to_thread(
                            send_qr_email,
                            email,
                            full_name,
                            qr_image,
                            exp_date,
                            cert_uuid or "N/A",
                            False,
                            overall_score
                        )

                    if email_sent:
                        logger.info(f"Certificate email resent to {email_masked} after profile update for RFC={request.rfc}")
                    else:
                        logger.warning(f"Failed to resend certificate email after profile update for RFC={request.rfc}")
        except Exception as email_error:
            logger.warning(f"Error resending certificate email after profile update: {str(email_error)}")

        return {
            "success": True,
            "message": "Perfil actualizado exitosamente",
            "updated_fields": list(fields_to_update.keys()),
            "email_sent": email_sent,
            "email_masked": email_masked
        }

    except HTTPException:
        raise
    except OnboardingSmartsheetServiceError as e:
        logger.error(f"Smartsheet error in profile/update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar en el sistema"
        )
    except Exception as e:
        logger.error(f"Unexpected error in profile/update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


# ============================================================
# Correo especial: solicitud de actualización de foto
# ============================================================

def send_photo_update_request_email(
    email_to: str,
    full_name: str,
    rfc: str,
    cert_uuid: str,
    expiration_date_str: str,
    collaborator_data: dict = None,
    section_results: dict = None
) -> bool:
    """
    Envía correo solicitando actualización de foto de credencial.
    Incluye PDF con placeholder y enlace a /actualizar-perfil.
    Correo de uso único para usuarios sin foto por fallo de GCS.
    """
    try:
        qr_image = generate_certificate_qr(cert_uuid, API_BASE_URL)

        expiration_date = None
        for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
            try:
                expiration_date = datetime.strptime(str(expiration_date_str), date_format)
                break
            except ValueError:
                continue
        if not expiration_date:
            expiration_date = datetime.utcnow() + timedelta(days=365)

        subject = f"Acción Requerida: Actualiza tu Foto de Credencial - {full_name}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9fafb;
                }}
                .container {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    padding: 30px;
                    margin: 20px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 3px solid #FFC600;
                }}
                .logo {{
                    max-height: 80px;
                    margin-bottom: 15px;
                }}
                h1 {{
                    color: #1f2937;
                    font-size: 22px;
                    margin: 0;
                }}
                .alert-box {{
                    background-color: #FEF3C7;
                    border-left: 4px solid #F59E0B;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .certificate-info {{
                    background-color: #f0fdf4;
                    border-left: 4px solid #16a34a;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .steps-box {{
                    background-color: #EFF6FF;
                    border: 1px solid #BFDBFE;
                    padding: 20px;
                    margin: 20px 0;
                    border-radius: 8px;
                }}
                .btn {{
                    display: inline-block;
                    background-color: #D91E18;
                    color: #ffffff;
                    padding: 14px 40px;
                    text-decoration: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    font-size: 12px;
                    color: #6b7280;
                }}
                .highlight {{
                    color: #16a34a;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="https://entersys.mx/images/coca-cola-femsa-logo.png" alt="FEMSA" class="logo">
                    <h1>Actualización de Foto de Credencial</h1>
                </div>

                <p>Estimado/a <strong>{full_name}</strong>,</p>

                <div class="alert-box">
                    <p style="margin: 0;"><strong>Coca-Cola FEMSA (KOF)</strong> requiere que todos los colaboradores cuenten con
                    su <strong>foto de credencial actualizada</strong> por motivos de seguridad en el acceso a sus instalaciones.</p>
                </div>

                <p>Como parte del proceso de seguridad, <strong>Coca-Cola FEMSA requiere de manera obligatoria</strong>
                que todos los colaboradores mantengan su foto de credencial actualizada.
                Al recibir este correo, es indispensable que realices la actualización de tu fotografía
                a la brevedad posible para mantener tu acceso vigente a las instalaciones.</p>

                <div class="certificate-info">
                    <p><strong>Tu Certificación Actual:</strong></p>
                    <ul style="margin: 5px 0;">
                        <li>Nombre: <strong>{full_name}</strong></li>
                        <li>RFC: <strong>{rfc}</strong></li>
                        <li>Estado: <span class="highlight">VIGENTE</span></li>
                        <li>Válido hasta: <span class="highlight">{expiration_date.strftime('%d/%m/%Y')}</span></li>
                    </ul>
                </div>

                <p>Adjunto a este correo encontrarás tu certificado PDF y código QR actuales.
                <strong>Una vez que actualices tu foto</strong>, recibirás una nueva versión con tu fotografía.</p>

                <div class="steps-box">
                    <p style="margin: 0 0 10px 0; font-weight: bold; color: #1E40AF;">Para actualizar tu foto:</p>
                    <ol style="margin: 0; padding-left: 20px;">
                        <li>Haz clic en el botón de abajo</li>
                        <li>Ingresa tu <strong>RFC</strong> y <strong>NSS</strong></li>
                        <li>Toma una nueva foto con tu cámara</li>
                        <li>Guarda los cambios</li>
                    </ol>
                </div>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://www.entersys.mx/actualizar-perfil" class="btn">
                        Actualizar mi Foto
                    </a>
                </div>

                <p><strong>Importante:</strong></p>
                <ul>
                    <li>Tu certificación sigue vigente, no es necesario volver a realizar el examen.</li>
                    <li>La foto debe ser tipo credencial: rostro visible, fondo claro, sin accesorios que cubran el rostro.</li>
                    <li>Puedes acceder desde tu celular o computadora con cámara.</li>
                </ul>

                <div class="footer">
                    <p>Este es un correo enviado por el equipo de EnterSys a solicitud de Coca-Cola FEMSA.</p>
                    <p>&copy; {datetime.utcnow().year} FEMSA - Entersys. Todos los derechos reservados.</p>
                </div>
            </div>
        </body>
        </html>
        """

        attachments = []

        # QR adjunto
        attachments.append({
            "filename": f"certificado_qr_{cert_uuid[:8]}.png",
            "content": base64.b64encode(qr_image).decode('utf-8')
        })

        # PDF con placeholder
        if collaborator_data:
            try:
                pdf_data = collaborator_data.copy()
                pdf_data.update({
                    "full_name": full_name,
                    "email": email_to,
                    "cert_uuid": cert_uuid,
                    "vencimiento": expiration_date.strftime('%d/%m/%Y'),
                    "fecha_emision": datetime.utcnow().strftime('%d/%m/%Y'),
                    "is_approved": True,
                })
                if "foto_url" not in pdf_data and "url_imagen" in pdf_data:
                    pdf_data["foto_url"] = pdf_data["url_imagen"]

                pdf_bytes = generate_certificate_pdf(
                    collaborator_data=pdf_data,
                    section_results=section_results,
                    qr_image_bytes=qr_image
                )
                attachments.append({
                    "filename": f"certificado_{rfc.upper()}.pdf",
                    "content": base64.b64encode(pdf_bytes).decode('utf-8')
                })
            except Exception as e:
                logger.warning(f"Could not generate PDF for photo update request: {e}")

        result = send_email_via_gmail_api(
            to_emails=[email_to],
            subject=subject,
            html_content=html_content,
            attachments=attachments
        )

        if result:
            logger.info(f"Photo update request email sent to {email_to} for RFC {rfc}")
        return result

    except Exception as e:
        logger.error(f"Error sending photo update request email: {e}")
        return False


# ============================================================
# SOPORTE AUTH (must be defined before endpoints that use it)
# ============================================================

_security = HTTPBearer()


def _create_support_token(username: str) -> str:
    """Crea un token HMAC para sesión de soporte (válido 8 horas)."""
    expires = int((datetime.utcnow() + timedelta(hours=8)).timestamp())
    payload = f"{username}:{expires}"
    sig = hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_support_token(token: str) -> str:
    """Verifica token de soporte. Retorna username o lanza HTTPException."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        username, expires_str, sig = parts
        payload = f"{username}:{expires_str}"
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid signature")
        if int(expires_str) < int(datetime.utcnow().timestamp()):
            raise ValueError("Token expired")
        return username
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


async def require_support_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Dependency que protege endpoints de soporte."""
    return _verify_support_token(credentials.credentials)


@router.post(
    "/support/login",
    summary="Login del panel de soporte",
)
async def support_login(request: dict):
    """Autentica usuario de soporte y retorna token."""
    username = request.get("username", "").strip()
    password = request.get("password", "")

    if username != settings.SUPPORT_USERNAME or password != settings.SUPPORT_PASSWORD:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = _create_support_token(username)
    logger.info(f"Support login successful: {username}")

    return {
        "success": True,
        "token": token,
        "username": username,
        "expires_in": 8 * 60 * 60,
    }


@router.post(
    "/send-photo-update-request/{rfc}",
    summary="Enviar correo de solicitud de actualización de foto",
    description="Envía un correo al colaborador solicitando que actualice su foto de credencial."
)
async def send_photo_update_request(rfc: str, _user: str = Depends(require_support_auth)):
    """
    Endpoint para enviar correo de solicitud de foto a un colaborador sin foto.
    """
    logger.info(f"POST /onboarding/send-photo-update-request/{rfc}")

    if not rfc or len(rfc) < 10:
        raise HTTPException(status_code=400, detail="RFC inválido")

    try:
        service = get_onboarding_service_singleton()
        credential_data = await service.get_credential_data_by_rfc(rfc)

        if not credential_data:
            raise HTTPException(status_code=404, detail="No se encontró registro para este RFC")

        if credential_data.get("url_imagen"):
            return {
                "success": False,
                "message": "Este colaborador ya tiene foto registrada",
                "email_sent": False
            }

        email = credential_data.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="El colaborador no tiene email registrado")

        full_name = credential_data.get("full_name", "Colaborador")
        cert_uuid = credential_data.get("cert_uuid", "")
        vencimiento = credential_data.get("vencimiento", "")

        collaborator_data = {
            "rfc": rfc.upper(),
            "proveedor": credential_data.get("proveedor"),
            "tipo_servicio": credential_data.get("tipo_servicio"),
            "nss": credential_data.get("nss"),
            "rfc_empresa": credential_data.get("rfc_empresa"),
            "foto_url": "",  # sin foto, usará placeholder
        }

        section_results = credential_data.get("section_results")

        email_sent = await asyncio.to_thread(
            send_photo_update_request_email,
            email, full_name, rfc.upper(), cert_uuid, str(vencimiento),
            collaborator_data, section_results
        )

        masked = mask_email(email)

        return {
            "success": email_sent,
            "message": "Correo de solicitud de foto enviado" if email_sent else "Error al enviar el correo",
            "email_sent": email_sent,
            "email_masked": masked,
            "nombre": full_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in send-photo-update-request: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


# ============================================================
# PANEL DE SOPORTE
# ============================================================

@router.get(
    "/support/no-photo-users",
    summary="Listar usuarios aprobados sin foto",
    description="Obtiene la lista de colaboradores aprobados que no tienen foto registrada."
)
async def list_no_photo_users(_user: str = Depends(require_support_auth)):
    """Lista todos los aprobados sin foto para el panel de soporte."""
    try:
        service = get_onboarding_service_singleton()
        registros = await service.get_all_registros()

        no_photo = []
        for r in registros:
            url_img = r.get("url_imagen") or ""
            resultado = r.get("Resultado Examen", "") or ""
            if not str(url_img).strip() and str(resultado).strip().lower() == "aprobado":
                no_photo.append({
                    "rfc": r.get("RFC del Colaborador", ""),
                    "nombre": r.get("Nombre Colaborador", ""),
                    "email": r.get("Correo Electrónico", ""),
                    "proveedor": r.get("Proveedor / Empresa", ""),
                    "nss": r.get("NSS del Colaborador", ""),
                })

        return {"success": True, "total": len(no_photo), "users": no_photo}

    except Exception as e:
        logger.error(f"Error listing no-photo users: {e}")
        raise HTTPException(status_code=500, detail="Error al consultar registros")


@router.post(
    "/support/send-all-photo-requests",
    summary="Enviar correo de foto a TODOS los aprobados sin foto",
    description="Envía el correo de solicitud de actualización de foto a todos los aprobados sin foto."
)
async def send_all_photo_requests(_user: str = Depends(require_support_auth)):
    """Envía correos masivos de solicitud de foto."""
    try:
        service = get_onboarding_service_singleton()
        registros = await service.get_all_registros()

        no_photo_rfcs = []
        for r in registros:
            url_img = r.get("url_imagen") or ""
            resultado = r.get("Resultado Examen", "") or ""
            if not str(url_img).strip() and str(resultado).strip().lower() == "aprobado":
                rfc = r.get("RFC del Colaborador", "")
                if rfc:
                    no_photo_rfcs.append(rfc)

        sent = 0
        failed = 0
        results = []
        for rfc in no_photo_rfcs:
            try:
                credential_data = await service.get_credential_data_by_rfc(rfc)
                if not credential_data:
                    results.append({"rfc": rfc, "status": "not_found"})
                    failed += 1
                    continue

                if credential_data.get("url_imagen"):
                    results.append({"rfc": rfc, "status": "has_photo"})
                    continue

                email = credential_data.get("email")
                if not email:
                    results.append({"rfc": rfc, "status": "no_email"})
                    failed += 1
                    continue

                full_name = credential_data.get("full_name", "Colaborador")
                cert_uuid = credential_data.get("cert_uuid", "")
                vencimiento = credential_data.get("vencimiento", "")

                collaborator_data = {
                    "rfc": rfc.upper(),
                    "proveedor": credential_data.get("proveedor"),
                    "tipo_servicio": credential_data.get("tipo_servicio"),
                    "nss": credential_data.get("nss"),
                    "rfc_empresa": credential_data.get("rfc_empresa"),
                    "foto_url": "",
                }
                section_results = credential_data.get("section_results")

                email_sent = await asyncio.to_thread(
                    send_photo_update_request_email,
                    email, full_name, rfc.upper(), cert_uuid, str(vencimiento),
                    collaborator_data, section_results
                )

                if email_sent:
                    sent += 1
                    results.append({"rfc": rfc, "status": "sent", "email": mask_email(email)})
                else:
                    failed += 1
                    results.append({"rfc": rfc, "status": "send_failed"})

            except Exception as e:
                failed += 1
                results.append({"rfc": rfc, "status": "error", "detail": str(e)[:100]})

        return {
            "success": True,
            "total": len(no_photo_rfcs),
            "sent": sent,
            "failed": failed,
            "results": results
        }

    except Exception as e:
        logger.error(f"Error in send-all-photo-requests: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post(
    "/support/resend-cert/{rfc}",
    summary="Reenviar certificado por RFC (soporte, sin NSS)",
    description="Reenvía el certificado al email registrado sin requerir NSS. Solo para uso de soporte."
)
async def support_resend_cert(rfc: str, _user: str = Depends(require_support_auth)):
    """Reenvía certificado sin requerir NSS - uso exclusivo de soporte."""
    logger.info(f"POST /support/resend-cert/{rfc}")

    if not rfc or len(rfc) < 10:
        raise HTTPException(status_code=400, detail="RFC inválido")

    try:
        service = get_onboarding_service_singleton()
        credential_data = await service.get_credential_data_by_rfc(rfc)

        if not credential_data:
            raise HTTPException(status_code=404, detail="No se encontró registro para este RFC")

        email = credential_data.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="El colaborador no tiene email registrado")

        full_name = credential_data.get("full_name", "Colaborador")
        cert_uuid = credential_data.get("cert_uuid", "")
        vencimiento = credential_data.get("vencimiento", "")
        is_approved = credential_data.get("is_approved", False)

        if not is_approved or not cert_uuid:
            raise HTTPException(status_code=400, detail="El colaborador no tiene certificación aprobada")

        collaborator_data = {
            "rfc": rfc.upper(),
            "proveedor": credential_data.get("proveedor"),
            "tipo_servicio": credential_data.get("tipo_servicio"),
            "nss": credential_data.get("nss"),
            "rfc_empresa": credential_data.get("rfc_empresa"),
            "url_imagen": credential_data.get("url_imagen", ""),
            "foto_url": credential_data.get("url_imagen", ""),
        }
        section_results = credential_data.get("section_results")

        email_sent = await asyncio.to_thread(
            resend_approved_certificate_email,
            email, full_name, cert_uuid, str(vencimiento),
            collaborator_data, section_results
        )

        return {
            "success": email_sent,
            "message": "Certificado reenviado" if email_sent else "Error al enviar",
            "email_sent": email_sent,
            "email_masked": mask_email(email),
            "nombre": full_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in support/resend-cert: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get(
    "/support/logs",
    summary="Obtener logs recientes del sistema",
    description="Obtiene los últimos logs del sistema filtrados por tipo y búsqueda."
)
async def get_support_logs(
    search: Optional[str] = Query(None, description="Buscar en logs (RFC, email, error, etc.)"),
    level: Optional[str] = Query(None, description="Filtrar por nivel: error, warning, info"),
    limit: int = Query(100, description="Número de líneas", ge=10, le=500),
    _user: str = Depends(require_support_auth),
):
    """Obtiene logs recientes del sistema para soporte."""
    import subprocess

    try:
        # Leer logs del proceso actual via docker logs (stdout/stderr)
        cmd = ["tail", "-n", str(limit * 3), "/proc/1/fd/1"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            raw_lines = result.stdout.splitlines() if result.stdout else []
        except Exception:
            raw_lines = []

        # Fallback: leer desde logging handler en memoria
        if not raw_lines:
            # Usar el MemoryLogHandler si existe
            handler = _get_memory_log_handler()
            raw_lines = list(handler.buffer) if handler else []

        # Filtrar y parsear
        logs = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue

            # Determinar nivel
            log_level = "info"
            if "ERROR" in line or "Error" in line or "error" in line:
                log_level = "error"
            elif "WARNING" in line or "Warning" in line or "warn" in line:
                log_level = "warning"

            # Filtrar por nivel
            if level and log_level != level:
                continue

            # Filtrar por búsqueda
            if search and search.upper() not in line.upper():
                continue

            logs.append({
                "message": line[:500],
                "level": log_level,
            })

        # Tomar solo las últimas N
        logs = logs[-limit:]

        return {
            "success": True,
            "total": len(logs),
            "logs": logs
        }

    except Exception as e:
        logger.error(f"Error getting support logs: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener logs")


# In-memory log handler for support panel
class _MemoryLogHandler(logging.Handler):
    """Stores last N log records in memory for the support panel."""
    def __init__(self, capacity=2000):
        super().__init__()
        from collections import deque
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            pass


_memory_handler_instance = None


def _get_memory_log_handler():
    global _memory_handler_instance
    return _memory_handler_instance


def _setup_memory_log_handler():
    global _memory_handler_instance
    if _memory_handler_instance is None:
        _memory_handler_instance = _MemoryLogHandler(capacity=2000)
        _memory_handler_instance.setFormatter(
            logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
        )
        logging.getLogger().addHandler(_memory_handler_instance)
        # Also capture uvicorn access logs
        for name in ['uvicorn', 'uvicorn.access', 'uvicorn.error', '']:
            log = logging.getLogger(name)
            if _memory_handler_instance not in log.handlers:
                log.addHandler(_memory_handler_instance)


# Initialize on module load
_setup_memory_log_handler()
