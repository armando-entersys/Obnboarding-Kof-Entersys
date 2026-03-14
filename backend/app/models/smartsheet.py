from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime


class SmartsheetCell(BaseModel):
    """Representa una celda en una hoja de Smartsheet"""
    column_id: Optional[int] = None
    column_name: Optional[str] = None
    display_value: Optional[str] = None
    value: Optional[Union[str, int, float, bool, datetime]] = None


class SmartsheetAttachment(BaseModel):
    """Representa un adjunto en Smartsheet"""
    id: int
    name: str
    url: Optional[str] = None
    attachment_type: Optional[str] = None
    mime_type: Optional[str] = None
    size_in_kb: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class SmartsheetRow(BaseModel):
    """Representa una fila en una hoja de Smartsheet"""
    id: int
    row_number: int
    cells: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[SmartsheetAttachment] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None


class SmartsheetColumn(BaseModel):
    """Representa una columna en una hoja de Smartsheet"""
    id: int
    index: int
    title: str
    type: str
    primary: Optional[bool] = False
    hidden: Optional[bool] = False
    locked: Optional[bool] = False


class SmartsheetSheet(BaseModel):
    """Representa información básica de una hoja de Smartsheet"""
    id: int
    name: str
    permalink: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    total_row_count: Optional[int] = None


class SmartsheetRowsResponse(BaseModel):
    """Respuesta del endpoint de filas de Smartsheet"""
    success: bool = True
    data: "SmartsheetRowsData"
    filters_applied: Optional[str] = None
    execution_time_ms: int = 0


class SmartsheetRowsData(BaseModel):
    """Datos de respuesta de filas de Smartsheet"""
    sheet_id: int
    total_rows: int
    returned_rows: int
    offset: int
    limit: int
    rows: List[SmartsheetRow]


class SmartsheetErrorResponse(BaseModel):
    """Respuesta de error de Smartsheet"""
    success: bool = False
    error: str
    error_code: Optional[str] = None
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class QueryFilter(BaseModel):
    """Representa un filtro para consultas dinámicas"""
    column: str
    operator: str
    value: str

    @validator('operator')
    def validate_operator(cls, v):
        allowed_operators = [
            'equals', 'iequals', 'contains', 'icontains',
            'not_equals', 'is_empty', 'not_empty',
            'greater_than', 'less_than'
        ]
        if v not in allowed_operators:
            raise ValueError(f'Operator must be one of: {", ".join(allowed_operators)}')
        return v


class QueryCondition(BaseModel):
    """Representa una condición completa de consulta con filtros y operadores lógicos"""
    filters: List[QueryFilter]
    logical_operators: List[str] = Field(default_factory=list)

    @validator('logical_operators')
    def validate_logical_operators(cls, v):
        allowed_ops = ['AND', 'OR']
        for op in v:
            if op not in allowed_ops:
                raise ValueError(f'Logical operator must be one of: {", ".join(allowed_ops)}')
        return v

    @validator('logical_operators', always=True)
    def validate_operators_count(cls, v, values):
        filters = values.get('filters', [])
        if len(filters) > 1 and len(v) != len(filters) - 1:
            raise ValueError('Number of logical operators must be one less than number of filters')
        return v


# Actualizar las referencias hacia adelante
SmartsheetRowsResponse.model_rebuild()