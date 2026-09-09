"""
Panel de supervisor.

- /supervisor                  -> KPIs de todos los puestos + alertas de vencimiento
- /api/supervisor/resumen      -> los mismos datos en JSON (poll cada 15 s)
- /supervisor/puesto/{id}      -> detalle de un puesto en SOLO LECTURA
- /supervisor/cierre           -> resumen del día, listo para imprimir

El supervisor ve todo pero no toca nada: sus rutas no permiten editar.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
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
        filas_puestos.append({
            "id": p.id,
            "numero": p.numero,
            "activo": p.activo,
            "ocupado_por": dueno.username if dueno else "",
            "kpis": k.as_dict(),
        })

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
            alertas.append({
                "puesto": puesto.numero,
                "material": f"{material.codigo} - {material.descripcion}",
                "lote": lote.codigo if lote else "",
                "vence": linea.fecha_vencimiento.isoformat(),
                "estado": estado,
            })

    return {"fecha": hoy.isoformat(), "puestos": filas_puestos, "alertas": alertas}


@router.get("/supervisor")
def panel(request: Request, user: Usuario = solo_supervisor,
          session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request, "supervisor.html", {"user": user, "resumen": _construir_resumen(session)}
    )


@router.get("/api/supervisor/resumen")
def resumen_json(user: Usuario = solo_supervisor, session: Session = Depends(get_session)):
    return _construir_resumen(session)


# ---------------------------------------------------------------------------
# Detalle de un puesto (solo lectura)
# ---------------------------------------------------------------------------
def _lineas_de(session: Session, puesto_id: int, fecha: date) -> list[dict]:
    filas = session.exec(
        select(LineaPicking, Material, Almacen)
        .join(Material, Material.id == LineaPicking.material_id)
        .join(Almacen, Almacen.id == LineaPicking.almacen_id)
        .where(LineaPicking.puesto_id == puesto_id, LineaPicking.fecha == fecha)
        .order_by(Almacen.codigo, Material.codigo)
    ).all()
    salida = []
    for linea, material, almacen in filas:
        lote = session.get(Lote, linea.lote_id) if linea.lote_id else None
        editor = session.get(Usuario, linea.editado_por_id) if linea.editado_por_id else None
        salida.append({
            "almacen": f"{almacen.codigo} - {almacen.nombre}",
            "material": f"{material.codigo} · {material.descripcion}",
            "unidad": material.tipo_unidad.value,
            "es_kg": material.tipo_unidad.value == "KG",
            "pedida": linea.cantidad_pedida,
            "despachada": round(linea.cantidad_despachada, 3),
            "pesos": list(linea.pesos or []),
            "lote": lote.codigo if lote else "",
            "vencimiento": linea.fecha_vencimiento.isoformat() if linea.fecha_vencimiento else "",
            "vencimiento_estado": clasificar_vencimiento(linea.fecha_vencimiento),
            "canastillas": linea.canastillas,
            "diferencia": round(linea.cantidad_pedida - linea.cantidad_despachada, 3),
            "editado_por": editor.username if editor else "",
            "actualizado_en": linea.actualizado_en.strftime("%H:%M"),
        })
    return salida


@router.get("/supervisor/puesto/{puesto_id}")
def detalle_puesto(puesto_id: int, request: Request, user: Usuario = solo_supervisor,
                   session: Session = Depends(get_session)):
    puesto = session.get(Puesto, puesto_id)
    if puesto is None:
        raise HTTPException(status_code=404, detail="Ese puesto no existe.")
    hoy = date.today()
    return templates.TemplateResponse(request, "supervisor_puesto.html", {
        "user": user,
        "puesto": puesto,
        "hoy": hoy.isoformat(),
        "lineas": _lineas_de(session, puesto_id, hoy),
        "kpis": calcular_kpis(session, puesto_id, hoy).as_dict(),
        "ocupado_por": (lambda uid: session.get(Usuario, uid).username if uid else "")(
            lock_manager.snapshot().get(puesto_id)
        ),
    })


# ---------------------------------------------------------------------------
# Cierre del día (para imprimir)
# ---------------------------------------------------------------------------
@router.get("/supervisor/cierre")
def cierre(request: Request, user: Usuario = solo_supervisor,
           session: Session = Depends(get_session)):
    resumen = _construir_resumen(session)
    return templates.TemplateResponse(request, "supervisor_cierre.html", {
        "user": user,
        "resumen": resumen,
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
