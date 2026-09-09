"""
Conexión a la base de datos.

Conceptos:

- `engine` (motor): el objeto que sabe hablar con la base de datos. Se crea una
  sola vez y se reutiliza en toda la app.

- `sqlite:///picking.db`: la "dirección" de la base de datos. Aquí decimos
  "usa SQLite, en un archivo llamado picking.db en esta carpeta".

- `Session` (sesión): una conversación temporal con la base de datos para leer o
  escribir. Se abre, se hace el trabajo, se cierra. La usaremos desde la Fase 1.
"""

import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

# Nombre del archivo de base de datos. Al ser SQLite, es UN solo archivo.
SQLITE_FILE_NAME = "picking.db"
DATABASE_URL = f"sqlite:///{SQLITE_FILE_NAME}"

# Con la variable de entorno SQL_ECHO=1, SQLModel imprime cada sentencia SQL que
# ejecuta. Útil para aprender; se deja apagado por defecto para no ensuciar los
# logs del servidor.
#   PowerShell:  $env:SQL_ECHO=1 ; py run.py
_ECHO = os.getenv("SQL_ECHO", "").lower() in ("1", "true", "yes")
engine = create_engine(DATABASE_URL, echo=_ECHO)


def create_db_and_tables() -> None:
    """Crea el archivo picking.db y todas las tablas que aún no existan.

    `SQLModel.metadata` es un registro donde quedan anotadas todas las clases
    con `table=True` que se hayan importado. Por eso, quien llame a esta función
    debe haber importado antes `app.models` (para que las tablas estén anotadas).

    `create_all` NO borra ni modifica tablas existentes: solo crea las que faltan.
    """
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Entrega una sesión de base de datos y la cierra al terminar.

    FastAPI llamará a esta función (con `Depends(get_session)`) antes de cada
    ruta que la pida. El `yield` entrega la sesión a la ruta; cuando la ruta
    termina, el `with` la cierra automáticamente, pase lo que pase.
    """
    with Session(engine) as session:
        yield session
