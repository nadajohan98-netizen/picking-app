"""
Bloqueo de puestos en tiempo real (Fase 4).

Idea: mientras un operario tiene abierta la pantalla de un puesto, su navegador
mantiene una conexión WebSocket viva con el servidor. Esa conexión ES el
candado: si el operario cierra la pestaña, se va la luz o se cae la red, la
conexión se corta y el servidor libera el puesto automáticamente.

- `holds`      : puesto_id -> usuario_id  (quién tiene el candado ahora mismo)
- `_conns`     : todas las conexiones abiertas (pantallas de selección Y de puesto)
- `_conn_hold` : qué puesto tiene tomado cada conexión, para soltarlo al cerrarse

Además se deja rastro en la tabla SesionPuesto (para el "quién y cuándo"), pero
la autoridad del candado en vivo es este objeto en memoria.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import WebSocket
from sqlmodel import Session, select

from app.database import engine
from app.models import SesionPuesto


class PuestoLockManager:
    def __init__(self) -> None:
        self.holds: dict[int, int] = {}
        self._conns: set[WebSocket] = set()
        self._conn_hold: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    # -- conexiones ---------------------------------------------------------
    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._conns.add(ws)
        await self._send_state(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        self._conns.discard(ws)
        puesto_id = self._conn_hold.pop(ws, None)
        if puesto_id is not None and self.holds.get(puesto_id) is not None:
            del self.holds[puesto_id]
            _cerrar_sesion_db(puesto_id)
            await self.broadcast_state()

    # -- candado ----------------------------------------------------------
    async def acquire(self, ws: WebSocket, puesto_id: int, usuario_id: int) -> bool:
        """Intenta tomar el puesto. Devuelve True si lo logró."""
        async with self._lock:
            actual = self.holds.get(puesto_id)
            if actual is not None and actual != usuario_id:
                return False
            self.holds[puesto_id] = usuario_id
            self._conn_hold[ws] = puesto_id
        _abrir_sesion_db(puesto_id, usuario_id)
        await self.broadcast_state()
        return True

    async def release(self, ws: WebSocket) -> None:
        puesto_id = self._conn_hold.pop(ws, None)
        if puesto_id is not None and puesto_id in self.holds:
            del self.holds[puesto_id]
            _cerrar_sesion_db(puesto_id)
            await self.broadcast_state()

    # -- difusión --------------------------------------------------------
    async def broadcast_state(self) -> None:
        for ws in list(self._conns):
            await self._send_state(ws)

    async def _send_state(self, ws: WebSocket) -> None:
        try:
            await ws.send_json({"type": "estado", "ocupados": self.holds})
        except Exception:
            self._conns.discard(ws)

    def snapshot(self) -> dict[int, int]:
        return dict(self.holds)


def _abrir_sesion_db(puesto_id: int, usuario_id: int) -> None:
    with Session(engine) as session:
        session.add(
            SesionPuesto(puesto_id=puesto_id, usuario_id=usuario_id)
        )
        session.commit()


def _cerrar_sesion_db(puesto_id: int) -> None:
    with Session(engine) as session:
        abiertas = session.exec(
            select(SesionPuesto).where(
                SesionPuesto.puesto_id == puesto_id,
                SesionPuesto.hora_fin.is_(None),  # type: ignore[union-attr]
            )
        ).all()
        for s in abiertas:
            s.hora_fin = datetime.now()
            session.add(s)
        session.commit()


def cerrar_sesiones_de_usuario(usuario_id: int) -> None:
    """Suelta en memoria y en la BD todos los puestos que tenga ese usuario.

    Se usa al cerrar sesión. El WebSocket, si seguía abierto, se cerrará solo
    poco después y no encontrará nada que soltar.
    """
    for puesto_id, dueno in list(lock_manager.holds.items()):
        if dueno == usuario_id:
            del lock_manager.holds[puesto_id]
            _cerrar_sesion_db(puesto_id)
    for ws, puesto_id in list(lock_manager._conn_hold.items()):
        if lock_manager.holds.get(puesto_id) is None:
            lock_manager._conn_hold.pop(ws, None)
    # Aviso a las pantallas conectadas (best-effort, sin bloquear el logout).
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(lock_manager.broadcast_state())
    except RuntimeError:
        pass


def cerrar_todas_las_sesiones() -> None:
    """Al arrancar el servidor: no hay ningún WebSocket vivo todavía, así que
    cualquier SesionPuesto sin hora_fin quedó colgada de una ejecución anterior."""
    with Session(engine) as session:
        colgadas = session.exec(
            select(SesionPuesto).where(SesionPuesto.hora_fin.is_(None))  # type: ignore[union-attr]
        ).all()
        for s in colgadas:
            s.hora_fin = datetime.now()
            session.add(s)
        session.commit()


# Instancia única para toda la app.
lock_manager = PuestoLockManager()
