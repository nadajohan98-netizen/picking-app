"""
Panel de administrador: índice, configuración y usuarios.

Los catálogos (lotes, materiales, almacenes, puestos, asignaciones) están en
`app/routers/catalogos.py`.
"""

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import require_roles
from app.database import get_session
from app.models import Rol, Usuario
from app.security import hash_password
from app.services.configuracion import actualizar_config, get_config
from app.templating import templates

router = APIRouter(prefix="/admin")
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


@router.post("/usuarios/{usuario_id}/editar")
def editar_usuario(
    usuario_id: int,
    actor: Usuario = solo_admin,
    session: Session = Depends(get_session),
    cedula: str = Form(...),
    rol: Rol = Form(...),
    reiniciar: str | None = Form(None),
):
    u = session.get(Usuario, usuario_id)
    if u:
        cedula = cedula.strip()
        cambio_cedula = cedula != u.cedula
        u.cedula = cedula
        # No dejamos que el admin se quite a sí mismo el rol de administrador.
        if not (u.id == actor.id and rol is not Rol.administrador):
            u.rol = rol
        if reiniciar or cambio_cedula:
            u.hashed_password = hash_password(cedula)
        session.add(u)
        session.commit()
    return _redir_usuarios("Usuario actualizado.")


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
