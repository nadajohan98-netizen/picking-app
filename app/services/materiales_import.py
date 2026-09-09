"""
Lectura del archivo de materiales/productos que sube el administrador.

Columnas esperadas (por nombre, sin importar mayúsculas ni tildes):
  - codigo   (obligatoria)
  - descripcion / nombre  (obligatoria)
  - unidad / tipo_unidad  -> "UN" o "KG" (si falta, se asume KG)
"""

from __future__ import annotations

from app.models import TipoUnidad
from app.services.tabla_import import leer_tabla


def _unidad(valor: str) -> TipoUnidad:
    v = valor.strip().upper()
    if v in ("UN", "UND", "UNIDAD", "U"):
        return TipoUnidad.unidad
    if v in ("KG", "KILO", "KILOS", "KILOGRAMO", "K"):
        return TipoUnidad.kilogramo
    return TipoUnidad.kilogramo


def extraer_materiales(nombre_archivo: str, contenido: bytes) -> list[dict]:
    """Devuelve [{codigo, descripcion, tipo_unidad}] sin repetir por código."""
    filas = leer_tabla(nombre_archivo, contenido)
    if not filas:
        return []

    vistos: set[str] = set()
    materiales: list[dict] = []
    for fila in filas:
        codigo = (fila.get("codigo") or fila.get("code") or "").strip()
        desc = (fila.get("descripcion") or fila.get("nombre") or fila.get("material") or "").strip()
        if not codigo or not desc or codigo in vistos:
            continue
        unidad_txt = fila.get("unidad") or fila.get("tipo unidad") or fila.get("tipo_unidad") or ""
        vistos.add(codigo)
        materiales.append({
            "codigo": codigo,
            "descripcion": desc,
            "tipo_unidad": _unidad(unidad_txt),
        })
    return materiales
