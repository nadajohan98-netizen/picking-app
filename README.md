# App de Picking

Reemplazo de la hoja de Excel compartida para el picking de cárnicos: cuadrícula
tipo hoja de cálculo, validaciones, autoguardado, bloqueo de puestos en tiempo
real y trazabilidad automática de quién editó cada línea.

Corre en la red local del punto, sin internet.

## Requisitos

- Python 3.13 (en Windows: el comando es `py`).

## Instalación

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Base de datos

```bat
.venv\Scripts\python.exe manage.py reset
```

Crea `picking.db` con las tablas y datos de prueba. Subcomandos:

| Comando | Qué hace |
|---|---|
| `manage.py init`  | Crea las tablas que falten (no borra nada). |
| `manage.py seed`  | Carga usuarios y datos de ejemplo. |
| `manage.py reset` | Borra la base, la recrea y la vuelve a llenar. |

## Correr

```bat
.venv\Scripts\python.exe run.py
```

Abrí **http://127.0.0.1:8000**. Para pararlo: `Ctrl+C`.

Usuarios de prueba (contraseña = cédula):

| Usuario | Contraseña | Rol |
|---|---|---|
| `usuario1` | `1001` | Operario |
| `usuario2` | `1002` | Supervisor |
| `admin`   | `1003` | Administrador |

## Cómo funciona el picking

- **Materiales en KG:** se piquea canastilla por canastilla. Clic en una casilla
  de la columna "Piqueo", se escribe el peso, `Enter` confirma y salta a la
  siguiente. La app suma los pesos y cuenta las canastillas.
- **Peso del código de barras:** en la barra de arriba, se teclean (o escanean)
  los dígitos del código y `Enter` mete ese peso en la casilla seleccionada.
- **Materiales en UN:** se escribe el total a mano en la celda "Desp.".
- No se puede pasar de lo pedido más del margen de tolerancia (configurable).

## Configuración

El administrador ajusta todas las reglas en **Administración → Configuración**
sin tocar código: formato del código de barras, tolerancia, rango de
vencimientos, meta de cumplimiento, timeout de sesión.

## Arquitectura

FastAPI + SQLModel + SQLite en el backend; Jinja2 + JavaScript vanilla +
Tabulator.js en el frontend. Sin build step. Ver `CLAUDE.md` para el detalle de
la estructura y las decisiones de diseño, y `plan-app-picking.md` para el plan
original.
