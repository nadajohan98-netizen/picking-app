"""
Modelo de datos de la app de picking (Fase 0).

Cada clase que hereda de SQLModel y lleva `table=True` se convierte en una TABLA
de la base de datos. Cada atributo de la clase es una COLUMNA de esa tabla.

Ideas clave que se repiten abajo:

- `id: int | None = Field(default=None, primary_key=True)`
  Es la CLAVE PRIMARIA: un número único que identifica cada fila. Lo pone la
  base de datos automáticamente (1, 2, 3...), por eso arranca en None.

- `Field(foreign_key="puesto.id")`
  Es una CLAVE FORÁNEA: esta columna guarda el `id` de una fila de OTRA tabla.
  Así se relacionan las tablas entre sí (una línea de picking "pertenece" a un
  puesto, a un almacén y a un material).

- `Field(index=True)` crea un índice: hace que buscar por esa columna sea rápido.
- `Field(unique=True)` impide que se repita un valor en esa columna.
- `str | None` significa "texto o vacío (NULL)". Sin el `| None`, es obligatorio.
"""

from datetime import date, datetime
from enum import Enum

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Enumeraciones: listas cerradas de valores permitidos.
# En vez de guardar texto libre ("operario", "Operario", "OPERARIO"...),
# obligamos a que el valor sea uno de estos.
# ---------------------------------------------------------------------------
class Rol(str, Enum):
    operario = "operario"
    supervisor = "supervisor"
    administrador = "administrador"


class TipoUnidad(str, Enum):
    unidad = "UN"       # se despacha por unidades enteras
    kilogramo = "KG"    # se despacha por peso


# ---------------------------------------------------------------------------
# Usuario: quién entra a la app.
# ---------------------------------------------------------------------------
class Usuario(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)   # "usuario1", "usuario2"...
    cedula: str                                      # documento de la persona
    rol: Rol                                         # operario / supervisor / administrador
    hashed_password: str                             # la contraseña NUNCA en texto plano
    activo: bool = Field(default=True)               # se "desactiva" en vez de borrar


# ---------------------------------------------------------------------------
# Puesto: cada estación de trabajo de picking (1, 2, 3, 4, 5, 6, 8, 10...).
# ---------------------------------------------------------------------------
class Puesto(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    numero: int = Field(unique=True, index=True)     # el número visible del puesto
    descripcion: str | None = None                   # "Bogotá", "Satélites", "Cali"...


# ---------------------------------------------------------------------------
# Almacén: el punto de venta / bodega de donde se despacha (ej. "091 - Éxito Occidente").
# ---------------------------------------------------------------------------
class Almacen(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(unique=True, index=True)     # "091"
    nombre: str                                      # "Éxito Occidente"


# ---------------------------------------------------------------------------
# AsignacionDiaria: qué almacenes le tocan a cada puesto un día concreto.
# La relación puesto <-> almacén cambia día a día, por eso lleva fecha.
# ---------------------------------------------------------------------------
class AsignacionDiaria(SQLModel, table=True):
    # No tiene sentido asignar el mismo almacén al mismo puesto dos veces el
    # mismo día: esta regla se la imponemos a la base de datos.
    __table_args__ = (
        UniqueConstraint("fecha", "puesto_id", "almacen_id", name="uq_asignacion"),
    )

    id: int | None = Field(default=None, primary_key=True)
    fecha: date = Field(index=True)
    puesto_id: int = Field(foreign_key="puesto.id", index=True)
    almacen_id: int = Field(foreign_key="almacen.id", index=True)


# ---------------------------------------------------------------------------
# Lote: catálogo maestro de lotes válidos, cargado por el administrador.
# El operario elige de aquí (autocompletado); no escribe lotes a mano.
# ---------------------------------------------------------------------------
class Lote(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(unique=True, index=True)
    fecha_registro: date = Field(default_factory=date.today)
    activo: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Material (Producto): qué se despacha. El tipo de unidad (UN/KG) lo define
# el material, no lo escoge el operario.
# ---------------------------------------------------------------------------
class Material(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(unique=True, index=True)
    descripcion: str
    tipo_unidad: TipoUnidad


# ---------------------------------------------------------------------------
# LineaPicking: cada renglón de la cuadrícula de picking. Es la tabla central.
#
# "Diferencia / faltante" NO se guarda como columna: se calcula al mostrarlo
# (cantidad_pedida - cantidad_despachada). Guardar un dato que se puede calcular
# lleva a inconsistencias (que la diferencia no cuadre con las cantidades).
# ---------------------------------------------------------------------------
class LineaPicking(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fecha: date = Field(index=True)

    puesto_id: int = Field(foreign_key="puesto.id", index=True)
    almacen_id: int = Field(foreign_key="almacen.id", index=True)
    material_id: int = Field(foreign_key="material.id", index=True)

    cantidad_pedida: float = Field(default=0)
    # Para líneas KG: se recalcula = suma de `pesos`. Para líneas UN: la escribe
    # el operario a mano. Se guarda (no solo se calcula) para que las consultas
    # de KPIs y del panel de supervisor sean simples y rápidas.
    cantidad_despachada: float = Field(default=0)

    # Piqueo por canastilla (solo líneas KG): el peso de cada canastilla pesada.
    # Es una lista guardada como JSON en una sola columna.
    #   len(pesos)  -> número de canastillas
    #   sum(pesos)  -> cantidad despachada
    pesos: list[float] = Field(default_factory=list, sa_type=JSON)

    # El lote y el vencimiento empiezan vacíos: el operario los completa después.
    lote_id: int | None = Field(default=None, foreign_key="lote.id")
    fecha_vencimiento: date | None = None

    canastillas: int = Field(default=0)   # = len(pesos) en líneas KG

    # Trazabilidad: quién tocó esta línea por última vez y cuándo. Se llena solo.
    editado_por_id: int | None = Field(default=None, foreign_key="usuario.id")
    actualizado_en: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# SesionPuesto: controla el bloqueo. Mientras una fila tenga hora_fin = None,
# ese puesto está OCUPADO por ese usuario y nadie más puede abrirlo.
# ---------------------------------------------------------------------------
class SesionPuesto(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    puesto_id: int = Field(foreign_key="puesto.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fecha: date = Field(default_factory=date.today, index=True)
    hora_inicio: datetime = Field(default_factory=datetime.now)
    hora_fin: datetime | None = None


# ---------------------------------------------------------------------------
# Configuracion: una sola fila (id=1) con todos los parámetros que el
# administrador puede ajustar sin tocar código.
# ---------------------------------------------------------------------------
class Configuracion(SQLModel, table=True):
    id: int | None = Field(default=1, primary_key=True)

    # --- Lectura del código de barras (de ahí sale el peso) ---
    bc_longitud: int = Field(default=13)          # dígitos totales del código
    bc_prefijo: str = Field(default="29")         # prefijo esperado ("" = cualquiera)
    bc_peso_inicio: int = Field(default=8)        # posición (1-based) del primer dígito del peso
    bc_peso_digitos: int = Field(default=5)       # cuántos dígitos ocupa el peso
    bc_peso_divisor: int = Field(default=1000)    # 1000 = el código trae gramos -> kg

    # --- Reglas de despacho ---
    tolerancia_pct: float = Field(default=2.0)    # % que se puede pasar de lo pedido

    # --- Vencimientos ---
    venc_max_dias: int = Field(default=75)
    venc_alerta_dias: int = Field(default=15)

    # --- Cumplimiento ---
    cumplimiento_objetivo: float = Field(default=95.0)

    # --- Sesión de puesto ---
    sesion_timeout_min: int = Field(default=20)
