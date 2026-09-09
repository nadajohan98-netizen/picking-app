"""
Acceso a la configuración editable por el administrador.

Hay una sola fila (id=1). Si no existe, se crea con los valores por defecto del
modelo. Se guarda en memoria (`_cache`) porque cambia poquísimo; cada vez que el
admin la modifica, se invalida.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.database import engine
from app.models import Configuracion

_cache: Configuracion | None = None


def get_config() -> Configuracion:
    global _cache
    if _cache is not None:
        return _cache
    with Session(engine) as session:
        cfg = session.get(Configuracion, 1)
        if cfg is None:
            cfg = Configuracion(id=1)
            session.add(cfg)
            session.commit()
            session.refresh(cfg)
        _cache = cfg
        session.expunge(cfg)  # lo usamos fuera de la sesión, como objeto suelto
    return _cache


def actualizar_config(datos: dict) -> Configuracion:
    """Aplica los campos de `datos` a la fila de configuración y refresca la caché."""
    global _cache
    with Session(engine) as session:
        cfg = session.get(Configuracion, 1) or Configuracion(id=1)
        for campo, valor in datos.items():
            if hasattr(cfg, campo):
                setattr(cfg, campo, valor)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
        session.expunge(cfg)
    _cache = cfg
    return _cache


def invalidar_cache() -> None:
    global _cache
    _cache = None
