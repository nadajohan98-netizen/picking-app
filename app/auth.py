"""
Autenticación y autorización con FastAPI.

- Autenticación = "¿quién eres?"  -> `get_current_user`
- Autorización  = "¿puedes entrar aquí?" -> `require_roles`

Ambas se usan como DEPENDENCIAS: se ponen en la firma de una ruta con
`Depends(...)` y FastAPI las ejecuta antes que la ruta. Si lanzan una excepción,
la ruta ni siquiera corre.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.database import get_session
from app.models import Rol, Usuario

# Nombre de la clave donde guardamos el id del usuario dentro de la cookie de sesión.
SESSION_USER_KEY = "user_id"


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Usuario:
    """Devuelve el usuario de la sesión activa, o redirige a /login si no hay.

    Una redirección se hace lanzando una HTTPException 303 con la cabecera
    `Location`: el navegador la sigue y termina en la pantalla de login.
    """
    redirect_to_login = HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/login"},
    )

    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        raise redirect_to_login

    user = session.get(Usuario, user_id)
    if user is None or not user.activo:
        request.session.clear()  # cookie inválida: la borramos
        raise redirect_to_login

    return user


def require_roles(*allowed: Rol) -> Callable[..., Usuario]:
    """Crea una dependencia que solo deja pasar a ciertos roles.

    El administrador siempre pasa (en el plan, "puede hacer todo lo anterior").
    """

    def dependency(user: Usuario = Depends(get_current_user)) -> Usuario:
        if user.rol is not Rol.administrador and user.rol not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder a esta página.",
            )
        return user

    return dependency
