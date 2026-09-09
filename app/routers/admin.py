"""
Panel de administrador (Fase 5):

- /admin                      -> índice con accesos
- /admin/lotes                -> catálogo de lotes + carga por archivo
- /admin/asignaciones         -> qué almacenes le tocan a cada puesto por día
- /admin/usuarios             -> alta / baja / reinicio de contraseña
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import require_roles
from app.database import get_session
from app.models import (
    Almacen,
    AsignacionDiaria,
    Lote,
    Puesto,
    Rol,
    Usuario,
)
from app.security import hash_password
from app.services.configuracion import actualizar_config, get_config
from app.services.lotes_import import extraer_codigos
from app.templating import templates

router = APIRouter(prefix="/admin")

# Todas las rutas de este router exigen rol administrador.
solo_admin = Depends(require_roles(Rol.administrador))


@router.get("")
def indice(request: Request, user: Usuario = solo_admin):
    return templates.TemplateResponse(request, "admin/indice.html", {"user": user})


# ---------------------------------------------------------------------------
# Configuración (reglas del negocio, editables sin tocar código)
# ---------------------------------------------------------------------------
_CAMPOS_CONFIG_INT = {
    "bc_longitud", "bc_peso_inicio", "bc_peso_digitos", "bc_peso_divisor",
    "venc_max_dias", "venc_alerta_dias", "sesion_timeout_min",
}
_CAMPOS_CONFIG_FLOAT = {"tolerancia_pct", "cumplimiento_objetivo"}


@router.get("/config")
def ver_config(request: Request, user: Usuario = solo_admin, msg: str | None = None):
    return templates.TemplateResponse(
        request, "admin/config.html", {"user": user, "cfg": get_config(), "msg": msg}
    )


@router.post("/config/guardar")
async def guardar_config(request: Request, user: Usuario = solo_admin):
    form = await request.form()
    datos: dict = {}
    for campo in _CAMPOS_CONFIG_INT:
        if campo in form:
            try:
                datos[campo] = int(str(form[campo]).strip())
            except ValueError:
                pass
    for campo in _CAMPOS_CONFIG_FLOAT:
        if campo in form:
            try:
                datos[campo] = float(str(form[campo]).replace(",", ".").strip())
            except ValueError:
                pass
    datos["bc_prefijo"] = str(form.get("bc_prefijo", "")).strip()

    actualizar_config(datos)
    return RedirectResponse(
        "/admin/config?msg=Configuración guardada.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# Catálogo de lotes
# ---------------------------------------------------------------------------
@router.get("/lotes")
def ver_lotes(
    request: Request,
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
    msg: str | None = None,
):
    lotes = session.exec(select(Lote).order_by(Lote.codigo)).all()
    return templates.TemplateResponse(
        request, "admin/lotes.html", {"user": user, "lotes": lotes, "msg": msg}
    )


@router.post("/lotes/cargar")
async def cargar_lotes(
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
    archivo: UploadFile = File(...),
):
    contenido = await archivo.read()
    try:
        codigos = extraer_codigos(archivo.filename or "", contenido)
    except ValueError as e:
        return _redir_lotes(str(e))

    existentes = {l.codigo for l in session.exec(select(Lote)).all()}
    nuevos = 0
    for codigo in codigos:
        if codigo not in existentes:
            session.add(Lote(codigo=codigo))
            existentes.add(codigo)
            nuevos += 1
    session.commit()
    return _redir_lotes(
        f"Archivo leído: {len(codigos)} códigos, {nuevos} nuevos agregados."
    )


@router.post("/lotes/{lote_id}/toggle")
def toggle_lote(
    lote_id: int,
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
):
    lote = session.get(Lote, lote_id)
    if lote:
        lote.activo = not lote.activo
        session.add(lote)
        session.commit()
    return _redir_lotes()


def _redir_lotes(msg: str | None = None) -> RedirectResponse:
    url = "/admin/lotes" + (f"?msg={msg}" if msg else "")
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Asignación diaria puesto <-> almacenes
# ---------------------------------------------------------------------------
@router.get("/asignaciones")
def ver_asignaciones(
    request: Request,
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
    fecha: str | None = None,
):
    dia = date.fromisoformat(fecha) if fecha else date.today()
    puestos = session.exec(select(Puesto).order_by(Puesto.numero)).all()
    almacenes = session.exec(select(Almacen).order_by(Almacen.codigo)).all()

    asignaciones = session.exec(
        select(AsignacionDiaria).where(AsignacionDiaria.fecha == dia)
    ).all()
    # {puesto_id: {almacen_id, ...}}
    actuales: dict[int, set[int]] = {}
    for a in asignaciones:
        actuales.setdefault(a.puesto_id, set()).add(a.almacen_id)

    return templates.TemplateResponse(
        request,
        "admin/asignaciones.html",
        {
            "user": user,
            "fecha": dia.isoformat(),
            "puestos": puestos,
            "almacenes": almacenes,
            "actuales": actuales,
        },
    )


@router.post("/asignaciones/guardar")
async def guardar_asignaciones(
    request: Request,
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
):
    form = await request.form()
    dia = date.fromisoformat(str(form["fecha"]))

    # Los checkboxes marcados llegan como "asg-<puesto_id>-<almacen_id>".
    marcados: set[tuple[int, int]] = set()
    for clave in form.keys():
        if clave.startswith("asg-"):
            _, p, a = clave.split("-")
            marcados.add((int(p), int(a)))

    existentes = session.exec(
        select(AsignacionDiaria).where(AsignacionDiaria.fecha == dia)
    ).all()
    existentes_set = {(e.puesto_id, e.almacen_id): e for e in existentes}

    # Borrar las que se desmarcaron.
    for clave, obj in existentes_set.items():
        if clave not in marcados:
            session.delete(obj)
    # Crear las nuevas.
    for (p, a) in marcados:
        if (p, a) not in existentes_set:
            session.add(AsignacionDiaria(fecha=dia, puesto_id=p, almacen_id=a))
    session.commit()

    return RedirectResponse(
        f"/admin/asignaciones?fecha={dia.isoformat()}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@router.get("/usuarios")
def ver_usuarios(
    request: Request,
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
    msg: str | None = None,
):
    usuarios = session.exec(select(Usuario).order_by(Usuario.username)).all()
    return templates.TemplateResponse(
        request,
        "admin/usuarios.html",
        {"user": user, "usuarios": usuarios, "roles": list(Rol), "msg": msg},
    )


@router.post("/usuarios/crear")
def crear_usuario(
    user: Usuario = solo_admin,
    session: Session = Depends(get_session),
    username: str = Form(...),
    cedula: str = Form(...),
    rol: Rol = Form(...),
):
    username = username.strip()
    if session.exec(select(Usuario).where(Usuario.username == username)).first():
        return _redir_usuarios(f"El usuario '{username}' ya existe.")
    session.add(
        Usuario(
            username=username,
            cedula=cedula.strip(),
            rol=rol,
            hashed_password=hash_password(cedula.strip()),
        )
    )
    session.commit()
    return _redir_usuarios(f"Usuario '{username}' creado (contraseña = cédula).")


@router.post("/usuarios/{usuario_id}/toggle")
def toggle_usuario(
    usuario_id: int,
    actor: Usuario = solo_admin,
    session: Session = Depends(get_session),
):
    u = session.get(Usuario, usuario_id)
    if u and u.id != actor.id:  # no puede desactivarse a sí mismo
        u.activo = not u.activo
        session.add(u)
        session.commit()
    return _redir_usuarios()


@router.post("/usuarios/{usuario_id}/reset")
def reset_password(
    usuario_id: int,
    actor: Usuario = solo_admin,
    session: Session = Depends(get_session),
):
    u = session.get(Usuario, usuario_id)
    if u:
        u.hashed_password = hash_password(u.cedula)
        session.add(u)
        session.commit()
    return _redir_usuarios("Contraseña reiniciada a la cédula.")


def _redir_usuarios(msg: str | None = None) -> RedirectResponse:
    url = "/admin/usuarios" + (f"?msg={msg}" if msg else "")
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
