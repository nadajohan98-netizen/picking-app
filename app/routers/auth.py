"""Rutas públicas: login y logout."""

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import SESSION_USER_KEY, get_current_user
from app.database import get_session
from app.models import Rol, Usuario
from app.security import verify_password
from app.services.locks import cerrar_sesiones_de_usuario
from app.templating import templates

router = APIRouter()

# A dónde mandamos a cada rol después de entrar.
HOME_BY_ROLE = {
    Rol.operario: "/puestos",
    Rol.supervisor: "/supervisor",
    Rol.administrador: "/admin",
}


@router.get("/", include_in_schema=False)
def index(request: Request):
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/inicio", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/inicio", include_in_schema=False)
def inicio(user: Usuario = Depends(get_current_user)):
    return RedirectResponse(
        HOME_BY_ROLE[user.rol], status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    usuario = session.exec(
        select(Usuario).where(Usuario.username == username)
    ).first()

    if (
        usuario is None
        or not usuario.activo
        or not verify_password(password, usuario.hashed_password)
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Usuario o contraseña incorrectos."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session[SESSION_USER_KEY] = usuario.id
    return RedirectResponse(
        HOME_BY_ROLE[usuario.rol], status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/logout", include_in_schema=False)
def logout(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is not None:
        # Al cerrar sesión, soltamos cualquier puesto que tuviera abierto.
        cerrar_sesiones_de_usuario(user_id)
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
