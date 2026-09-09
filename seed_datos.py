"""
Datos de ejemplo para probar la app (puestos, almacenes, materiales, lotes,
asignación de hoy y líneas de picking de hoy).

Se llama desde `manage.py seed` / `manage.py reset`. Es idempotente: si algo ya
existe, no lo duplica.

En la operación real, las líneas de picking vendrían del "pedido" del día; acá
las ponemos a mano.
"""

from datetime import date

from sqlmodel import Session, select

from app.database import engine
from app.models import (
    Almacen,
    AsignacionDiaria,
    LineaPicking,
    Lote,
    Material,
    Puesto,
    TipoUnidad,
)

PUESTOS = [1, 2, 3, 4, 5, 6, 8, 10, 11]

ALMACENES = [
    ("091", "Éxito Occidente"),
    ("092", "Éxito Norte"),
    ("105", "Carulla 85"),
    ("210", "Jumbo Calle 80"),
    ("305", "Olímpica Cali"),
]

MATERIALES = [
    ("100234", "Pechuga de pollo fresca", TipoUnidad.kilogramo),
    ("100235", "Muslo contramuslo", TipoUnidad.kilogramo),
    ("100236", "Alas de pollo", TipoUnidad.kilogramo),
    ("100240", "Carne molida de res", TipoUnidad.kilogramo),
    ("100241", "Lomo fino de res", TipoUnidad.kilogramo),
    ("200110", "Salchicha ranchera x 5", TipoUnidad.unidad),
    ("200111", "Jamón de cerdo tajado x 250g", TipoUnidad.unidad),
    ("200112", "Chorizo santarrosano x 4", TipoUnidad.unidad),
    ("200113", "Costilla de cerdo ahumada", TipoUnidad.kilogramo),
    ("200120", "Tocineta americana x 200g", TipoUnidad.unidad),
]

LOTES = [
    "L240901", "L240902", "L240903", "L240905", "L240908",
    "L240910", "L240912", "L240915", "L240918", "L240920",
    "LP2409A", "LP2409B", "LR2408X", "LC2409M", "LC2409N",
]

# líneas de HOY: (puesto, almacén, material, pedida, pesos_ya_piqueados)
# los pesos solo aplican a materiales KG; para UN se deja []
LINEAS = [
    (1, "091", "100234", 120, [15.986, 14.220, 13.5]),
    (1, "091", "100240", 80, [7.506]),
    (1, "091", "200110", 60, []),
    (1, "091", "200111", 45, []),
    (1, "092", "100235", 95, []),
    (1, "092", "100241", 30, [12.100]),
    (1, "092", "200112", 24, []),
    (1, "092", "200120", 18, []),
    (2, "105", "100236", 40, []),
    (2, "105", "200113", 22, []),
    (2, "105", "100234", 55, []),
]

ASIGNACIONES = [(1, "091"), (1, "092"), (2, "105"), (3, "305")]


def _get_or_create(session, modelo, defaults=None, **claves):
    obj = session.exec(select(modelo).filter_by(**claves)).first()
    if obj:
        return obj
    obj = modelo(**claves, **(defaults or {}))
    session.add(obj)
    session.flush()
    return obj


def cargar_datos_demo() -> None:
    hoy = date.today()
    with Session(engine) as session:
        for numero in PUESTOS:
            _get_or_create(session, Puesto, numero=numero)
        for codigo, nombre in ALMACENES:
            _get_or_create(session, Almacen, {"nombre": nombre}, codigo=codigo)
        for codigo, desc, unidad in MATERIALES:
            _get_or_create(
                session, Material,
                {"descripcion": desc, "tipo_unidad": unidad},
                codigo=codigo,
            )
        for codigo in LOTES:
            _get_or_create(session, Lote, codigo=codigo)
        session.commit()

        puestos = {p.numero: p for p in session.exec(select(Puesto)).all()}
        almacenes = {a.codigo: a for a in session.exec(select(Almacen)).all()}
        materiales = {m.codigo: m for m in session.exec(select(Material)).all()}

        for pnum, acod in ASIGNACIONES:
            _get_or_create(
                session, AsignacionDiaria, fecha=hoy,
                puesto_id=puestos[pnum].id, almacen_id=almacenes[acod].id,
            )

        for pnum, acod, mcod, pedida, pesos in LINEAS:
            existe = session.exec(
                select(LineaPicking).where(
                    LineaPicking.fecha == hoy,
                    LineaPicking.puesto_id == puestos[pnum].id,
                    LineaPicking.almacen_id == almacenes[acod].id,
                    LineaPicking.material_id == materiales[mcod].id,
                )
            ).first()
            if existe:
                continue
            es_kg = materiales[mcod].tipo_unidad is TipoUnidad.kilogramo
            pesos_ok = [round(p, 3) for p in pesos] if es_kg else []
            session.add(
                LineaPicking(
                    fecha=hoy,
                    puesto_id=puestos[pnum].id,
                    almacen_id=almacenes[acod].id,
                    material_id=materiales[mcod].id,
                    cantidad_pedida=pedida,
                    pesos=pesos_ok,
                    cantidad_despachada=round(sum(pesos_ok), 3),
                    canastillas=len(pesos_ok),
                )
            )
        session.commit()
