"""
Cálculo de la barra de KPIs (Fase 6).

Los KPIs NO se guardan en ninguna tabla: se calculan sumando las líneas de
picking de un puesto en una fecha. Así nunca quedan "desfasados".
"""

from dataclasses import dataclass, asdict
from datetime import date

from sqlmodel import Session, select

from app.models import LineaPicking, Material, TipoUnidad
from app.services.configuracion import get_config


@dataclass
class KPIs:
    total_pedido: float = 0.0
    total_despachado: float = 0.0
    pct_cumplimiento: float = 0.0
    pct_faltante: float = 0.0
    total_unidades: int = 0
    total_pendiente: float = 0.0
    cumple_objetivo: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


def calcular_kpis(session: Session, puesto_id: int, fecha: date) -> KPIs:
    filas = session.exec(
        select(LineaPicking, Material)
        .join(Material, Material.id == LineaPicking.material_id)
        .where(
            LineaPicking.puesto_id == puesto_id,
            LineaPicking.fecha == fecha,
        )
    ).all()
    lineas = [linea for linea, _ in filas]

    total_pedido = sum(l.cantidad_pedida for l in lineas)
    total_despachado = sum(l.cantidad_despachada for l in lineas)
    # "Total unidades" = lo despachado en las líneas que se cuentan por unidad.
    total_unidades = sum(
        int(linea.cantidad_despachada)
        for linea, material in filas
        if material.tipo_unidad is TipoUnidad.unidad
    )
    # El pendiente por línea nunca es negativo (si despacharon de más, cuenta 0).
    total_pendiente = sum(
        max(l.cantidad_pedida - l.cantidad_despachada, 0) for l in lineas
    )

    if total_pedido > 0:
        pct_cumplimiento = round(total_despachado / total_pedido * 100, 1)
    else:
        pct_cumplimiento = 0.0
    pct_faltante = round(100 - pct_cumplimiento, 1)

    return KPIs(
        total_pedido=round(total_pedido, 2),
        total_despachado=round(total_despachado, 2),
        pct_cumplimiento=pct_cumplimiento,
        pct_faltante=pct_faltante,
        total_unidades=total_unidades,
        total_pendiente=round(total_pendiente, 2),
        cumple_objetivo=pct_cumplimiento >= get_config().cumplimiento_objetivo,
    )
