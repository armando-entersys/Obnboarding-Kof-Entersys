import asyncio
import smartsheet
import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from app.core.config import settings
from app.models.smartsheet import (
    SmartsheetRow, SmartsheetRowsData, SmartsheetRowsResponse,
    SmartsheetErrorResponse, SmartsheetAttachment, SmartsheetColumn
)
from app.utils.query_parser import SmartsheetQueryParser, QueryParserError


class SmartsheetServiceError(Exception):
    """Excepción personalizada para errores del servicio de Smartsheet"""
    pass


class SmartsheetService:
    """
    Servicio para interactuar con la API de Smartsheet
    Maneja la obtención de datos, filtrado y paginación
    """

    def __init__(self):
        """Inicializa el servicio de Smartsheet"""
        self.logger = logging.getLogger(__name__)
        self.query_parser = SmartsheetQueryParser()

        try:
            # Inicializar el cliente de Smartsheet
            self.client = smartsheet.Smartsheet(settings.SMARTSHEET_ACCESS_TOKEN)
            self.client.errors_as_exceptions(True)
            self.logger.info("Smartsheet client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Smartsheet client: {str(e)}")
            raise SmartsheetServiceError(f"Error initializing Smartsheet client: {str(e)}")

    async def get_sheet_rows(
        self,
        sheet_id: int,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[str] = None,
        include_attachments: bool = False,
        query_string: Optional[str] = None
    ) -> Union[SmartsheetRowsResponse, SmartsheetErrorResponse]:
        """
        Obtiene las filas de una hoja de Smartsheet con filtrado y paginación

        Args:
            sheet_id: ID de la hoja de Smartsheet
            limit: Número máximo de filas a retornar
            offset: Offset para paginación
            fields: Columnas específicas a incluir (separadas por comas)
            include_attachments: Si incluir información de adjuntos
            query_string: Cadena de filtrado dinámico

        Returns:
            SmartsheetRowsResponse o SmartsheetErrorResponse
        """
        start_time = time.time()

        try:
            self.logger.info(f"Getting rows from sheet {sheet_id} with limit={limit}, offset={offset}")

            # Obtener la hoja completa con todas las filas
            sheet = await self._get_sheet_data(sheet_id, include_attachments)

            if not sheet:
                return SmartsheetErrorResponse(
                    error="SHEET_NOT_FOUND",
                    message=f"Sheet with ID {sheet_id} not found"
                )

            # Convertir filas a formato de respuesta
            converted_rows = self._convert_sheet_rows(sheet, include_attachments)

            # Aplicar filtros si se proporcionaron
            if query_string:
                try:
                    condition = self.query_parser.parse_query_string(query_string)
                    converted_rows = self.query_parser.apply_filters(converted_rows, condition)
                    self.logger.info(f"Applied filters: {query_string}, remaining rows: {len(converted_rows)}")
                except QueryParserError as e:
                    return SmartsheetErrorResponse(
                        error="INVALID_QUERY",
                        message=f"Invalid query syntax: {str(e)}"
                    )

            # Aplicar selección de campos si se especificaron
            if fields:
                field_list = [field.strip() for field in fields.split(',')]
                converted_rows = self._filter_fields(converted_rows, field_list)

            # Aplicar paginación
            total_rows = len(converted_rows)
            paginated_rows = converted_rows[offset:offset + limit]

            # Convertir a objetos SmartsheetRow
            smartsheet_rows = []
            for row_data in paginated_rows:
                smartsheet_rows.append(SmartsheetRow(**row_data))

            # Crear respuesta
            execution_time = int((time.time() - start_time) * 1000)

            response_data = SmartsheetRowsData(
                sheet_id=sheet_id,
                total_rows=total_rows,
                returned_rows=len(smartsheet_rows),
                offset=offset,
                limit=limit,
                rows=smartsheet_rows
            )

            response = SmartsheetRowsResponse(
                success=True,
                data=response_data,
                filters_applied=query_string,
                execution_time_ms=execution_time
            )

            self.logger.info(
                f"Successfully retrieved {len(smartsheet_rows)} rows from sheet {sheet_id} "
                f"in {execution_time}ms"
            )

            return response

        except smartsheet.exceptions.ApiError as e:
            self.logger.error(f"Smartsheet API error: {str(e)}")
            return SmartsheetErrorResponse(
                error="SMARTSHEET_API_ERROR",
                error_code=str(e.error.result.code) if hasattr(e.error, 'result') else None,
                message=f"Smartsheet API error: {str(e)}"
            )

        except Exception as e:
            self.logger.error(f"Unexpected error getting sheet rows: {str(e)}")
            return SmartsheetErrorResponse(
                error="INTERNAL_ERROR",
                message=f"Internal server error: {str(e)}"
            )

    async def _get_sheet_data(self, sheet_id: int, include_attachments: bool) -> Optional[Any]:
        """
        Obtiene los datos de la hoja desde la API de Smartsheet

        Args:
            sheet_id: ID de la hoja
            include_attachments: Si incluir adjuntos

        Returns:
            Objeto sheet de Smartsheet o None si no existe
        """
        try:
            include_params = ['format', 'objectValue']

            if include_attachments:
                include_params.extend(['attachments', 'discussions'])

            sheet = await asyncio.to_thread(
                self.client.Sheets.get_sheet,
                sheet_id,
                include=include_params
            )

            self.logger.debug(f"Retrieved sheet with {len(sheet.rows)} rows and {len(sheet.columns)} columns")
            return sheet

        except smartsheet.exceptions.ApiError as e:
            if e.error.result.code == 1006:  # NOT_FOUND
                self.logger.warning(f"Sheet {sheet_id} not found")
                return None
            else:
                raise

    def _convert_sheet_rows(self, sheet: Any, include_attachments: bool) -> List[Dict[str, Any]]:
        """
        Convierte las filas de Smartsheet al formato de respuesta

        Args:
            sheet: Objeto sheet de Smartsheet
            include_attachments: Si incluir información de adjuntos

        Returns:
            Lista de diccionarios con datos de filas
        """
        converted_rows = []

        # Crear mapeo de ID de columna a nombre
        column_map = {}
        for column in sheet.columns:
            column_map[column.id] = column.title

        for row in sheet.rows:
            row_data = {
                'id': row.id,
                'row_number': row.row_number,
                'cells': {},
                'attachments': [],
                'created_at': row.created_at,
                'modified_at': row.modified_at,
                'created_by': getattr(row.created_by, 'name', None) if hasattr(row, 'created_by') and row.created_by else None,
                'modified_by': getattr(row.modified_by, 'name', None) if hasattr(row, 'modified_by') and row.modified_by else None
            }

            # Procesar celdas
            for cell in row.cells:
                column_name = column_map.get(cell.column_id, f"Column_{cell.column_id}")

                # Usar display_value si está disponible, sino usar value
                cell_value = cell.display_value if cell.display_value is not None else cell.value

                row_data['cells'][column_name] = cell_value

            # Procesar adjuntos si están incluidos
            if include_attachments and hasattr(row, 'attachments') and row.attachments:
                for attachment in row.attachments:
                    attachment_data = {
                        'id': attachment.id,
                        'name': attachment.name,
                        'url': attachment.url if hasattr(attachment, 'url') else None,
                        'attachment_type': attachment.attachment_type if hasattr(attachment, 'attachment_type') else None,
                        'mime_type': attachment.mime_type if hasattr(attachment, 'mime_type') else None,
                        'size_in_kb': attachment.size_in_kb if hasattr(attachment, 'size_in_kb') else None,
                        'created_at': attachment.created_at if hasattr(attachment, 'created_at') else None,
                        'created_by': getattr(attachment.created_by, 'name', None) if hasattr(attachment, 'created_by') and attachment.created_by else None
                    }
                    row_data['attachments'].append(attachment_data)

            converted_rows.append(row_data)

        return converted_rows

    def _filter_fields(self, rows: List[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
        """
        Filtra las columnas de las filas según los campos especificados

        Args:
            rows: Lista de filas
            fields: Lista de nombres de campos a incluir

        Returns:
            Lista de filas con solo los campos especificados
        """
        filtered_rows = []

        for row in rows:
            filtered_row = {
                'id': row['id'],
                'row_number': row['row_number'],
                'cells': {},
                'attachments': row['attachments'],
                'created_at': row['created_at'],
                'modified_at': row['modified_at'],
                'created_by': row['created_by'],
                'modified_by': row['modified_by']
            }

            # Incluir solo los campos solicitados
            for field in fields:
                if field in row['cells']:
                    filtered_row['cells'][field] = row['cells'][field]

            filtered_rows.append(filtered_row)

        return filtered_rows

    async def get_sheet_columns(self, sheet_id: int) -> List[SmartsheetColumn]:
        """
        Obtiene información sobre las columnas de una hoja

        Args:
            sheet_id: ID de la hoja

        Returns:
            Lista de columnas de la hoja
        """
        try:
            sheet = await asyncio.to_thread(self.client.Sheets.get_sheet, sheet_id, include=['format'])
            columns = []

            for column in sheet.columns:
                column_data = SmartsheetColumn(
                    id=column.id,
                    index=column.index,
                    title=column.title,
                    type=str(column.type),  # Convert EnumeratedValue to string
                    primary=getattr(column, 'primary', False),
                    hidden=getattr(column, 'hidden', False),
                    locked=getattr(column, 'locked', False)
                )
                columns.append(column_data)

            return columns

        except Exception as e:
            self.logger.error(f"Error getting sheet columns: {str(e)}")
            raise SmartsheetServiceError(f"Error getting sheet columns: {str(e)}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica que el servicio de Smartsheet esté funcionando correctamente

        Returns:
            Diccionario con el estado del servicio
        """
        try:
            # Intentar obtener información del usuario actual
            user_info = await asyncio.to_thread(self.client.Users.get_current_user)

            return {
                "status": "healthy",
                "user": user_info.email if hasattr(user_info, 'email') else "unknown",
                "api_base_url": settings.SMARTSHEET_API_BASE_URL,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Smartsheet health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Singleton
_smartsheet_service_instance: Optional[SmartsheetService] = None


def get_smartsheet_service_singleton() -> SmartsheetService:
    global _smartsheet_service_instance
    if _smartsheet_service_instance is None:
        _smartsheet_service_instance = SmartsheetService()
    return _smartsheet_service_instance