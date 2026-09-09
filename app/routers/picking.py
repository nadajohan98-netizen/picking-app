"""
Cuadrícula de picking.

- GET   /picking/{puesto_id}                 -> la pantalla (HTML + Tabulator)
- GET   /api/puestos/{puesto_id}/lineas      -> los datos de la grilla (JSON)
- PUT   /api/lineas/{linea_id}/pesos         -> guarda el piqueo por canastilla (KG)
- PATCH /api/lineas/{linea_id}               -> guarda lote / vencimiento / despachado UN
- GET   /api/puestos/{puesto_id}/kpis        -> la barra de KPIs
- GET   /api/lotes?q=ABC                     -> autocompletado de lotes
- GET   /api/config                          -> parámetros (para leer el código de barras)
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_roles
from app.database import get_session
from app.models import (
    Almacen,
    AsignacionDiaria,
    LineaPicking,
    Lote,
    Material,
    Puesto,
    Rol,
    TipoUnidad,
    Usuario,
)
from app.services.configuracion import get_config
from app.services.kpis import calcular_kpis
from app.services.locks import lock_manager
from app.services.vencimiento import (
    VencimientoInvalido,
    clasificar_vencimiento,
    validar_vencimiento,
)
from app.templating import templates

router = APIRouter()


def _exigir_candado(linea: LineaPicking, user: Usuario) -> None:
    """Solo puede editar quien tiene el puesto abierto en este momento."""
    if lock_manager.holds.get(linea.puesto_id) != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este puesto no está abierto por ti. Vuelve a abrirlo.",
        )


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------
@router.get("/picking/{puesto_id}")
def pantalla_picking(
    request: Request,
    puesto_id: int,
    user: Usuario = Depends(require_roles(Rol.operario)),
    session: Session = Depends(get_session),
):
    puesto = session.get(Puesto, puesto_id)
    if puesto is None:
        raise HTTPException(status_code=404, detail="Ese puesto no existe.")

    hoy = date.today()
    almacenes = session.exec(
        select(Almacen)
        .join(AsignacionDiaria, AsignacionDiaria.almacen_id == Almacen.id)
        .where(
            AsignacionDiaria.puesto_id == puesto_id,
            AsignacionDiaria.fecha == hoy,
        )
        .order_by(Almacen.codigo)
    ).all()

    return templates.TemplateResponse(
        request,
        "picking.html",
        {
            "user": user,
            "puesto": puesto,
            "almacenes": almacenes,
            "hoy": hoy.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Datos de la grilla
# ---------------------------------------------------------------------------
def _linea_a_dict(
    linea: LineaPicking,
    material: Material,
    almacen: Almacen,
    lote: Lote | None,
    editor: Usuario | None,
) -> dict:
    return {
        "id": linea.id,
        "almacen": f"{almacen.codigo} - {almacen.nombre}",
        "almacen_codigo": almacen.codigo,
        "material_codigo": material.codigo,
        "material_descripcion": material.descripcion,
        "unidad": material.tipo_unidad.value,
        "es_kg": material.tipo_unidad is TipoUnidad.kilogramo,
        "cantidad_pedida": linea.cantidad_pedida,
        "cantidad_despachada": round(linea.cantidad_despachada, 3),
        "pesos": list(linea.pesos or []),
        "lote": lote.codigo if lote else "",
        "fecha_vencimiento": (
            linea.fecha_vencimiento.isoformat() if linea.fecha_vencimiento else ""
        ),
        "vencimiento_estado": clasificar_vencimiento(linea.fecha_vencimiento),
        "canastillas": linea.canastillas,
        "diferencia": round(linea.cantidad_pedida - linea.cantidad_despachada, 3),
        "editado_por": editor.username if editor else "",
        "actualizado_en": linea.actualizado_en.strftime("%Y-%m-%d %H:%M"),
    }


def _cargar_linea_dict(session: Session, linea: LineaPicking, editor: Usuario) -> dict:
    material = session.get(Material, linea.material_id)
    almacen = session.get(Almacen, linea.almacen_id)
    lote = session.get(Lote, linea.lote_id) if linea.lote_id else None
    return _linea_a_dict(linea, material, almacen, lote, editor)


@router.get("/api/puestos/{puesto_id}/lineas")
def listar_lineas(
    puesto_id: int,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    hoy = date.today()
    filas = session.exec(
        select(LineaPicking, Material, Almacen)
        .join(Material, Material.id == LineaPicking.material_id)
        .join(Almacen, Almacen.id == LineaPicking.almacen_id)
        .where(LineaPicking.puesto_id == puesto_id, LineaPicking.fecha == hoy)
        .order_by(Almacen.codigo, Material.codigo)
    ).all()

    resultado = []
    for linea, material, almacen in filas:
        lote = session.get(Lote, linea.lote_id) if linea.lote_id else None
        editor = (
            session.get(Usuario, linea.editado_por_id)
            if linea.editado_por_id
            else None
        )
        resultado.append(_linea_a_dict(linea, material, almacen, lote, editor))
    return resultado


# ---------------------------------------------------------------------------
# Piqueo por canastilla (líneas KG): se envía la lista completa de pesos
# ---------------------------------------------------------------------------
class PesosBody(BaseModel):
    pesos: list[float]


@router.put("/api/lineas/{linea_id}/pesos")
def guardar_pesos(
    linea_id: int,
    body: PesosBody,
    user: Usuario = Depends(require_roles(Rol.operario)),
    session: Session = Depends(get_session),
):
    linea = session.get(LineaPicking, linea_id)
    if linea is None:
        raise HTTPException(status_code=404, detail="Línea no encontrada.")
    _exigir_candado(linea, user)

    material = session.get(Material, linea.material_id)
    if material.tipo_unidad is not TipoUnidad.kilogramo:
        raise HTTPException(
            status_code=422, detail="Esta línea no se piquea por peso (es por unidad)."
        )

    pesos = [round(float(p), 3) for p in body.pesos if p is not None]
    if any(p <= 0 for p in pesos):
        raise HTTPException(status_code=422, detail="Los pesos deben ser mayores que 0.")

    total = round(sum(pesos), 3)
    tope = linea.cantidad_pedida * (1 + get_config().tolerancia_pct / 100)
    if total > tope + 1e-9:
        exceso = round(total - linea.cantidad_pedida, 3)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Te pasarías {exceso} kg de lo pedido "
                f"(límite +{get_config().tolerancia_pct:g} %)."
            ),
        )

    linea.pesos = pesos
    linea.cantidad_despachada = total
    linea.canastillas = len(pesos)
    linea.editado_por_id = user.id
    linea.actualizado_en = datetime.now()
    session.add(linea)
    session.commit()
    session.refresh(linea)
    return _cargar_linea_dict(session, linea, user)


# ---------------------------------------------------------------------------
# Lote / vencimiento / despachado de líneas UN
# ---------------------------------------------------------------------------
class CambioCelda(BaseModel):
    campo: str
    valor: str | float | int | None


CAMPOS_EDITABLES = {"cantidad_despachada", "lote", "fecha_vencimiento"}


@router.patch("/api/lineas/{linea_id}")
def editar_linea(
    linea_id: int,
    cambio: CambioCelda,
    user: Usuario = Depends(require_roles(Rol.operario)),
    session: Session = Depends(get_session),
):
    linea = session.get(LineaPicking, linea_id)
    if linea is None:
        raise HTTPException(status_code=404, detail="Línea no encontrada.")
    _exigir_candado(linea, user)

    if cambio.campo not in CAMPOS_EDITABLES:
        raise HTTPException(status_code=422, detail=f"Campo no editable: {cambio.campo}")

    try:
        _aplicar_cambio(session, linea, cambio.campo, cambio.valor)
    except (VencimientoInvalido, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    linea.editado_por_id = user.id
    linea.actualizado_en = datetime.now()
    session.add(linea)
    session.commit()
    session.refresh(linea)
    return _cargar_linea_dict(session, linea, user)


def _aplicar_cambio(session: Session, linea: LineaPicking, campo: str, valor) -> None:
    if campo == "cantidad_despachada":
        material = session.get(Material, linea.material_id)
        if material.tipo_unidad is TipoUnidad.kilogramo:
            raise ValueError("Las líneas en KG se piquean por canastilla, no a mano.")
        x = float(valor or 0)
        if x < 0:
            raise ValueError("No puede ser negativa.")
        tope = linea.cantidad_pedida * (1 + get_config().tolerancia_pct / 100)
        if x > tope + 1e-9:
            raise ValueError(
                f"Te pasas de lo pedido más del "
                f"{get_config().tolerancia_pct:g} % permitido."
            )
        linea.cantidad_despachada = x

    elif campo == "lote":
        texto = str(valor).strip() if valor is not None else ""
        if texto == "":
            linea.lote_id = None
            return
        lote = session.exec(
            select(Lote).where(Lote.codigo == texto, Lote.activo == True)  # noqa: E712
        ).first()
        if lote is None:
            raise ValueError(f"El lote '{texto}' no está en el catálogo.")
        linea.lote_id = lote.id

    elif campo == "fecha_vencimiento":
        texto = str(valor).strip() if valor is not None else ""
        if texto == "":
            linea.fecha_vencimiento = None
            return
        try:
            parsed = date.fromisoformat(texto)
        except ValueError:
            raise ValueError("Fecha no válida (usa el formato AAAA-MM-DD).")
        linea.fecha_vencimiento = validar_vencimiento(parsed)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
@router.get("/api/puestos/{puesto_id}/kpis")
def kpis_puesto(
    puesto_id: int,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return calcular_kpis(session, puesto_id, date.today()).as_dict()


# ---------------------------------------------------------------------------
# Autocompletado de lotes
# ---------------------------------------------------------------------------
@router.get("/api/lotes")
def buscar_lotes(
    q: str = "",
    all: bool = False,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    consulta = select(Lote).where(Lote.activo == True)  # noqa: E712
    q = q.strip()
    if q:
        consulta = consulta.where(Lote.codigo.ilike(f"{q}%"))  # type: ignore[union-attr]
    consulta = consulta.order_by(Lote.codigo).limit(5000 if all else 20)
    return [lote.codigo for lote in session.exec(consulta).all()]


# ---------------------------------------------------------------------------
# Configuración (lectura para el frontend: leer el peso del código de barras)
# ---------------------------------------------------------------------------
@router.get("/api/config")
def config_publica(user: Usuario = Depends(get_current_user)):
    c = get_config()
    return {
        "bc_longitud": c.bc_longitud,
        "bc_prefijo": c.bc_prefijo,
        "bc_peso_inicio": c.bc_peso_inicio,
        "bc_peso_digitos": c.bc_peso_digitos,
        "bc_peso_divisor": c.bc_peso_divisor,
        "tolerancia_pct": c.tolerancia_pct,
        "venc_alerta_dias": c.venc_alerta_dias,
    }
