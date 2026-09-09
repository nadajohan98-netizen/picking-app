"""
Lectura de archivos .xlsx / .csv que sube el administrador.

`leer_tabla` devuelve una lista de diccionarios: una fila = un diccionario cuyas
claves son los encabezados de la primera fila, en minúsculas y sin espacios ni
tildes. Así los importadores (lotes, materiales) buscan sus columnas por nombre
sin importar cómo las escribió la persona en el Excel.
"""

from __future__ import annotations

import csv
import io
import unicodedata

from openpyxl import load_workbook


def normalizar(texto: str) -> str:
    """'Código ' -> 'codigo' ; 'Tipo Unidad' -> 'tipo unidad'."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().lower()


def leer_tabla(nombre_archivo: str, contenido: bytes) -> list[dict]:
    nombre = nombre_archivo.lower()
    if nombre.endswith(".csv"):
        filas = _leer_csv(contenido)
    elif nombre.endswith(".xlsx"):
        filas = _leer_xlsx(contenido)
    else:
        raise ValueError("Formato no soportado. Subí un archivo .xlsx o .csv.")

    if not filas:
        return []

    encabezados = [normalizar(c) if c is not None else "" for c in filas[0]]
    resultado: list[dict] = []
    for fila in filas[1:]:
        if not any(v is not None and str(v).strip() for v in fila):
            continue  # fila vacía
        d = {}
        for i, valor in enumerate(fila):
            if i < len(encabezados) and encabezados[i]:
                d[encabezados[i]] = "" if valor is None else str(valor).strip()
        resultado.append(d)
    return resultado


def primera_col(fila: dict) -> str:
    """El primer valor no vacío de la fila (para archivos de una sola columna)."""
    for v in fila.values():
        if v:
            return v
    return ""


def _leer_csv(contenido: bytes) -> list[list]:
    texto = contenido.decode("utf-8-sig", errors="replace")
    return [fila for fila in csv.reader(io.StringIO(texto))]


def _leer_xlsx(contenido: bytes) -> list[list]:
    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    hoja = libro.active
    return [list(fila) for fila in hoja.iter_rows(values_only=True)]
