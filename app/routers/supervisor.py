"""
Panel de supervisor (Fase 6):

- /supervisor              -> KPIs de todos los puestos + alertas de vencimiento
- /api/supervisor/resumen  -> los mismos datos en JSON, para refrescar solo (poll)
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from app.auth import require_roles
from app.database import get_session
from app.models import Almacen, LineaPicking, Lote, Material, Puesto, Rol, Usuario
from app.services.kpis import calcular_kpis
from app.services.locks import lock_manager
from app.services.vencimiento import clasificar_vencimiento
from app.templating import templates

router = APIRouter()

solo_supervisor = Depends(require_roles(Rol.supervisor))


def _construir_resumen(session: Session) -> dict:
    hoy = date.today()
    puestos = session.exec(select(Puesto).order_by(Puesto.numero)).all()
    ocupados = lock_manager.snapshot()

    filas_puestos = []
    for p in puestos:
        k = calcular_kpis(session, p.id, hoy)
        dueno_id = ocupados.get(p.id)
        dueno = session.get(Usuario, dueno_id) if dueno_id else None
        filas_puestos.append(
            {
                "numero": p.numero,
                "descripcion": p.descripcion or "",
                "ocupado_por": dueno.username if dueno else "",
                "kpis": k.as_dict(),
            }
        )

    # Alertas: líneas de hoy con vencimiento "pronto" o "vencido", en cualquier puesto.
    alertas = []
    filas = session.exec(
        select(LineaPicking, Material, Puesto)
        .join(Material, Material.id == LineaPicking.material_id)
        .join(Puesto, Puesto.id == LineaPicking.puesto_id)
        .where(
            LineaPicking.fecha == hoy,
            LineaPicking.fecha_vencimiento.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(LineaPicking.fecha_vencimiento)
    ).all()
    for linea, material, puesto in filas:
        estado = clasificar_vencimiento(linea.fecha_vencimiento)
        if estado in ("pronto", "vencido"):
            lote = session.get(Lote, linea.lote_id) if linea.lote_id else None
            alertas.append(
                {
                    "puesto": puesto.numero,
                    "material": f"{material.codigo} - {material.descripcion}",
                    "lote": lote.codigo if lote else "",
                    "vence": linea.fecha_vencimiento.isoformat(),
                    "estado": estado,
                }
            )

    return {"fecha": hoy.isoformat(), "puestos": filas_puestos, "alertas": alertas}


@router.get("/supervisor")
def panel(
    request: Request,
    user: Usuario = solo_supervisor,
    session: Session = Depends(get_session),
):
    resumen = _construir_resumen(session)
    return templates.TemplateResponse(
        request, "supervisor.html", {"user": user, "resumen": resumen}
    )


@router.get("/api/supervisor/resumen")
def resumen_json(
    user: Usuario = solo_supervisor,
    session: Session = Depends(get_session),
):
    return _construir_resumen(session)
