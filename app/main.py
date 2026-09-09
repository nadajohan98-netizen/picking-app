"""
Aplicación web de picking.

Arrancar en desarrollo:   py run.py
Luego abrir:              http://127.0.0.1:8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler as default_http_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.routers import admin, auth, catalogos, picking, puestos, supervisor
from app.security import get_secret_key
from app.services.locks import cerrar_todas_las_sesiones
from app.templating import templates

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar: limpiar candados de puestos que quedaron colgados de una
    # ejecución anterior (no puede haber ningún WebSocket vivo todavía).
    cerrar_todas_las_sesiones()
    yield


app = FastAPI(title="App de Picking", lifespan=lifespan)

# Cookie de sesión firmada.
app.add_middleware(SessionMiddleware, secret_key=get_secret_key())

# Archivos estáticos (CSS, JS, Tabulator).
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Rutas, agrupadas por tema.
app.include_router(auth.router)
app.include_router(puestos.router)
app.include_router(picking.router)
app.include_router(admin.router)
app.include_router(catalogos.router)
app.include_router(supervisor.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Para el 403 mostramos una página; para todo lo demás, el comportamiento
    normal de FastAPI (incluidas las redirecciones 303 a /login)."""
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        return templates.TemplateResponse(
            request, "403.html", {"detail": exc.detail}, status_code=exc.status_code
        )
    return await default_http_handler(request, exc)
