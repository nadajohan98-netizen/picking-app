# App de Picking

App web local que reemplaza una hoja de Excel compartida para el picking de
cárnicos. Varios operarios trabajan a la vez desde PCs distintos, en la red del
punto, sin depender de internet. Objetivo y alcance completos en
`plan-app-picking.md`.

## Stack

- **Backend:** Python 3.13 + FastAPI + SQLModel (SQLAlchemy) + Uvicorn.
- **Base de datos:** SQLite, un archivo `picking.db`.
- **Frontend:** plantillas Jinja2 + JS vanilla + Tabulator.js (vendorizado en
  `app/static/vendor/`, sin CDN — la app corre offline).
- **Tiempo real:** WebSocket (`/ws/puestos`) para el bloqueo de puestos.
- Sin build step, sin npm. El diseño es "hoja de cálculo mejorada" (claro por
  defecto, tema claro/oscuro/automático). Tipografías IBM Plex Sans/Mono.

## Correr

```
py -m venv .venv                     # una vez
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py reset    # crea BD + datos de prueba
.venv\Scripts\python.exe run.py             # servidor en http://127.0.0.1:8000
```

`manage.py` tiene subcomandos: `init` (crear tablas), `seed` (datos demo),
`reset` (borrar + recrear + seed). Usuarios demo: `usuario1/1001` (operario),
`usuario2/1002` (supervisor), `admin/1003` (administrador); la contraseña
inicial es la cédula.

Entorno de desarrollo: **Windows, sin git al inicio**. El tool Bash está roto en
esta máquina — usar PowerShell. `python` no está en PATH, usar `py` o
`.venv\Scripts\python.exe`. No matar procesos python filtrando por "uvicorn"
(mata el server bueno); filtrar por `app.main:app` o por PID.

## Estructura

```
app/
  main.py            arma la FastAPI app, middleware de sesión, monta routers y estáticos
  models.py          todas las tablas SQLModel
  database.py        engine + get_session (dependencia) + create_db_and_tables
  security.py        hash de contraseña (pbkdf2 de la stdlib) + secret key
  auth.py            get_current_user / require_roles (dependencias de FastAPI)
  templating.py      objeto Jinja2Templates compartido
  routers/
    auth.py          /login /logout /inicio (redirige según rol)
    puestos.py       /puestos (solo puestos activos) + WebSocket /ws/puestos
    picking.py       /picking/{id} + API de la grilla (lineas, pesos, kpis, lotes, config)
    admin.py         /admin, /admin/config, /admin/usuarios (crear/editar/toggle/reset)
    catalogos.py     /admin/{lotes,materiales,almacenes,puestos,asignaciones} — CRUD
    supervisor.py    /supervisor, /api/supervisor/resumen,
                     /supervisor/puesto/{id} (solo lectura), /supervisor/cierre (imprimible)
  services/
    configuracion.py  fila única de Configuracion, con caché en memoria
    kpis.py           calcula la barra de KPIs a partir de las líneas
    vencimiento.py    valida y clasifica (ok/pronto/vencido) la fecha
    locks.py          PuestoLockManager: candado en memoria + rastro en SesionPuesto
    tabla_import.py   lee .xlsx/.csv a lista de dicts por encabezado
    lotes_import.py / materiales_import.py   usan tabla_import
  templates/         base.html -> app.html -> páginas
  static/            css/app.css (tokens de tema), js/*.js, vendor/tabulator.*
manage.py            utilidades de BD (dev)
seed_datos.py        datos de ejemplo (lo usa manage.py)
run.py               arranca uvicorn con --reload
```

## Decisiones y reglas clave

- **Diferencia y KPIs se calculan, no se guardan** (evita inconsistencias).
- **Líneas KG** se piquean por canastilla: `LineaPicking.pesos` es una columna
  JSON con la lista de pesos. `cantidad_despachada = sum(pesos)` y
  `canastillas = len(pesos)` se recalculan al guardar (`PUT /api/lineas/{id}/pesos`).
  Escribir `cantidad_despachada` a mano en una línea KG se rechaza (422).
- **Líneas UN** no se piquean: el operario escribe el total a mano en la celda
  "Desp." (`PATCH /api/lineas/{id}` campo `cantidad_despachada`).
- **Código de barras: solo trae el peso** (no identifica material). El parseo se
  hace en el cliente con los parámetros de `/api/config`; el servidor solo valida
  la tolerancia al guardar. El operario elige material y lote a mano.
- **Tolerancia:** no se puede pasar de lo pedido más de `tolerancia_pct` %.
- **Todo lo configurable vive en la tabla `Configuracion`** (una fila, id=1),
  editable en `/admin/config`: formato del código, tolerancia, días de
  vencimiento, meta de cumplimiento, timeout de sesión. NO hay `app/config.py`.
- **Bloqueo de puestos:** el candado vive mientras el WebSocket está abierto. Si
  se cae la pestaña/red/luz, se libera solo. Al arrancar el server se cierran las
  `SesionPuesto` colgadas.
- **Puestos** se muestran como "01, 02, 03…" sin región (`Puesto.descripcion`
  existe en el modelo pero no se usa).
- `Puesto`, `Almacen`, `Material` tienen `activo`. Un puesto/almacén inactivo no
  aparece para elegir/asignar; los materiales inactivos sí siguen en líneas
  históricas (el flag es informativo + para el futuro "crear pedido").
- **Roles:** el admin siempre pasa `require_roles` (ve todo). El supervisor ve el
  panel + detalle de puestos en solo lectura + el cierre imprimible; NO toca
  catálogos, usuarios ni configuración. El operario solo su puesto.
- Al **editar un usuario**, cambiar la cédula reinicia su contraseña a la nueva
  cédula (si no, el hash de la vieja quedaría mal).
- Autoguardado en cada cambio: no hay botón "guardar" en la grilla.
- Trazabilidad automática: cada escritura guarda `editado_por_id` + `actualizado_en`.

## Roadmap (plan-app-picking.md, sección 9)

Fases 0–7 construidas. Falta pulir según feedback del usuario y decidir mejoras
futuras (sección 10 del plan: forzar cambio de contraseña, ubicación física de
productos, columnas RU / COD_UCR).

## Al trabajar en este repo

- El usuario está aprendiendo Python: explicar brevemente qué se construye, por
  qué y qué conceptos nuevos aparecen, antes de escribir código de una fase nueva.
- Seguir el roadmap en orden, sin adelantar fases.
- Al terminar algo, decir cómo probarlo.
- Si algo del plan no está claro o hay mejor forma, preguntar antes de decidir.
- Probar los cambios (HTTP + navegador) antes de darlos por hechos.
