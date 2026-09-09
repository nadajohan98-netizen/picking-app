"""
Lectura del archivo de lotes que sube el administrador.

Busca una columna "lote" / "codigo" / "code"; si no la encuentra, usa la primera.
Devuelve la lista de códigos, limpios y sin repetir.
"""

from __future__ import annotations

from app.services.tabla_import import leer_tabla, primera_col

_NOMBRES = ("lote", "codigo", "code")


def extraer_codigos(nombre_archivo: str, contenido: bytes) -> list[str]:
    filas = leer_tabla(nombre_archivo, contenido)
    vistos: set[str] = set()
    codigos: list[str] = []
    for fila in filas:
        codigo = next((fila[n] for n in _NOMBRES if fila.get(n)), primera_col(fila))
        codigo = codigo.strip()
        if codigo and codigo not in vistos:
            vistos.add(codigo)
            codigos.append(codigo)
    return codigos
