"""
Catálogos que administra el admin: lotes, materiales, almacenes, puestos y la
asignación diaria de almacenes por puesto.

Todas las rutas cuelgan de /admin y exigen rol administrador.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import require_roles
from app.database import get_session
from app.models import Almacen, AsignacionDiaria, Lote, Material, Puesto, Rol, TipoUnidad, Usuario
from app.services.lotes_import import extraer_codigos
from app.services.materiales_import import extraer_materiales
from app.templating import templates

router = APIRouter(prefix="/admin")
solo_admin = Depends(require_roles(Rol.administrador))


def _redir(destino: str, msg: str | None = None) -> RedirectResponse:
    url = destino + (f"?msg={msg}" if msg else "")
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


# ===========================================================================
# LOTES
# ===========================================================================
@router.get("/lotes")
def ver_lotes(request: Request, user: Usuario = solo_admin,
              session: Session = Depends(get_session), msg: str | None = None):
    lotes = session.exec(select(Lote).order_by(Lote.codigo)).all()
    return templates.TemplateResponse(request, "admin/lotes.html",
                                      {"user": user, "lotes": lotes, "msg": msg})


@router.post("/lotes/cargar")
async def cargar_lotes(user: Usuario = solo_admin, session: Session = Depends(get_session),
                       archivo: UploadFile = File(...)):
    contenido = await archivo.read()
    try:
        codigos = extraer_codigos(archivo.filename or "", contenido)
    except ValueError as e:
        return _redir("/admin/lotes", str(e))

    existentes = {l.codigo for l in session.exec(select(Lote)).all()}
    nuevos = 0
    for codigo in codigos:
        if codigo not in existentes:
            session.add(Lote(codigo=codigo))
            existentes.add(codigo)
            nuevos += 1
    session.commit()
    return _redir("/admin/lotes", f"Archivo leído: {len(codigos)} códigos, {nuevos} nuevos.")


@router.post("/lotes/{lote_id}/toggle")
def toggle_lote(lote_id: int, user: Usuario = solo_admin, session: Session = Depends(get_session)):
    lote = session.get(Lote, lote_id)
    if lote:
        lote.activo = not lote.activo
        session.add(lote)
        session.commit()
    return _redir("/admin/lotes")


# ===========================================================================
# MATERIALES / PRODUCTOS
# ===========================================================================
@router.get("/materiales")
def ver_materiales(request: Request, user: Usuario = solo_admin,
                   session: Session = Depends(get_session), msg: str | None = None):
    materiales = session.exec(select(Material).order_by(Material.codigo)).all()
    return templates.TemplateResponse(request, "admin/materiales.html",
                                      {"user": user, "materiales": materiales,
                                       "unidades": list(TipoUnidad), "msg": msg})


@router.post("/materiales/crear")
def crear_material(user: Usuario = solo_admin, session: Session = Depends(get_session),
                   codigo: str = Form(...), descripcion: str = Form(...),
                   tipo_unidad: TipoUnidad = Form(...)):
    codigo = codigo.strip()
    if session.exec(select(Material).where(Material.codigo == codigo)).first():
        return _redir("/admin/materiales", f"El código '{codigo}' ya existe.")
    session.add(Material(codigo=codigo, descripcion=descripcion.strip(), tipo_unidad=tipo_unidad))
    session.commit()
    return _redir("/admin/materiales", f"Material '{codigo}' creado.")


@router.post("/materiales/{material_id}/editar")
def editar_material(material_id: int, user: Usuario = solo_admin,
                    session: Session = Depends(get_session),
                    descripcion: str = Form(...), tipo_unidad: TipoUnidad = Form(...)):
    m = session.get(Material, material_id)
    if m:
        m.descripcion = descripcion.strip()
        m.tipo_unidad = tipo_unidad
        session.add(m)
        session.commit()
    return _redir("/admin/materiales", "Material actualizado.")


@router.post("/materiales/{material_id}/toggle")
def toggle_material(material_id: int, user: Usuario = solo_admin,
                    session: Session = Depends(get_session)):
    m = session.get(Material, material_id)
    if m:
        m.activo = not m.activo
        session.add(m)
        session.commit()
    return _redir("/admin/materiales")


@router.post("/materiales/cargar")
async def cargar_materiales(user: Usuario = solo_admin, session: Session = Depends(get_session),
                            archivo: UploadFile = File(...)):
    contenido = await archivo.read()
    try:
        filas = extraer_materiales(archivo.filename or "", contenido)
    except ValueError as e:
        return _redir("/admin/materiales", str(e))

    existentes = {m.codigo: m for m in session.exec(select(Material)).all()}
    nuevos = actualizados = 0
    for f in filas:
        m = existentes.get(f["codigo"])
        if m is None:
            session.add(Material(**f))
            existentes[f["codigo"]] = f
            nuevos += 1
        else:
            m.descripcion = f["descripcion"]
            m.tipo_unidad = f["tipo_unidad"]
            session.add(m)
            actualizados += 1
    session.commit()
    return _redir("/admin/materiales",
                  f"Archivo leído: {nuevos} nuevos, {actualizados} actualizados.")


# ===========================================================================
# ALMACENES
# ===========================================================================
@router.get("/almacenes")
def ver_almacenes(request: Request, user: Usuario = solo_admin,
                  session: Session = Depends(get_session), msg: str | None = None):
    almacenes = session.exec(select(Almacen).order_by(Almacen.codigo)).all()
    return templates.TemplateResponse(request, "admin/almacenes.html",
                                      {"user": user, "almacenes": almacenes, "msg": msg})


@router.post("/almacenes/crear")
def crear_almacen(user: Usuario = solo_admin, session: Session = Depends(get_session),
                  codigo: str = Form(...), nombre: str = Form(...)):
    codigo = codigo.strip()
    if session.exec(select(Almacen).where(Almacen.codigo == codigo)).first():
        return _redir("/admin/almacenes", f"El código '{codigo}' ya existe.")
    session.add(Almacen(codigo=codigo, nombre=nombre.strip()))
    session.commit()
    return _redir("/admin/almacenes", f"Almacén '{codigo}' creado.")


@router.post("/almacenes/{almacen_id}/editar")
def editar_almacen(almacen_id: int, user: Usuario = solo_admin,
                   session: Session = Depends(get_session), nombre: str = Form(...)):
    a = session.get(Almacen, almacen_id)
    if a:
        a.nombre = nombre.strip()
        session.add(a)
        session.commit()
    return _redir("/admin/almacenes", "Almacén actualizado.")


@router.post("/almacenes/{almacen_id}/toggle")
def toggle_almacen(almacen_id: int, user: Usuario = solo_admin,
                   session: Session = Depends(get_session)):
    a = session.get(Almacen, almacen_id)
    if a:
        a.activo = not a.activo
        session.add(a)
        session.commit()
    return _redir("/admin/almacenes")


# ===========================================================================
# PUESTOS
# ===========================================================================
@router.get("/puestos")
def ver_puestos(request: Request, user: Usuario = solo_admin,
                session: Session = Depends(get_session), msg: str | None = None):
    puestos = session.exec(select(Puesto).order_by(Puesto.numero)).all()
    return templates.TemplateResponse(request, "admin/puestos.html",
                                      {"user": user, "puestos": puestos, "msg": msg})


@router.post("/puestos/crear")
def crear_puesto(user: Usuario = solo_admin, session: Session = Depends(get_session),
                 numero: int = Form(...)):
    if session.exec(select(Puesto).where(Puesto.numero == numero)).first():
        return _redir("/admin/puestos", f"El puesto {numero} ya existe.")
    session.add(Puesto(numero=numero))
    session.commit()
    return _redir("/admin/puestos", f"Puesto {numero} creado.")


@router.post("/puestos/{puesto_id}/toggle")
def toggle_puesto(puesto_id: int, user: Usuario = solo_admin,
                  session: Session = Depends(get_session)):
    p = session.get(Puesto, puesto_id)
    if p:
        p.activo = not p.activo
        session.add(p)
        session.commit()
    return _redir("/admin/puestos")


# ===========================================================================
# ASIGNACIÓN DIARIA puesto <-> almacenes
# ===========================================================================
@router.get("/asignaciones")
def ver_asignaciones(request: Request, user: Usuario = solo_admin,
                     session: Session = Depends(get_session), fecha: str | None = None):
    dia = date.fromisoformat(fecha) if fecha else date.today()
    puestos = session.exec(
        select(Puesto).where(Puesto.activo == True).order_by(Puesto.numero)  # noqa: E712
    ).all()
    almacenes = session.exec(
        select(Almacen).where(Almacen.activo == True).order_by(Almacen.codigo)  # noqa: E712
    ).all()

    asignaciones = session.exec(
        select(AsignacionDiaria).where(AsignacionDiaria.fecha == dia)
    ).all()
    actuales: dict[int, set[int]] = {}
    for a in asignaciones:
        actuales.setdefault(a.puesto_id, set()).add(a.almacen_id)

    return templates.TemplateResponse(request, "admin/asignaciones.html",
                                      {"user": user, "fecha": dia.isoformat(),
                                       "puestos": puestos, "almacenes": almacenes,
                                       "actuales": actuales})


@router.post("/asignaciones/guardar")
async def guardar_asignaciones(request: Request, user: Usuario = solo_admin,
                               session: Session = Depends(get_session)):
    form = await request.form()
    dia = date.fromisoformat(str(form["fecha"]))

    marcados: set[tuple[int, int]] = set()
    for clave in form.keys():
        if clave.startswith("asg-"):
            _, p, a = clave.split("-")
            marcados.add((int(p), int(a)))

    existentes = session.exec(
        select(AsignacionDiaria).where(AsignacionDiaria.fecha == dia)
    ).all()
    existentes_set = {(e.puesto_id, e.almacen_id): e for e in existentes}

    for clave, obj in existentes_set.items():
        if clave not in marcados:
            session.delete(obj)
    for (p, a) in marcados:
        if (p, a) not in existentes_set:
            session.add(AsignacionDiaria(fecha=dia, puesto_id=p, almacen_id=a))
    session.commit()

    return _redir(f"/admin/asignaciones?fecha={dia.isoformat()}")
