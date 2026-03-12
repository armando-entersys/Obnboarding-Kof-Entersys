# app/db/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Clase base declarativa de la cual heredarán todos los modelos de la base de datos.
    """
    pass

# Los modelos se importan directamente en cada archivo que los necesite
# para evitar importaciones circulares