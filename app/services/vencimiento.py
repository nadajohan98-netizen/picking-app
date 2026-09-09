"""
Reglas de la fecha de vencimiento.

Dos cosas distintas:

1. VALIDAR al guardar: la fecha debe ser real y estar dentro de un rango
   razonable. Si no, se rechaza el guardado (no se escribe en la BD).

2. CLASIFICAR para mostrar: dada una fecha válida, decir si está "ok",
   "pronto" (por vencer) o "vencido", para pintar la celda de color.

Los límites (días máximos, días de alerta) los define el administrador en la
pantalla de Configuración; se leen con get_config().
"""

from datetime import date, timedelta

from app.services.configuracion import get_config


class VencimientoInvalido(ValueError):
    """Se lanza cuando la fecha de vencimiento no cumple las reglas."""


def validar_vencimiento(valor: date, hoy: date | None = None) -> date:
    """Devuelve la fecha si es válida; si no, lanza VencimientoInvalido."""
    cfg = get_config()
    hoy = hoy or date.today()
    limite = hoy + timedelta(days=cfg.venc_max_dias)

    if valor < hoy:
        raise VencimientoInvalido("La fecha de vencimiento ya pasó.")
    if valor > limite:
        raise VencimientoInvalido(
            f"La fecha está demasiado lejos "
            f"(máximo {cfg.venc_max_dias} días desde hoy)."
        )
    return valor


def clasificar_vencimiento(valor: date | None, hoy: date | None = None) -> str:
    """'sin_fecha' | 'ok' | 'pronto' | 'vencido' — para elegir el color."""
    if valor is None:
        return "sin_fecha"
    hoy = hoy or date.today()
    dias_restantes = (valor - hoy).days
    if dias_restantes < 0:
        return "vencido"
    if dias_restantes <= get_config().venc_alerta_dias:
        return "pronto"
    return "ok"
