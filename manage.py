"""
Herramienta de línea de comandos para la base de datos (solo desarrollo).

    py manage.py init     -> crea las tablas que falten (no borra nada)
    py manage.py seed     -> carga usuarios y datos de prueba
    py manage.py reset     -> borra la BD, la recrea y la vuelve a llenar

"reset" NO se debe usar con datos reales: borra todo.

Concepto nuevo: `argparse` lee lo que escribís después de `manage.py` (init /
seed / reset) y llama a la función que corresponde. Es la forma estándar en
Python de hacer un programa con "subcomandos".
"""

import argparse
from pathlib import Path

from sqlmodel import Session, select

from app import models  # noqa: F401  (importarlo registra todas las tablas)
from app.database import SQLITE_FILE_NAME, create_db_and_tables, engine
from app.models import Rol, Usuario
from app.security import hash_password
from app.services.configuracion import get_config, invalidar_cache

# --- usuarios de prueba: (usuario, cédula, rol) ---
USUARIOS_DEMO = [
    ("usuario1", "1001", Rol.operario),
    ("usuario2", "1002", Rol.supervisor),
    ("admin", "1003", Rol.administrador),
]


def cmd_init() -> None:
    create_db_and_tables()
    tablas = ", ".join(sorted(models.SQLModel.metadata.tables))
    print(f"Tablas listas ({len(models.SQLModel.metadata.tables)}): {tablas}")


def cmd_seed() -> None:
    _seed_usuarios()
    # `seed_datos` vive en su propio archivo porque son muchos datos de ejemplo.
    from seed_datos import cargar_datos_demo

    cargar_datos_demo()
    invalidar_cache()
    get_config()  # deja creada la fila de configuración con los valores por defecto
    print("Datos de prueba cargados.")


def cmd_reset() -> None:
    archivo = Path(SQLITE_FILE_NAME)
    if archivo.exists():
        archivo.unlink()
        print(f"Borrado: {archivo}")
    cmd_init()
    cmd_seed()
    print("\nEntrá con usuario1 / 1001 · usuario2 / 1002 · admin / 1003")


def _seed_usuarios() -> None:
    with Session(engine) as session:
        for username, cedula, rol in USUARIOS_DEMO:
            existe = session.exec(
                select(Usuario).where(Usuario.username == username)
            ).first()
            if existe:
                continue
            session.add(
                Usuario(
                    username=username,
                    cedula=cedula,
                    rol=rol,
                    hashed_password=hash_password(cedula),
                )
            )
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Utilidades de base de datos (dev).")
    parser.add_argument("comando", choices=["init", "seed", "reset"])
    args = parser.parse_args()
    {"init": cmd_init, "seed": cmd_seed, "reset": cmd_reset}[args.comando]()


if __name__ == "__main__":
    main()
