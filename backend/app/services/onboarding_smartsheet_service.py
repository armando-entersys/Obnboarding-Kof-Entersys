# app/services/onboarding_smartsheet_service.py
import asyncio
import smartsheet
import logging
import time
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta

from app.core.config import settings


class OnboardingSmartsheetServiceError(Exception):
    """Excepción personalizada para errores del servicio de Smartsheet de Onboarding"""
    pass


class OnboardingSmartsheetService:
    """
    Servicio especializado para operaciones de Smartsheet relacionadas con el
    sistema de validación de onboarding dinámico.

    Maneja 2 hojas:
    - SHEET_REGISTROS (4716003029110660): Registro principal con estatus del examen
    - SHEET_RESPUESTAS (4715605744635780): Bitácora de respuestas (Correcto/Incorrecto)
    """

    # IDs de las hojas de Smartsheet
    SHEET_REGISTROS_ID = 4716003029110660  # Registros_OnBoarding (estatus, intentos, resultado)
    SHEET_RESPUESTAS_ID = 4715605744635780  # Respuestas_Examen_OnBoarding (bitácora de respuestas)

    # Nombres de columnas en hoja de Registros
    # Datos del Colaborador (primera pantalla del formulario)
    COLUMN_NOMBRE_COLABORADOR = "Nombre Colaborador"
    COLUMN_RFC_COLABORADOR = "RFC del Colaborador"
    COLUMN_RFC_EMPRESA = "RFC de la Empresa"
    COLUMN_NSS_COLABORADOR = "NSS del Colaborador"
    COLUMN_TIPO_SERVICIO = "Tipo de Servicio"
    COLUMN_PROVEEDOR_EMPRESA = "Proveedor / Empresa"
    COLUMN_CORREO_ELECTRONICO = "Correo Electrónico"
    COLUMN_URL_IMAGEN = "url_imagen"  # URL de la foto de credencial en GCS

    # Datos del examen
    COLUMN_RFC = "RFC del Colaborador"  # Alias para compatibilidad
    COLUMN_FECHA_EXAMEN = "FechaExamen"
    COLUMN_TIPO = "Tipo"
    COLUMN_SECCION1 = "Seguridad"  # Score sección Seguridad (1-10)
    COLUMN_SECCION2 = "Inocuidad"  # Score sección Inocuidad (11-20)
    COLUMN_SECCION3 = "Ambiental"  # Score sección Ambiental (21-30)
    COLUMN_RESULTADO = "Resultado Examen"  # Aprobado/Reprobado
    COLUMN_UUID = "UUID"
    COLUMN_CERT_UUID = "UUID"  # Alias para compatibilidad con validacion
    COLUMN_ENVIO_CERT = "Envio Certificado"
    COLUMN_VENCIMIENTO = "Vencimiento"
    COLUMN_INTENTOS = "Intentos"
    COLUMN_ESTATUS_EXAMEN = "Estatus Examen"  # 1 = puede continuar
    COLUMN_NOTA = "Nota"
    COLUMN_REENVIAR_CORREO = "Reenviar correo"

    # Nombres de columnas en hoja de Respuestas (Bitácora)
    COLUMN_RESP_RFC = "RFC"  # En esta hoja la columna se llama solo "RFC"
    COLUMN_RESP_FECHA = "FechaExamen"
    COLUMN_RESP_SECCION = "Seccion"
    # R1 a R30 para las respuestas (Correcto/Incorrecto)

    # Constantes
    MAX_ATTEMPTS = 3
    MIN_SECTION_SCORE = 80.0

    def __init__(self, sheet_id: Optional[int] = None):
        """
        Inicializa el servicio de Smartsheet para Onboarding.

        Args:
            sheet_id: ID de la hoja de Smartsheet (opcional, para compatibilidad)
        """
        self.logger = logging.getLogger(__name__)
        self.sheet_id = sheet_id

        try:
            self.client = smartsheet.Smartsheet(settings.SMARTSHEET_ACCESS_TOKEN)
            self.client.errors_as_exceptions(True)
            self.logger.info("Onboarding Smartsheet service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Smartsheet client: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Error initializing Smartsheet client: {str(e)}"
            )

        # Cache de mapeo columna ID -> nombre (por hoja)
        self._column_map: Dict[int, str] = {}
        self._reverse_column_map: Dict[str, int] = {}
        self._registros_column_map: Dict[int, str] = {}
        self._registros_reverse_map: Dict[str, int] = {}
        self._respuestas_column_map: Dict[int, str] = {}
        self._respuestas_reverse_map: Dict[str, int] = {}

        # Cache de sheet data con TTL
        self._sheet_cache: Dict[int, Any] = {}
        self._sheet_cache_time: Dict[int, float] = {}
        self._sheet_cache_ttl = 60  # 60 segundos
        self._sheet_cache_lock = asyncio.Lock()

    async def _get_column_maps(self, sheet_id: int) -> None:
        """
        Obtiene y cachea el mapeo de columnas para una hoja.

        Args:
            sheet_id: ID de la hoja
        """
        if self._column_map:
            return

        try:
            sheet = await asyncio.to_thread(self.client.Sheets.get_sheet, sheet_id, include=['format'])

            for column in sheet.columns:
                self._column_map[column.id] = column.title
                self._reverse_column_map[column.title] = column.id

            self.logger.debug(f"Loaded {len(self._column_map)} columns for sheet {sheet_id}")

        except Exception as e:
            self.logger.error(f"Error loading column maps: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error loading column maps: {str(e)}")

    def _get_column_id(self, column_name: str) -> int:
        """
        Obtiene el ID de una columna por su nombre.

        Args:
            column_name: Nombre de la columna

        Returns:
            ID de la columna

        Raises:
            OnboardingSmartsheetServiceError: Si la columna no existe
        """
        if column_name not in self._reverse_column_map:
            raise OnboardingSmartsheetServiceError(
                f"Column '{column_name}' not found in sheet"
            )
        return self._reverse_column_map[column_name]

    async def _get_cached_sheet(self, sheet_id: int) -> Any:
        """Obtiene sheet data con cache TTL de 60 segundos y protección anti-estampida."""
        now = time.time()
        cached_time = self._sheet_cache_time.get(sheet_id, 0)
        if sheet_id in self._sheet_cache and (now - cached_time) < self._sheet_cache_ttl:
            self.logger.debug(f"Cache HIT for sheet {sheet_id}")
            return self._sheet_cache[sheet_id]

        # Lock: solo 1 coroutine descarga, las demás esperan
        async with self._sheet_cache_lock:
            # Re-check después de adquirir el lock (otro coroutine pudo haberlo llenado)
            now = time.time()
            cached_time = self._sheet_cache_time.get(sheet_id, 0)
            if sheet_id in self._sheet_cache and (now - cached_time) < self._sheet_cache_ttl:
                self.logger.debug(f"Cache HIT (post-lock) for sheet {sheet_id}")
                return self._sheet_cache[sheet_id]

            self.logger.debug(f"Cache MISS for sheet {sheet_id}, fetching from API")
            sheet = await asyncio.to_thread(self.client.Sheets.get_sheet, sheet_id)
            self._sheet_cache[sheet_id] = sheet
            self._sheet_cache_time[sheet_id] = now
            return sheet

    def _invalidate_sheet_cache(self, sheet_id: int) -> None:
        """Invalida cache de una hoja despues de update/add."""
        self._sheet_cache.pop(sheet_id, None)
        self._sheet_cache_time.pop(sheet_id, None)

    async def update_row_with_certificate(
        self,
        sheet_id: int,
        row_id: int,
        cert_uuid: str,
        expiration_date: datetime,
        is_valid: bool = True,
        score: float = 0.0
    ) -> bool:
        """
        Actualiza una fila de Smartsheet con los datos del certificado generado.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila a actualizar
            cert_uuid: UUID del certificado generado
            expiration_date: Fecha de vencimiento del certificado
            is_valid: Si el certificado es válido (score >= 80)
            score: Puntuación obtenida

        Returns:
            True si la actualización fue exitosa
        """
        try:
            await self._get_column_maps(sheet_id)

            # Construir las celdas a actualizar
            cells = [
                {
                    'column_id': self._get_column_id(self.COLUMN_UUID),
                    'value': cert_uuid
                },
                {
                    'column_id': self._get_column_id(self.COLUMN_VENCIMIENTO),
                    'value': expiration_date.strftime('%Y-%m-%d')
                }
            ]

            # Crear objeto de fila para actualización
            row_to_update = smartsheet.models.Row()
            row_to_update.id = row_id
            row_to_update.cells = [
                smartsheet.models.Cell(cell) for cell in cells
            ]

            # Ejecutar actualización
            response = await asyncio.to_thread(self.client.Sheets.update_rows, sheet_id, [row_to_update])
            self._invalidate_sheet_cache(sheet_id)

            if response.message == 'SUCCESS':
                self.logger.info(
                    f"Successfully updated row {row_id} with certificate {cert_uuid}"
                )
                return True
            else:
                self.logger.error(f"Unexpected response updating row: {response.message}")
                return False

        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error updating row: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Smartsheet API error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Error updating row with certificate: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Error updating row: {str(e)}"
            )

    async def update_last_validation(
        self,
        sheet_id: int,
        row_id: int,
        validation_time: Optional[datetime] = None
    ) -> bool:
        """
        Actualiza la columna 'Última Validación' de una fila.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila
            validation_time: Hora de validación (usa ahora si no se especifica)

        Returns:
            True si la actualización fue exitosa
        """
        try:
            await self._get_column_maps(sheet_id)

            if validation_time is None:
                validation_time = datetime.utcnow()

            # Construir celda a actualizar
            cell = smartsheet.models.Cell()
            cell.column_id = self._get_column_id(self.COLUMN_LAST_VALIDATION)
            cell.value = validation_time.strftime('%Y-%m-%d %H:%M:%S')

            # Crear fila para actualización
            row_to_update = smartsheet.models.Row()
            row_to_update.id = row_id
            row_to_update.cells = [cell]

            # Ejecutar actualización
            response = await asyncio.to_thread(self.client.Sheets.update_rows, sheet_id, [row_to_update])
            self._invalidate_sheet_cache(sheet_id)

            if response.message == 'SUCCESS':
                self.logger.info(
                    f"Updated last validation for row {row_id} to {validation_time}"
                )
                return True
            else:
                self.logger.error(f"Unexpected response: {response.message}")
                return False

        except Exception as e:
            self.logger.error(f"Error updating last validation: {str(e)}")
            # No re-raise para que la tarea en background no falle silenciosamente
            return False

    async def get_certificate_by_uuid(
        self,
        sheet_id: int,
        cert_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un certificado por su UUID en Smartsheet.

        Args:
            sheet_id: ID de la hoja
            cert_uuid: UUID del certificado a buscar

        Returns:
            Diccionario con los datos del certificado o None si no existe
        """
        try:
            await self._get_column_maps(sheet_id)

            # Obtener la hoja completa (cached)
            sheet = await self._get_cached_sheet(sheet_id)

            # Buscar la fila con el UUID
            for row in sheet.rows:
                row_data = {}

                for cell in row.cells:
                    column_name = self._column_map.get(cell.column_id, f"Col_{cell.column_id}")
                    cell_value = cell.display_value if cell.display_value is not None else cell.value
                    row_data[column_name] = cell_value

                # Verificar si es el UUID buscado
                if row_data.get(self.COLUMN_CERT_UUID) == cert_uuid:
                    row_data['row_id'] = row.id
                    self.logger.info(f"Found certificate {cert_uuid} in row {row.id}")
                    return row_data

            self.logger.warning(f"Certificate {cert_uuid} not found in sheet {sheet_id}")
            return None

        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error searching for certificate: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Smartsheet API error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Error searching for certificate: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Error searching for certificate: {str(e)}"
            )

    def is_certificate_valid(self, certificate_data: Dict[str, Any]) -> bool:
        """
        Verifica si un certificado es valido (Resultado Examen = Aprobado y no expirado).

        Args:
            certificate_data: Datos del certificado de Smartsheet

        Returns:
            True si el certificado es valido
        """
        try:
            # 1. Verificar el campo "Resultado Examen" (debe ser "Aprobado")
            resultado = certificate_data.get(self.COLUMN_RESULTADO)
            self.logger.info(f"Validating certificate - Resultado Examen: {resultado}")

            if resultado is None:
                self.logger.warning("Certificate has no 'Resultado Examen' field")
                return False

            resultado_str = str(resultado).strip().lower()
            if resultado_str != "aprobado":
                self.logger.info(f"Certificate invalid: Resultado Examen = '{resultado}' (not 'Aprobado')")
                return False

            # 2. Verificar fecha de vencimiento (campo "Vencimiento")
            expiration_str = certificate_data.get(self.COLUMN_VENCIMIENTO)
            self.logger.info(f"Validating certificate - Vencimiento: {expiration_str}")

            if not expiration_str:
                self.logger.warning("Certificate has no expiration date (Vencimiento)")
                return False

            # Parsear fecha de vencimiento (puede venir en varios formatos)
            expiration_date = None
            for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    expiration_date = datetime.strptime(str(expiration_str), date_format)
                    break
                except ValueError:
                    continue

            if expiration_date is None:
                self.logger.error(f"Could not parse expiration date: {expiration_str}")
                return False

            # Verificar si esta expirado
            is_valid = expiration_date.date() >= datetime.utcnow().date()

            if not is_valid:
                self.logger.info(f"Certificate expired on {expiration_date.date()}")
            else:
                self.logger.info(f"Certificate valid until {expiration_date.date()}")

            return is_valid

        except Exception as e:
            self.logger.error(f"Error validating certificate: {str(e)}")
            return False

    async def get_attempts_by_rfc(
        self,
        sheet_id: int,
        rfc_colaborador: str
    ) -> Dict[str, Any]:
        """
        Cuenta los intentos aprobados y fallidos de un colaborador por su RFC.

        Args:
            sheet_id: ID de la hoja
            rfc_colaborador: RFC del colaborador a buscar

        Returns:
            Diccionario con conteo de intentos:
            {
                "total": int,
                "aprobados": int,
                "fallidos": int,
                "registros": List[Dict] - Lista con datos de cada intento
            }
        """
        try:
            await self._get_column_maps(sheet_id)

            # Obtener la hoja completa (cached)
            sheet = await self._get_cached_sheet(sheet_id)

            # Contadores
            total = 0
            aprobados = 0
            fallidos = 0
            registros = []

            # Buscar todas las filas con el mismo RFC
            for row in sheet.rows:
                row_data = {}

                for cell in row.cells:
                    column_name = self._column_map.get(cell.column_id, f"Col_{cell.column_id}")
                    cell_value = cell.display_value if cell.display_value is not None else cell.value
                    row_data[column_name] = cell_value

                # Verificar si es el RFC buscado
                rfc_value = row_data.get("RFC Colaborador", "")
                if rfc_value and str(rfc_value).strip().upper() == str(rfc_colaborador).strip().upper():
                    total += 1
                    row_data['row_id'] = row.id

                    # Verificar estado (aprobado o no)
                    estado = row_data.get("Estado", "")
                    score_value = row_data.get("Score", 0)

                    # Determinar si aprobó por score o estado
                    is_approved = False
                    if estado:
                        is_approved = str(estado).lower() in ["aprobado", "approved"]
                    elif score_value:
                        try:
                            score = float(str(score_value).replace('%', '').strip())
                            is_approved = score >= 80.0
                        except (ValueError, TypeError):
                            pass

                    if is_approved:
                        aprobados += 1
                    else:
                        fallidos += 1

                    registros.append({
                        "row_id": row.id,
                        "nombre": row_data.get("Nombre Completo", ""),
                        "email": row_data.get("Email", ""),
                        "score": row_data.get("Score", ""),
                        "estado": estado,
                        "is_approved": is_approved
                    })

            self.logger.info(
                f"RFC {rfc_colaborador}: {total} intentos totales, "
                f"{aprobados} aprobados, {fallidos} fallidos"
            )

            return {
                "total": total,
                "aprobados": aprobados,
                "fallidos": fallidos,
                "registros": registros
            }

        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error getting attempts by RFC: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Smartsheet API error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Error getting attempts by RFC: {str(e)}")
            raise OnboardingSmartsheetServiceError(
                f"Error getting attempts by RFC: {str(e)}"
            )

    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica que el servicio de Smartsheet esté funcionando.

        Returns:
            Diccionario con el estado del servicio
        """
        try:
            user_info = await asyncio.to_thread(self.client.Users.get_current_user)

            return {
                "status": "healthy",
                "user": user_info.email if hasattr(user_info, 'email') else "unknown",
                "service": "onboarding_smartsheet",
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "service": "onboarding_smartsheet",
                "timestamp": datetime.utcnow().isoformat()
            }

    # ============================================
    # NUEVOS MÉTODOS PARA SISTEMA DE 3 SECCIONES
    # ============================================

    async def _get_registros_column_maps(self) -> None:
        """Obtiene y cachea el mapeo de columnas para la hoja de Registros."""
        if self._registros_column_map:
            return

        try:
            sheet = await asyncio.to_thread(self.client.Sheets.get_sheet, self.SHEET_REGISTROS_ID)
            for column in sheet.columns:
                self._registros_column_map[column.id] = column.title
                self._registros_reverse_map[column.title] = column.id
            self.logger.debug(f"Loaded {len(self._registros_column_map)} columns for Registros sheet")
        except Exception as e:
            self.logger.error(f"Error loading Registros column maps: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error loading column maps: {str(e)}")

    async def _get_respuestas_column_maps(self) -> None:
        """Obtiene y cachea el mapeo de columnas para la hoja de Respuestas."""
        if self._respuestas_column_map:
            return

        try:
            sheet = await asyncio.to_thread(self.client.Sheets.get_sheet, self.SHEET_RESPUESTAS_ID)
            for column in sheet.columns:
                self._respuestas_column_map[column.id] = column.title
                self._respuestas_reverse_map[column.title] = column.id
            self.logger.debug(f"Loaded {len(self._respuestas_column_map)} columns for Respuestas sheet")
        except Exception as e:
            self.logger.error(f"Error loading Respuestas column maps: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error loading column maps: {str(e)}")

    async def check_exam_status(self, rfc: str) -> Dict[str, Any]:
        """
        Verifica el estatus del examen para un RFC en la hoja de Registros.

        Args:
            rfc: RFC del colaborador

        Returns:
            Diccionario con:
            - can_take_exam: bool
            - attempts_used: int
            - attempts_remaining: int
            - is_approved: bool
            - is_expired: bool (si aprobó pero ya pasó 1 año)
            - last_attempt_date: str o None
            - section_results: dict o None
            - row_id: int o None (si existe registro)
            - cert_uuid: str o None (UUID del certificado si aprobó)
            - expiration_date: str o None (fecha de vencimiento del certificado)
            - full_name: str o None (nombre del colaborador)
            - email: str o None (email del colaborador)
        """
        try:
            await self._get_registros_column_maps()

            sheet = await self._get_cached_sheet(self.SHEET_REGISTROS_ID)
            rfc_upper = rfc.strip().upper()

            # Buscar registro existente con este RFC
            found_row = None
            for row in sheet.rows:
                row_data = {}
                for cell in row.cells:
                    col_name = self._registros_column_map.get(cell.column_id, "")
                    row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

                row_rfc = str(row_data.get(self.COLUMN_RFC, "")).strip().upper()
                if row_rfc == rfc_upper:
                    found_row = {"row_id": row.id, "data": row_data}
                    break

            # Si no existe registro, puede hacer el examen (primer intento)
            if not found_row:
                self.logger.info(f"RFC {rfc}: No existe registro, primer intento permitido")
                return {
                    "can_take_exam": True,
                    "attempts_used": 0,
                    "attempts_remaining": self.MAX_ATTEMPTS,
                    "is_approved": False,
                    "is_expired": False,
                    "last_attempt_date": None,
                    "section_results": None,
                    "row_id": None,
                    "estatus_examen": None,
                    "cert_uuid": None,
                    "expiration_date": None,
                    "full_name": None,
                    "email": None
                }

            # Extraer datos del registro
            data = found_row["data"]
            row_id = found_row["row_id"]

            # Verificar Estatus Examen
            estatus_examen = data.get(self.COLUMN_ESTATUS_EXAMEN)
            estatus_str = str(estatus_examen).strip() if estatus_examen else ""

            # Verificar Resultado (Aprobado/Reprobado)
            resultado = str(data.get(self.COLUMN_RESULTADO, "")).strip().lower()
            is_approved = resultado == "aprobado"

            # Obtener UUID del certificado si existe
            cert_uuid = data.get(self.COLUMN_UUID)
            cert_uuid_str = str(cert_uuid).strip() if cert_uuid else None

            # Obtener intentos
            intentos_str = str(data.get(self.COLUMN_INTENTOS, "0")).strip()
            try:
                intentos = int(intentos_str) if intentos_str else 0
            except ValueError:
                intentos = 0

            # Obtener fecha del último examen
            fecha_examen = data.get(self.COLUMN_FECHA_EXAMEN)
            fecha_str = str(fecha_examen) if fecha_examen else None

            # Obtener fecha de vencimiento
            vencimiento = data.get(self.COLUMN_VENCIMIENTO)
            vencimiento_str = str(vencimiento) if vencimiento else None

            # Verificar si el certificado ha expirado (pasó 1 año)
            is_expired = False
            if is_approved and vencimiento_str:
                # Intentar parsear la fecha de vencimiento
                expiration_date = None
                for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%d/%m/%y']:
                    try:
                        expiration_date = datetime.strptime(str(vencimiento_str), date_format)
                        if expiration_date.year < 100:
                            expiration_date = expiration_date.replace(year=expiration_date.year + 2000)
                        break
                    except ValueError:
                        continue

                if expiration_date:
                    is_expired = expiration_date.date() < datetime.utcnow().date()
                    self.logger.info(f"RFC {rfc}: Vencimiento={expiration_date.date()}, Hoy={datetime.utcnow().date()}, Expirado={is_expired}")

            # Obtener resultados por sección
            section_results = {
                "Seccion1": data.get(self.COLUMN_SECCION1),
                "Seccion2": data.get(self.COLUMN_SECCION2),
                "Seccion3": data.get(self.COLUMN_SECCION3)
            }

            # Determinar si puede hacer el examen:
            # 1. Si ya está aprobado Y no ha expirado, NO puede (debe renovar después del año)
            # 2. Si ya está aprobado PERO expiró, SI puede (renovación después del año)
            # 3. Si Estatus Examen != 1, NO puede
            # 4. Si intentos >= 3, NO puede
            can_take = False
            if is_approved and not is_expired:
                self.logger.info(f"RFC {rfc}: Ya está APROBADO y vigente, no puede re-tomar examen")
            elif is_approved and is_expired:
                can_take = True
                self.logger.info(f"RFC {rfc}: Aprobado pero EXPIRADO, puede renovar certificación")
            elif estatus_str != "1":
                self.logger.info(f"RFC {rfc}: Estatus Examen = '{estatus_str}' (no es 1), no puede continuar")
            elif intentos >= self.MAX_ATTEMPTS:
                self.logger.info(f"RFC {rfc}: Ya usó {intentos} intentos (máximo {self.MAX_ATTEMPTS})")
            else:
                can_take = True
                self.logger.info(f"RFC {rfc}: Puede hacer examen, intentos={intentos}")

            return {
                "can_take_exam": can_take,
                "attempts_used": intentos,
                "attempts_remaining": max(0, self.MAX_ATTEMPTS - intentos),
                "is_approved": is_approved,
                "is_expired": is_expired,
                "last_attempt_date": fecha_str,
                "section_results": section_results,
                "row_id": row_id,
                "estatus_examen": estatus_str,
                "cert_uuid": cert_uuid_str,
                "expiration_date": vencimiento_str,
                "full_name": data.get(self.COLUMN_NOMBRE_COLABORADOR),
                "email": data.get(self.COLUMN_CORREO_ELECTRONICO)
            }

        except Exception as e:
            self.logger.error(f"Error checking exam status for RFC {rfc}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error checking exam status: {str(e)}")

    async def save_exam_results(
        self,
        rfc: str,
        section_scores: Dict[str, float],
        is_approved: bool,
        answers_results: List[Dict[str, Any]],
        existing_row_id: Optional[int] = None,
        current_attempts: int = 0,
        colaborador_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Guarda los resultados del examen en ambas hojas de Smartsheet.

        Args:
            rfc: RFC del colaborador
            section_scores: Dict con scores de cada sección {"Seccion1": 80, "Seccion2": 90, "Seccion3": 70}
            is_approved: Si aprobó todas las secciones
            answers_results: Lista de 30 dicts con {"question_id": 1, "is_correct": True/False}
            existing_row_id: ID de fila existente en Registros (si ya hay registro)
            current_attempts: Intentos actuales antes de este intento
            colaborador_data: Dict opcional con datos del colaborador:
                - nombre_completo: Nombre del colaborador
                - rfc_empresa: RFC de la empresa
                - nss: NSS del colaborador
                - tipo_servicio: Tipo de servicio
                - proveedor: Proveedor / Empresa
                - email: Correo electrónico

        Returns:
            Dict con row_ids de ambas hojas
        """
        try:
            await self._get_registros_column_maps()
            await self._get_respuestas_column_maps()

            new_attempts = current_attempts + 1
            fecha_hoy = datetime.utcnow().strftime('%Y-%m-%d')
            resultado_str = "Aprobado" if is_approved else "Reprobado"

            # Inicializar colaborador_data si no se proporciona
            if colaborador_data is None:
                colaborador_data = {}

            # 1. ACTUALIZAR O INSERTAR en hoja de Registros
            registros_row_id = None

            if existing_row_id:
                # Actualizar fila existente
                cells = [
                    {"column_id": self._registros_reverse_map[self.COLUMN_FECHA_EXAMEN], "value": fecha_hoy},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION1], "value": section_scores.get("Seccion1", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION2], "value": section_scores.get("Seccion2", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION3], "value": section_scores.get("Seccion3", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_INTENTOS], "value": new_attempts},
                    {"column_id": self._registros_reverse_map[self.COLUMN_RESULTADO], "value": resultado_str},
                ]

                # Actualizar url_imagen si se proporciona
                if colaborador_data.get("url_imagen") and self.COLUMN_URL_IMAGEN in self._registros_reverse_map:
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_URL_IMAGEN],
                        "value": colaborador_data["url_imagen"]
                    })

                row_to_update = smartsheet.models.Row()
                row_to_update.id = existing_row_id
                row_to_update.cells = [smartsheet.models.Cell(cell) for cell in cells]

                response = await asyncio.to_thread(self.client.Sheets.update_rows, self.SHEET_REGISTROS_ID, [row_to_update])
                self._invalidate_sheet_cache(self.SHEET_REGISTROS_ID)
                if response.message == 'SUCCESS':
                    registros_row_id = existing_row_id
                    self.logger.info(f"Updated Registros row {existing_row_id} for RFC {rfc}")
                else:
                    self.logger.error(f"Error updating Registros row: {response.message}")

            else:
                # Insertar nueva fila con datos del colaborador
                cells = [
                    {"column_id": self._registros_reverse_map[self.COLUMN_RFC], "value": rfc.upper()},
                    {"column_id": self._registros_reverse_map[self.COLUMN_FECHA_EXAMEN], "value": fecha_hoy},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION1], "value": section_scores.get("Seccion1", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION2], "value": section_scores.get("Seccion2", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_SECCION3], "value": section_scores.get("Seccion3", 0)},
                    {"column_id": self._registros_reverse_map[self.COLUMN_INTENTOS], "value": new_attempts},
                    {"column_id": self._registros_reverse_map[self.COLUMN_RESULTADO], "value": resultado_str},
                ]

                # Agregar datos del colaborador si están disponibles
                if colaborador_data.get("nombre_completo"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_NOMBRE_COLABORADOR],
                        "value": colaborador_data["nombre_completo"]
                    })

                if colaborador_data.get("rfc_empresa"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_RFC_EMPRESA],
                        "value": colaborador_data["rfc_empresa"]
                    })

                if colaborador_data.get("nss"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_NSS_COLABORADOR],
                        "value": colaborador_data["nss"]
                    })

                if colaborador_data.get("tipo_servicio"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_TIPO_SERVICIO],
                        "value": colaborador_data["tipo_servicio"]
                    })

                if colaborador_data.get("proveedor"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_PROVEEDOR_EMPRESA],
                        "value": colaborador_data["proveedor"]
                    })

                if colaborador_data.get("email"):
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_CORREO_ELECTRONICO],
                        "value": colaborador_data["email"]
                    })

                # URL de imagen de credencial
                if colaborador_data.get("url_imagen") and self.COLUMN_URL_IMAGEN in self._registros_reverse_map:
                    cells.append({
                        "column_id": self._registros_reverse_map[self.COLUMN_URL_IMAGEN],
                        "value": colaborador_data["url_imagen"]
                    })

                new_row = smartsheet.models.Row()
                new_row.to_bottom = True
                new_row.cells = [smartsheet.models.Cell(cell) for cell in cells]

                response = await asyncio.to_thread(self.client.Sheets.add_rows, self.SHEET_REGISTROS_ID, [new_row])
                self._invalidate_sheet_cache(self.SHEET_REGISTROS_ID)
                if response.message == 'SUCCESS' and response.result:
                    registros_row_id = response.result[0].id
                    self.logger.info(f"Inserted new Registros row {registros_row_id} for RFC {rfc}")
                else:
                    self.logger.error(f"Error inserting Registros row: {response.message}")

            # 2. INSERTAR en hoja de Respuestas (Bitácora)
            # Guardar cada respuesta como Correcto/Incorrecto
            respuestas_cells = []
            
            # Verificar y agregar columnas si existen
            if self.COLUMN_RESP_RFC in self._respuestas_reverse_map:
                respuestas_cells.append({
                    "column_id": self._respuestas_reverse_map[self.COLUMN_RESP_RFC], 
                    "value": rfc.upper()
                })
            else:
                self.logger.warning(f"Column '{self.COLUMN_RESP_RFC}' not found in Respuestas sheet. Available: {list(self._respuestas_reverse_map.keys())[:10]}")
            
            if self.COLUMN_RESP_FECHA in self._respuestas_reverse_map:
                respuestas_cells.append({
                    "column_id": self._respuestas_reverse_map[self.COLUMN_RESP_FECHA], 
                    "value": fecha_hoy
                })
            else:
                self.logger.warning(f"Column '{self.COLUMN_RESP_FECHA}' not found in Respuestas sheet")

            # Agregar resultados de cada respuesta (R1 a R30)
            for answer in answers_results:
                q_id = answer.get("question_id")
                is_correct = answer.get("is_correct", False)
                col_name = f"R{q_id}"

                if col_name in self._respuestas_reverse_map:
                    respuestas_cells.append({
                        "column_id": self._respuestas_reverse_map[col_name],
                        "value": "Correcto" if is_correct else "Incorrecto"
                    })

            new_respuesta_row = smartsheet.models.Row()
            new_respuesta_row.to_bottom = True
            new_respuesta_row.cells = [smartsheet.models.Cell(cell) for cell in respuestas_cells]

            respuestas_response = await asyncio.to_thread(self.client.Sheets.add_rows, self.SHEET_RESPUESTAS_ID, [new_respuesta_row])
            self._invalidate_sheet_cache(self.SHEET_RESPUESTAS_ID)
            respuestas_row_id = None
            if respuestas_response.message == 'SUCCESS' and respuestas_response.result:
                respuestas_row_id = respuestas_response.result[0].id
                self.logger.info(f"Inserted Respuestas row {respuestas_row_id} for RFC {rfc}")

            return {
                "registros_row_id": registros_row_id,
                "respuestas_row_id": respuestas_row_id,
                "new_attempts": new_attempts,
                "resultado": resultado_str
            }

        except Exception as e:
            self.logger.error(f"Error saving exam results for RFC {rfc}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error saving exam results: {str(e)}")

    async def update_certificate_data(
        self,
        row_id: int,
        cert_uuid: str,
        expiration_date: datetime
    ) -> bool:
        """
        Actualiza una fila de la hoja de Registros con los datos del certificado generado.

        Args:
            row_id: ID de la fila a actualizar
            cert_uuid: UUID del certificado generado
            expiration_date: Fecha de vencimiento del certificado

        Returns:
            True si la actualización fue exitosa
        """
        try:
            await self._get_registros_column_maps()

            # Formatear fecha de vencimiento
            vencimiento_str = expiration_date.strftime('%Y-%m-%d')

            # Construir las celdas a actualizar
            # NOTA: COLUMN_ENVIO_CERT tiene formula en Smartsheet y se calcula automaticamente
            cells = [
                {
                    "column_id": self._registros_reverse_map[self.COLUMN_UUID],
                    "value": cert_uuid
                },
                {
                    "column_id": self._registros_reverse_map[self.COLUMN_VENCIMIENTO],
                    "value": vencimiento_str
                }
            ]

            # Crear objeto de fila para actualización
            row_to_update = smartsheet.models.Row()
            row_to_update.id = row_id
            row_to_update.cells = [smartsheet.models.Cell(cell) for cell in cells]

            # Ejecutar actualización
            response = await asyncio.to_thread(self.client.Sheets.update_rows, self.SHEET_REGISTROS_ID, [row_to_update])
            self._invalidate_sheet_cache(self.SHEET_REGISTROS_ID)

            if response.message == 'SUCCESS':
                self.logger.info(
                    f"Successfully updated row {row_id} with certificate UUID={cert_uuid}, "
                    f"Vencimiento={vencimiento_str}"
                )
                return True
            else:
                self.logger.error(f"Unexpected response updating certificate data: {response.message}")
                return False

        except KeyError as e:
            self.logger.error(f"Column not found in Registros sheet: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Column not found: {str(e)}")
        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error updating certificate data: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Smartsheet API error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error updating certificate data for row {row_id}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error updating certificate data: {str(e)}")

    async def get_credential_data_by_rfc(self, rfc: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos necesarios para generar una credencial virtual por RFC.

        Args:
            rfc: RFC del colaborador

        Returns:
            Diccionario con datos de credencial o None si no existe:
            - full_name: Nombre del colaborador
            - proveedor: Proveedor / Empresa
            - tipo_servicio: Tipo de servicio
            - nss: NSS del colaborador
            - email: Correo electrónico
            - cert_uuid: UUID del certificado
            - vencimiento: Fecha de vencimiento
            - fecha_emision: Fecha del examen
            - is_approved: Si está aprobado
            - is_expired: Si el certificado expiró
        """
        try:
            await self._get_registros_column_maps()

            sheet = await self._get_cached_sheet(self.SHEET_REGISTROS_ID)
            rfc_upper = rfc.strip().upper()

            # Buscar registro existente con este RFC
            for row in sheet.rows:
                row_data = {}
                for cell in row.cells:
                    col_name = self._registros_column_map.get(cell.column_id, "")
                    row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

                row_rfc = str(row_data.get(self.COLUMN_RFC, "")).strip().upper()
                if row_rfc == rfc_upper:
                    # Verificar si está aprobado
                    resultado = str(row_data.get(self.COLUMN_RESULTADO, "")).strip().lower()
                    is_approved = resultado == "aprobado"

                    # Obtener fecha de vencimiento y verificar expiración
                    vencimiento = row_data.get(self.COLUMN_VENCIMIENTO)
                    vencimiento_str = str(vencimiento) if vencimiento else None

                    is_expired = False
                    if is_approved and vencimiento_str:
                        for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%d/%m/%y']:
                            try:
                                expiration_date = datetime.strptime(str(vencimiento_str), date_format)
                                if expiration_date.year < 100:
                                    expiration_date = expiration_date.replace(year=expiration_date.year + 2000)
                                is_expired = expiration_date.date() < datetime.utcnow().date()
                                break
                            except ValueError:
                                continue

                    return {
                        "full_name": row_data.get(self.COLUMN_NOMBRE_COLABORADOR),
                        "proveedor": row_data.get(self.COLUMN_PROVEEDOR_EMPRESA),
                        "tipo_servicio": row_data.get(self.COLUMN_TIPO_SERVICIO),
                        "nss": row_data.get(self.COLUMN_NSS_COLABORADOR),
                        "rfc_empresa": row_data.get(self.COLUMN_RFC_EMPRESA),
                        "email": row_data.get(self.COLUMN_CORREO_ELECTRONICO),
                        "cert_uuid": row_data.get(self.COLUMN_UUID),
                        "vencimiento": vencimiento_str,
                        "fecha_emision": row_data.get(self.COLUMN_FECHA_EXAMEN),
                        "url_imagen": row_data.get(self.COLUMN_URL_IMAGEN),
                        "is_approved": is_approved,
                        "is_expired": is_expired,
                        # Scores de sección (para evitar llamada redundante a check_exam_status)
                        "section_results": {
                            "Seccion1": row_data.get(self.COLUMN_SECCION1),
                            "Seccion2": row_data.get(self.COLUMN_SECCION2),
                            "Seccion3": row_data.get(self.COLUMN_SECCION3),
                        },
                    }

            return None

        except Exception as e:
            self.logger.error(f"Error getting credential data for RFC {rfc}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error getting credential data: {str(e)}")

    async def get_collaborator_by_rfc_and_nss(self, rfc: str, nss: str) -> Optional[Dict[str, Any]]:
        """
        Busca un colaborador por RFC y valida que el NSS coincida (doble verificación de identidad).

        Args:
            rfc: RFC del colaborador
            nss: NSS del colaborador para verificación

        Returns:
            Diccionario con datos del colaborador o None si no existe o NSS no coincide
        """
        try:
            await self._get_registros_column_maps()

            sheet = await self._get_cached_sheet(self.SHEET_REGISTROS_ID)
            rfc_upper = rfc.strip().upper()
            nss_clean = nss.strip()

            for row in sheet.rows:
                row_data = {}
                for cell in row.cells:
                    col_name = self._registros_column_map.get(cell.column_id, "")
                    row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

                row_rfc = str(row_data.get(self.COLUMN_RFC, "")).strip().upper()
                if row_rfc == rfc_upper:
                    # Validar que el NSS coincida
                    row_nss = str(row_data.get(self.COLUMN_NSS_COLABORADOR, "")).strip()
                    if row_nss != nss_clean:
                        self.logger.warning(f"RFC {rfc} encontrado pero NSS no coincide")
                        return None

                    # NSS coincide, retornar datos completos
                    resultado = str(row_data.get(self.COLUMN_RESULTADO, "")).strip().lower()
                    is_approved = resultado == "aprobado"

                    return {
                        "row_id": row.id,
                        "full_name": row_data.get(self.COLUMN_NOMBRE_COLABORADOR),
                        "email": row_data.get(self.COLUMN_CORREO_ELECTRONICO),
                        "rfc": row_rfc,
                        "nss": row_nss,
                        "proveedor": row_data.get(self.COLUMN_PROVEEDOR_EMPRESA),
                        "tipo_servicio": row_data.get(self.COLUMN_TIPO_SERVICIO),
                        "rfc_empresa": row_data.get(self.COLUMN_RFC_EMPRESA),
                        "url_imagen": row_data.get(self.COLUMN_URL_IMAGEN),
                        "cert_uuid": row_data.get(self.COLUMN_UUID),
                        "vencimiento": row_data.get(self.COLUMN_VENCIMIENTO),
                        "fecha_examen": row_data.get(self.COLUMN_FECHA_EXAMEN),
                        "resultado": row_data.get(self.COLUMN_RESULTADO),
                        "is_approved": is_approved,
                        "seccion1": row_data.get(self.COLUMN_SECCION1),
                        "seccion2": row_data.get(self.COLUMN_SECCION2),
                        "seccion3": row_data.get(self.COLUMN_SECCION3),
                    }

            self.logger.info(f"RFC {rfc} no encontrado en registros")
            return None

        except Exception as e:
            self.logger.error(f"Error getting collaborator by RFC and NSS: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error getting collaborator: {str(e)}")

    async def lookup_by_nss_email(self, nss: str, email: str) -> Optional[Dict[str, Any]]:
        """
        Busca un colaborador por NSS y correo electronico.
        Retorna el RFC completo (con homoclave) si encuentra un registro que coincida.

        Args:
            nss: NSS del colaborador (11 digitos).
            email: Correo electronico del colaborador.

        Returns:
            Diccionario con rfc encontrado o None si no existe.
        """
        try:
            await self._get_registros_column_maps()

            sheet = await self._get_cached_sheet(self.SHEET_REGISTROS_ID)
            nss_clean = nss.strip()
            email_clean = email.strip().lower()

            for row in sheet.rows:
                row_data = {}
                for cell in row.cells:
                    col_name = self._registros_column_map.get(cell.column_id, "")
                    row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

                row_nss = str(row_data.get(self.COLUMN_NSS_COLABORADOR, "")).strip()
                row_email = str(row_data.get(self.COLUMN_CORREO_ELECTRONICO, "")).strip().lower()

                if row_nss == nss_clean and row_email == email_clean:
                    rfc_found = str(row_data.get(self.COLUMN_RFC, "")).strip().upper()
                    self.logger.info(f"Registro encontrado por NSS+email: RFC={rfc_found[:4]}****")
                    return {
                        "found": True,
                        "rfc": rfc_found,
                        "full_name": row_data.get(self.COLUMN_NOMBRE_COLABORADOR),
                    }

            self.logger.info(f"No se encontro registro con NSS={nss_clean} y email={email_clean}")
            return None

        except Exception as e:
            self.logger.error(f"Error en lookup_by_nss_email: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error buscando registro: {str(e)}")

    async def get_all_registros(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los registros de la hoja de Registros_OnBoarding.

        Returns:
            Lista de diccionarios con todos los registros
        """
        try:
            await self._get_registros_column_maps()

            sheet = await self._get_cached_sheet(self.SHEET_REGISTROS_ID)
            registros = []

            for row in sheet.rows:
                row_data = {"row_id": row.id}
                for cell in row.cells:
                    col_name = self._registros_column_map.get(cell.column_id, f"Col_{cell.column_id}")
                    row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

                registros.append(row_data)

            self.logger.info(f"Retrieved {len(registros)} registros from Smartsheet")
            return registros

        except Exception as e:
            self.logger.error(f"Error getting all registros: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error getting registros: {str(e)}")

    async def get_row_data_by_id(self, row_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos de una fila especifica de la hoja de Registros por su row_id.
        Mas eficiente que leer toda la hoja cuando solo se necesita una fila.

        Args:
            row_id: ID de la fila en Smartsheet

        Returns:
            Diccionario con los datos de la fila o None si ocurre un error
        """
        try:
            await self._get_registros_column_maps()

            row = await asyncio.to_thread(self.client.Sheets.get_row, self.SHEET_REGISTROS_ID, row_id)

            row_data = {"row_id": row.id}
            for cell in row.cells:
                col_name = self._registros_column_map.get(cell.column_id, f"Col_{cell.column_id}")
                row_data[col_name] = cell.display_value if cell.display_value is not None else cell.value

            self.logger.info(f"Retrieved row {row_id} from Registros sheet")
            return row_data

        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error getting row {row_id}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting row {row_id}: {str(e)}")
            return None

    def get_correo_electronico_column_id(self) -> Optional[int]:
        """
        Retorna el column ID de la columna 'Correo Electronico' en la hoja de Registros.
        Requiere que _get_registros_column_maps() haya sido llamado previamente.

        Returns:
            ID de la columna o None si no se encuentra
        """
        return self._registros_reverse_map.get(self.COLUMN_CORREO_ELECTRONICO)

    def get_reenviar_correo_column_id(self) -> Optional[int]:
        """
        Retorna el column ID de la columna 'Reenviar correo' en la hoja de Registros.
        Requiere que _get_registros_column_maps() haya sido llamado previamente.
        """
        return self._registros_reverse_map.get(self.COLUMN_REENVIAR_CORREO)

    async def uncheck_reenviar_correo(self, row_id: int) -> bool:
        """
        Desmarca la casilla 'Reenviar correo' de una fila (la pone en false).

        Args:
            row_id: ID de la fila en Smartsheet

        Returns:
            True si la actualizacion fue exitosa
        """
        try:
            await self._get_registros_column_maps()

            col_id = self._registros_reverse_map.get(self.COLUMN_REENVIAR_CORREO)
            if not col_id:
                self.logger.error("Column 'Reenviar correo' not found in sheet")
                return False

            cell = smartsheet.models.Cell()
            cell.column_id = col_id
            cell.value = False

            row_to_update = smartsheet.models.Row()
            row_to_update.id = row_id
            row_to_update.cells = [cell]

            response = await asyncio.to_thread(self.client.Sheets.update_rows, self.SHEET_REGISTROS_ID, [row_to_update])
            self._invalidate_sheet_cache(self.SHEET_REGISTROS_ID)

            if response.message == 'SUCCESS':
                self.logger.info(f"Unchecked 'Reenviar correo' for row {row_id}")
                return True
            else:
                self.logger.error(f"Error unchecking 'Reenviar correo': {response.message}")
                return False

        except Exception as e:
            self.logger.error(f"Error unchecking 'Reenviar correo' for row {row_id}: {str(e)}")
            return False

    async def update_collaborator_profile(self, row_id: int, fields: Dict[str, Any]) -> bool:
        """
        Actualiza columnas editables del perfil de un colaborador en la hoja de Registros.

        Args:
            row_id: ID de la fila en Smartsheet
            fields: Diccionario con campos a actualizar. Claves válidas:
                - nombre: Nombre Colaborador
                - rfc_colaborador: RFC del Colaborador
                - rfc_empresa: RFC de la Empresa
                - email: Correo Electrónico
                - nss: NSS del Colaborador
                - proveedor: Proveedor / Empresa
                - tipo_servicio: Tipo de Servicio
                - url_imagen: url_imagen

        Returns:
            True si la actualización fue exitosa
        """
        # Mapeo de campos del request a nombres de columnas en Smartsheet
        field_to_column = {
            "nombre": self.COLUMN_NOMBRE_COLABORADOR,
            "rfc_colaborador": self.COLUMN_RFC_COLABORADOR,
            "rfc_empresa": self.COLUMN_RFC_EMPRESA,
            "email": self.COLUMN_CORREO_ELECTRONICO,
            "nss": self.COLUMN_NSS_COLABORADOR,
            "proveedor": self.COLUMN_PROVEEDOR_EMPRESA,
            "tipo_servicio": self.COLUMN_TIPO_SERVICIO,
            "url_imagen": self.COLUMN_URL_IMAGEN,
        }

        try:
            await self._get_registros_column_maps()

            cells = []
            for field_key, value in fields.items():
                column_name = field_to_column.get(field_key)
                if not column_name:
                    self.logger.warning(f"Unknown field '{field_key}' skipped in profile update")
                    continue

                col_id = self._registros_reverse_map.get(column_name)
                if not col_id:
                    self.logger.warning(f"Column '{column_name}' not found in sheet, skipping")
                    continue

                cells.append({
                    "column_id": col_id,
                    "value": value
                })

            if not cells:
                self.logger.warning(f"No valid fields to update for row {row_id}")
                return False

            row_to_update = smartsheet.models.Row()
            row_to_update.id = row_id
            row_to_update.cells = [smartsheet.models.Cell(cell) for cell in cells]

            response = await asyncio.to_thread(self.client.Sheets.update_rows, self.SHEET_REGISTROS_ID, [row_to_update])
            self._invalidate_sheet_cache(self.SHEET_REGISTROS_ID)

            if response.message == 'SUCCESS':
                self.logger.info(f"Successfully updated profile for row {row_id}, fields: {list(fields.keys())}")
                return True
            else:
                self.logger.error(f"Unexpected response updating profile: {response.message}")
                return False

        except KeyError as e:
            self.logger.error(f"Column not found updating profile for row {row_id}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Column not found: {str(e)}")
        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error updating profile for row {row_id}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Smartsheet API error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error updating profile for row {row_id}: {str(e)}")
            raise OnboardingSmartsheetServiceError(f"Error updating profile: {str(e)}")


# Singleton — reusar en todos los endpoints
_onboarding_service_instance: Optional[OnboardingSmartsheetService] = None


def get_onboarding_service_singleton() -> OnboardingSmartsheetService:
    global _onboarding_service_instance
    if _onboarding_service_instance is None:
        _onboarding_service_instance = OnboardingSmartsheetService()
    return _onboarding_service_instance
