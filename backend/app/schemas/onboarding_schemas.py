# app/schemas/onboarding_schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID


class OnboardingGenerateRequest(BaseModel):
    """
    Schema para la solicitud de generación de QR desde Smartsheet Bridge.
    """
    row_id: int = Field(..., description="ID de la fila en Smartsheet", gt=0)
    full_name: str = Field(..., description="Nombre completo del usuario", min_length=1, max_length=255)
    email: EmailStr = Field(..., description="Correo electrónico del usuario")
    score: float = Field(..., description="Puntaje de evaluación del usuario", ge=0, le=100)

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Valida y limpia el nombre completo"""
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "row_id": 123456789,
                "full_name": "Juan Pérez García",
                "email": "juan.perez@empresa.com",
                "score": 85.5
            }
        }


class OnboardingGenerateResponse(BaseModel):
    """
    Schema para la respuesta de generación de QR exitosa.
    """
    success: bool = Field(..., description="Indica si la operación fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo del resultado")
    data: Optional["OnboardingGenerateData"] = Field(None, description="Datos de la generación")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "QR code generated and sent successfully",
                "data": {
                    "cert_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "expiration_date": "2026-01-15",
                    "email_sent": True,
                    "smartsheet_updated": True
                }
            }
        }


class OnboardingGenerateData(BaseModel):
    """
    Datos específicos de la generación de QR.
    """
    cert_uuid: str = Field(..., description="UUID del certificado generado")
    expiration_date: str = Field(..., description="Fecha de vencimiento del certificado")
    email_sent: bool = Field(..., description="Indica si el email fue enviado")
    smartsheet_updated: bool = Field(..., description="Indica si Smartsheet fue actualizado")


class OnboardingValidateResponse(BaseModel):
    """
    Schema para la respuesta de validación de QR (principalmente para documentación).
    En la práctica, este endpoint redirige al usuario.
    """
    valid: bool = Field(..., description="Indica si el certificado es válido")
    message: str = Field(..., description="Mensaje descriptivo del resultado")
    redirect_url: str = Field(..., description="URL a la que se redirige")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "message": "Certificate is valid",
                "redirect_url": "https://entersys.mx/certificacion-seguridad/550e8400-e29b-41d4-a716-446655440000"
            }
        }


class CertificateInfo(BaseModel):
    """
    Información del certificado almacenada en Smartsheet.
    """
    row_id: int = Field(..., description="ID de la fila en Smartsheet")
    cert_uuid: str = Field(..., description="UUID del certificado")
    full_name: str = Field(..., description="Nombre completo del titular")
    email: str = Field(..., description="Correo electrónico del titular")
    score: float = Field(..., description="Puntaje de evaluación")
    expiration_date: datetime = Field(..., description="Fecha de vencimiento")
    qr_sent: bool = Field(False, description="Indica si el QR fue enviado")
    last_validation: Optional[datetime] = Field(None, description="Última fecha de validación")


class OnboardingErrorResponse(BaseModel):
    """
    Schema para respuestas de error.
    """
    success: bool = Field(False, description="Siempre False para errores")
    error: str = Field(..., description="Código de error")
    message: str = Field(..., description="Mensaje descriptivo del error")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "SCORE_TOO_LOW",
                "message": "Score must be >= 80 to generate certificate. Current score: 75.0"
            }
        }


# ============================================
# Schemas para el formulario de examen público
# ============================================

class ExamCategoryOut(BaseModel):
    """Categoría del examen (enviada al frontend)."""
    id: int
    name: str
    color: str
    display_order: int
    questions_to_show: int
    min_score_percent: int

    class Config:
        from_attributes = True


class ExamQuestionOut(BaseModel):
    """Pregunta del examen (SIN correct_answer, nunca se envía al frontend)."""
    id: int
    category_id: int
    question_text: str
    options: list[str]

    class Config:
        from_attributes = True


class ExamConfigResponse(BaseModel):
    """Respuesta del endpoint GET /exam-questions."""
    categories: list[ExamCategoryOut]
    questions: list[ExamQuestionOut]


class ExamAnswer(BaseModel):
    """Respuesta individual de una pregunta del examen."""
    question_id: int = Field(..., description="ID de la pregunta en BD")
    answer: str = Field(..., description="Respuesta seleccionada")


class SectionResult(BaseModel):
    """Resultado de una sección del examen."""
    section_name: str = Field(..., description="Nombre de la sección")
    section_number: int = Field(..., description="Número de sección (1, 2 o 3)")
    correct_count: int = Field(..., description="Respuestas correctas")
    total_questions: int = Field(10, description="Total de preguntas en la sección")
    score: float = Field(..., description="Porcentaje de la sección")
    approved: bool = Field(..., description="Si aprobó la sección (>=80%)")


class ExamSubmitRequest(BaseModel):
    """
    Schema para la solicitud de envío del examen de seguridad.
    Ahora con 30 preguntas divididas en 3 secciones.
    """
    # Datos personales
    nombre_completo: str = Field(..., description="Nombre completo", min_length=2, max_length=255)
    rfc_colaborador: str = Field(..., description="RFC del colaborador", min_length=10, max_length=13)
    rfc_empresa: Optional[str] = Field(None, description="RFC de la empresa", max_length=13)
    nss: Optional[str] = Field(None, description="NSS del colaborador", max_length=11)
    tipo_servicio: Optional[str] = Field(None, description="Tipo de servicio")
    proveedor: str = Field(..., description="Nombre del proveedor", min_length=2, max_length=255)
    email: EmailStr = Field(..., description="Correo electrónico")

    # URL de la foto de credencial (opcional, almacenada en GCS)
    url_imagen: Optional[str] = Field(None, description="URL de la foto de credencial en GCS")

    # Respuestas del examen (dinámico según categorías activas)
    answers: list[ExamAnswer] = Field(..., description="Lista de respuestas del examen")

    @field_validator('nombre_completo')
    @classmethod
    def validate_nombre(cls, v: str) -> str:
        return v.strip().title()

    @field_validator('rfc_colaborador', 'rfc_empresa')
    @classmethod
    def validate_rfc(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().upper()
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "nombre_completo": "Juan Pérez García",
                "rfc_colaborador": "PEGJ850101XXX",
                "rfc_empresa": "EMP850101XXX",
                "nss": "12345678901",
                "tipo_servicio": "Mantenimiento",
                "proveedor": "Servicios Industriales SA",
                "email": "juan.perez@empresa.com",
                "answers": [
                    {"question_id": 1, "answer": "Respuesta"}
                    # ... respuestas del examen
                ]
            }
        }


class ExamSubmitResponse(BaseModel):
    """
    Schema para la respuesta del envío del examen.
    Incluye resultados por sección.
    """
    success: bool = Field(..., description="Si el envío fue exitoso")
    approved: bool = Field(..., description="Si el examen fue aprobado (todas las secciones >=80%)")
    sections: list[SectionResult] = Field(..., description="Resultados por sección")
    overall_score: float = Field(..., description="Promedio general de las 3 secciones")
    message: str = Field(..., description="Mensaje descriptivo")
    attempts_used: int = Field(..., description="Intentos utilizados")
    attempts_remaining: int = Field(..., description="Intentos restantes")
    can_retry: bool = Field(..., description="Si puede volver a intentar")
    ref_code: Optional[str] = Field(None, description="Código de referencia interno (solo presente si hubo algún issue)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "approved": False,
                "sections": [
                    {"section_name": "Seguridad", "section_number": 1, "correct_count": 9, "total_questions": 10, "score": 90.0, "approved": True},
                    {"section_name": "Inocuidad", "section_number": 2, "correct_count": 8, "total_questions": 10, "score": 80.0, "approved": True},
                    {"section_name": "Ambiental", "section_number": 3, "correct_count": 6, "total_questions": 10, "score": 60.0, "approved": False}
                ],
                "overall_score": 76.67,
                "message": "No aprobaste. Sección 'Ambiental' requiere mínimo 80%.",
                "attempts_used": 1,
                "attempts_remaining": 2,
                "can_retry": True,
                "ref_code": None
            }
        }


class ExamStatusResponse(BaseModel):
    """
    Schema para verificar si un RFC puede realizar el examen.
    """
    can_take_exam: bool = Field(..., description="Si puede realizar el examen")
    rfc: str = Field(..., description="RFC consultado")
    attempts_used: int = Field(..., description="Intentos utilizados")
    attempts_remaining: int = Field(..., description="Intentos restantes (máximo 3)")
    is_approved: bool = Field(..., description="Si ya está aprobado")
    is_expired: bool = Field(False, description="Si el certificado aprobado ya expiró (pasó 1 año)")
    last_attempt_date: Optional[str] = Field(None, description="Fecha del último intento")
    expiration_date: Optional[str] = Field(None, description="Fecha de vencimiento del certificado")
    message: str = Field(..., description="Mensaje descriptivo")
    section_results: Optional[dict] = Field(None, description="Resultados por sección si existe registro")
    certificate_resent: bool = Field(False, description="Si se reenvió el certificado por correo")

    class Config:
        json_schema_extra = {
            "example": {
                "can_take_exam": True,
                "rfc": "PEGJ850101XXX",
                "attempts_used": 1,
                "attempts_remaining": 2,
                "is_approved": False,
                "is_expired": False,
                "last_attempt_date": "2025-12-14",
                "expiration_date": "2026-12-14",
                "message": "Puedes realizar el examen. Te quedan 2 intentos.",
                "section_results": {
                    "Seccion1": 90,
                    "Seccion2": 70,
                    "Seccion3": 80
                },
                "certificate_resent": False
            }
        }


# ============================================
# Schemas para reenvío de certificado (soporte)
# ============================================

class ResendCertificateRequest(BaseModel):
    """Schema para la solicitud de reenvío de certificado por soporte."""
    rfc: str = Field(..., description="RFC del colaborador", min_length=10, max_length=13)
    nss: str = Field(..., description="NSS del colaborador (verificación de identidad)", min_length=11, max_length=11)

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

    class Config:
        json_schema_extra = {
            "example": {
                "rfc": "PEGJ850101XXX",
                "nss": "12345678901"
            }
        }


class ResendCertificateResponse(BaseModel):
    """Schema para la respuesta de reenvío de certificado."""
    success: bool = Field(..., description="Si el reenvío fue exitoso")
    message: str = Field(..., description="Mensaje descriptivo")
    email_masked: Optional[str] = Field(None, description="Email censurado al que se envió (ej: arm***@entersys.mx)")
    resultado: Optional[str] = Field(None, description="Resultado del examen (Aprobado/Reprobado)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Certificado reenviado exitosamente",
                "email_masked": "arm***@entersys.mx",
                "resultado": "Aprobado"
            }
        }


# Rebuild models to handle forward references
OnboardingGenerateResponse.model_rebuild()
