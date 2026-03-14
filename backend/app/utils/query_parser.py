from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import re
import logging
from app.models.smartsheet import QueryFilter, QueryCondition

logger = logging.getLogger(__name__)


class QueryParserError(Exception):
    """Excepción personalizada para errores del parser de consultas"""
    pass


class SmartsheetQueryParser:
    """
    Parser para consultas dinámicas de Smartsheet con sintaxis:
    [nombre_columna]:[operador]:[valor]

    Operadores soportados:
    - equals: Coincidencia exacta (sensible a mayúsculas)
    - iequals: Coincidencia exacta (insensible a mayúsculas)
    - contains: Contiene el texto
    - icontains: Contiene el texto (insensible a mayúsculas)
    - not_equals: No es igual a
    - is_empty: Celda vacía
    - not_empty: Celda no vacía
    - greater_than: Mayor que (números/fechas)
    - less_than: Menor que (números/fechas)
    """

    SUPPORTED_OPERATORS = [
        'equals', 'iequals', 'contains', 'icontains',
        'not_equals', 'is_empty', 'not_empty',
        'greater_than', 'less_than'
    ]

    LOGICAL_OPERATORS = ['AND', 'OR']

    def __init__(self):
        """Inicializa el parser de consultas"""
        self.logger = logger

    def parse_query_string(self, query_string: str) -> QueryCondition:
        """
        Parsea una cadena de consulta y retorna un objeto QueryCondition

        Args:
            query_string: Cadena de consulta en formato definido

        Returns:
            QueryCondition: Objeto con filtros y operadores lógicos parseados

        Raises:
            QueryParserError: Si la consulta tiene formato inválido
        """
        if not query_string or not query_string.strip():
            return QueryCondition(filters=[], logical_operators=[])

        try:
            # Dividir la consulta en componentes
            components = self._split_query_components(query_string)

            # Separar filtros y operadores lógicos
            filters = []
            logical_operators = []

            for i, component in enumerate(components):
                if i % 2 == 0:  # Componentes pares son filtros
                    filter_obj = self._parse_filter_component(component)
                    filters.append(filter_obj)
                else:  # Componentes impares son operadores lógicos
                    logical_op = component.strip().upper()
                    if logical_op not in self.LOGICAL_OPERATORS:
                        raise QueryParserError(f"Operador lógico inválido: {logical_op}")
                    logical_operators.append(logical_op)

            # Validar que el número de operadores sea correcto
            if len(filters) > 1 and len(logical_operators) != len(filters) - 1:
                raise QueryParserError(
                    f"Número incorrecto de operadores lógicos. "
                    f"Se esperaban {len(filters) - 1}, se encontraron {len(logical_operators)}"
                )

            return QueryCondition(filters=filters, logical_operators=logical_operators)

        except Exception as e:
            self.logger.error(f"Error parsing query string '{query_string}': {str(e)}")
            raise QueryParserError(f"Error en el formato de la consulta: {str(e)}")

    def _split_query_components(self, query_string: str) -> List[str]:
        """
        Divide la cadena de consulta en componentes individuales
        Maneja comas que pueden estar dentro de valores
        """
        components = []
        current_component = ""
        in_quotes = False

        i = 0
        while i < len(query_string):
            char = query_string[i]

            if char == '"' and (i == 0 or query_string[i-1] != '\\'):
                in_quotes = not in_quotes
                current_component += char
            elif char == ',' and not in_quotes:
                # Verificar si es el separador de un operador lógico
                remaining = query_string[i+1:].strip()
                logical_op_match = re.match(r'^(AND|OR)\s*,', remaining, re.IGNORECASE)

                if logical_op_match:
                    # Es un operador lógico
                    components.append(current_component.strip())
                    i += 1  # Saltar la coma
                    # Agregar el operador lógico
                    op_end = logical_op_match.end() - 1  # -1 para no incluir la coma final
                    components.append(query_string[i:i+op_end].strip())
                    i += op_end
                    current_component = ""
                else:
                    # Es una coma normal dentro del valor
                    current_component += char
            else:
                current_component += char

            i += 1

        if current_component.strip():
            components.append(current_component.strip())

        return components

    def _parse_filter_component(self, component: str) -> QueryFilter:
        """
        Parsea un componente individual de filtro
        Formato: [columna]:[operador]:[valor]
        """
        # Usar regex para dividir respetando los dos puntos escapados
        parts = re.split(r'(?<!\\):', component, maxsplit=2)

        if len(parts) < 2:
            raise QueryParserError(f"Formato de filtro inválido: {component}")

        column = parts[0].strip()
        operator = parts[1].strip().lower()
        value = parts[2].strip() if len(parts) > 2 else ""

        # Limpiar comillas si existen
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        # Desescapar caracteres especiales
        value = value.replace('\\:', ':').replace('\\"', '"')

        if not column:
            raise QueryParserError("El nombre de la columna no puede estar vacío")

        if operator not in self.SUPPORTED_OPERATORS:
            raise QueryParserError(f"Operador no soportado: {operator}")

        # Validar que operadores que requieren valor lo tengan
        if operator not in ['is_empty', 'not_empty'] and not value:
            raise QueryParserError(f"El operador '{operator}' requiere un valor")

        return QueryFilter(column=column, operator=operator, value=value)

    def apply_filters(self, rows: List[Dict[str, Any]], condition: QueryCondition) -> List[Dict[str, Any]]:
        """
        Aplica los filtros a una lista de filas

        Args:
            rows: Lista de filas a filtrar
            condition: Condición con filtros y operadores lógicos

        Returns:
            List[Dict]: Lista filtrada de filas
        """
        if not condition.filters:
            return rows

        filtered_rows = []

        for row in rows:
            if self._evaluate_row_condition(row, condition):
                filtered_rows.append(row)

        return filtered_rows

    def _evaluate_row_condition(self, row: Dict[str, Any], condition: QueryCondition) -> bool:
        """
        Evalúa si una fila cumple con la condición especificada
        """
        if not condition.filters:
            return True

        # Evaluar el primer filtro
        results = [self._evaluate_filter(row, condition.filters[0])]

        # Evaluar filtros adicionales con operadores lógicos
        for i in range(1, len(condition.filters)):
            filter_result = self._evaluate_filter(row, condition.filters[i])
            logical_op = condition.logical_operators[i-1]

            if logical_op == 'AND':
                results.append(results[-1] and filter_result)
            elif logical_op == 'OR':
                results.append(results[-1] or filter_result)

        return results[-1] if results else True

    def _evaluate_filter(self, row: Dict[str, Any], filter_obj: QueryFilter) -> bool:
        """
        Evalúa un filtro individual contra una fila
        """
        cells = row.get('cells', {})
        cell_value = cells.get(filter_obj.column)

        # Convertir a string para comparación
        cell_str = str(cell_value) if cell_value is not None else ""
        filter_value = filter_obj.value

        try:
            if filter_obj.operator == 'equals':
                return cell_str == filter_value

            elif filter_obj.operator == 'iequals':
                return cell_str.lower() == filter_value.lower()

            elif filter_obj.operator == 'contains':
                return filter_value in cell_str

            elif filter_obj.operator == 'icontains':
                return filter_value.lower() in cell_str.lower()

            elif filter_obj.operator == 'not_equals':
                return cell_str != filter_value

            elif filter_obj.operator == 'is_empty':
                return not cell_value or cell_str.strip() == ""

            elif filter_obj.operator == 'not_empty':
                return bool(cell_value) and cell_str.strip() != ""

            elif filter_obj.operator == 'greater_than':
                return self._compare_numeric_or_date(cell_value, filter_value, '>')

            elif filter_obj.operator == 'less_than':
                return self._compare_numeric_or_date(cell_value, filter_value, '<')

            else:
                self.logger.warning(f"Operador no reconocido: {filter_obj.operator}")
                return False

        except Exception as e:
            self.logger.warning(f"Error evaluating filter {filter_obj.column}:{filter_obj.operator}:{filter_obj.value}: {str(e)}")
            return False

    def _compare_numeric_or_date(self, cell_value: Any, filter_value: str, operator: str) -> bool:
        """
        Compara valores numéricos o de fecha
        """
        try:
            # Intentar conversión numérica
            try:
                cell_num = float(cell_value)
                filter_num = float(filter_value)

                if operator == '>':
                    return cell_num > filter_num
                elif operator == '<':
                    return cell_num < filter_num
            except (ValueError, TypeError):
                pass

            # Intentar conversión de fecha
            try:
                if isinstance(cell_value, datetime):
                    cell_date = cell_value
                else:
                    cell_date = datetime.fromisoformat(str(cell_value).replace('Z', '+00:00'))

                try:
                    filter_date = datetime.fromisoformat(filter_value.replace('Z', '+00:00'))
                except:
                    filter_date = datetime.strptime(filter_value, '%Y-%m-%d')

                if operator == '>':
                    return cell_date > filter_date
                elif operator == '<':
                    return cell_date < filter_date
            except (ValueError, TypeError):
                pass

            # Comparación de strings como último recurso
            cell_str = str(cell_value)
            if operator == '>':
                return cell_str > filter_value
            elif operator == '<':
                return cell_str < filter_value

        except Exception as e:
            self.logger.warning(f"Error in numeric/date comparison: {str(e)}")
            return False

        return False