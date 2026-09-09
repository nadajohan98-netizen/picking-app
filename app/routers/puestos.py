"""
Selección de puesto y bloqueo en tiempo real (Fase 4).

- GET  /puestos           -> pantalla con la lista de puestos
- WS   /ws/puestos        -> canal en vivo: quién ocupa qué

El WebSocket lo usan DOS pantallas:
  * la de selección (solo escucha, para atenuar los ocupados)
  * la del puesto (además envía "abrir" para tomar el candado)
"""

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from app.auth import SESSION_USER_KEY, get_current_user
from app.database import get_session
from app.models import Puesto, Rol, Usuario
from app.services.locks import lock_manager
from app.templating import templates

router = APIRouter()


@router.get("/puestos")
def pantalla_puestos(
    request: Request,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    puestos = session.exec(select(Puesto).order_by(Puesto.numero)).all()
    return templates.TemplateResponse(
        request,
        "puestos.html",
        {
            "user": user,
            "puestos": puestos,
            "ocupados": lock_manager.snapshot(),
        },
    )


@router.websocket("/ws/puestos")
async def ws_puestos(websocket: WebSocket, session: Session = Depends(get_session)):
    # La cookie de sesión viaja también en el handshake del WebSocket.
    user_id = websocket.session.get(SESSION_USER_KEY)
    user = session.get(Usuario, user_id) if user_id else None
    if user is None or not user.activo:
        await websocket.close(code=4401)  # no autenticado
        return

    await lock_manager.connect(websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            accion = msg.get("accion")

            if accion == "abrir":
                puesto_id = int(msg["puesto_id"])
                if user.rol not in (Rol.operario, Rol.administrador):
                    await websocket.send_json({"type": "rechazado", "motivo": "rol"})
                    continue
                ok = await lock_manager.acquire(websocket, puesto_id, user.id)
                await websocket.send_json(
                    {"type": "abierto" if ok else "rechazado", "puesto_id": puesto_id}
                )

            elif accion == "cerrar":
                await lock_manager.release(websocket)
                await websocket.send_json({"type": "cerrado"})

    except WebSocketDisconnect:
        pass
    finally:
        await lock_manager.disconnect(websocket)
