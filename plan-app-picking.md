# Plan de arquitectura — App de Picking

Documento de trabajo para construir la app en Claude Code. Resume lo conversado: el problema, el alcance, el modelo de datos, la arquitectura recomendada, las pantallas y el orden sugerido de construcción.

## 1. Resumen y objetivo

Hoy el picking se hace en una hoja de Excel compartida entre varios operarios, cada uno desde su propio computador. Eso genera errores costosos y sin trazabilidad clara:

- Lotes escritos a mano, con errores de digitación.
- Fechas de vencimiento mal ingresadas.
- Fórmulas borradas por accidente (Ctrl+X).
- El archivo a veces no guarda solo; si se va la luz o el internet, se pierde el trabajo.
- La cédula de quien hizo cada línea se anota a mano después, por un superior — no queda un registro confiable de quién editó qué.
- Varios operarios trabajan al mismo tiempo sobre el mismo archivo y se coordinan manualmente (hablando entre ellos) para no pisarse el trabajo en el mismo "puesto".

**Objetivo:** reemplazar esa hoja compartida por una aplicación propia, con la misma lógica visual de cuadrícula tipo Excel (para que el personal actual no tenga que reaprender nada), pero que valide los datos, autocomplete lo repetitivo, guarde todo al instante, evite que dos personas trabajen el mismo puesto a la vez, y registre automáticamente quién hizo cada cambio.

## 2. Alcance

### Incluido en la primera versión (MVP)

- Login con usuario genérico (usuario1, usuario2...) y contraseña inicial = cédula de la persona.
- Tres roles: Operario, Supervisor, Administrador.
- Selección de puesto después de iniciar sesión; el puesto queda bloqueado/ocupado mientras alguien lo está trabajando, para que nadie más lo abra al mismo tiempo.
- Cuadrícula de picking por puesto, con: Almacén, Material, Unidad (UN o KG según el producto), Cantidad pedida, Cantidad despachada, Lote (con autocompletado), Vencimiento (validado), Canastillas, Unidades, Diferencia/faltante.
- Catálogo interno de lotes válidos, cargado por el administrador (por ejemplo arrastrando una hoja Excel), para evitar lotes mal escritos.
- Autocompletado de lote: al escribir iniciales aparecen coincidencias; se navega con Tab/flechas y se confirma con Enter; Tab también avanza de fila.
- Asignación diaria de qué almacenes le corresponden a cada puesto, editable por el administrador (porque cambia día a día).
- Validación de fecha de vencimiento: solo fechas reales, dentro de un rango razonable (los cárnicos no duran más de ~2 meses); aviso visual cuando la fecha está próxima, para que los supervisores prioricen el envío.
- Barra de KPIs por puesto, igual a la que ya usan: Total Pedido, Total Despachado, % Cumplimiento, % Faltante, Total Unidades, Total Pendiente.
- Registro automático de qué usuario editó cada línea (ya no se digita la cédula a mano).
- Guardado automático de cada cambio, sin botón "guardar" y sin depender de que no se corte la luz o el internet.
- Modo oscuro / claro, alternable.

### Fuera de alcance por ahora

- Integración con SAP o SAT (se descartó: la app es independiente).
- Seguimiento de ubicación física de los productos (idea para más adelante, aún sin definir cómo).
- Forzar cambio de contraseña en el primer ingreso (mejora de seguridad pendiente de decidir).
- Las columnas de la hoja actual que ni siquiera en el proceso de hoy están claras (RU, # COD_UCR, las columnas numeradas 1, 2, 3... de picking secuencial). No se replican en el MVP; si más adelante se identifica para qué sirven realmente, se agregan.

## 3. Roles y usuarios

| Rol | Qué puede hacer |
|---|---|
| Operario | Ve y edita solo el/los puestos que tiene abiertos: lote, vencimiento, cantidad despachada, canastillas. |
| Supervisor | Ve todos los puestos, recibe las alertas de vencimiento próximo, supervisa el cumplimiento con los KPIs. |
| Administrador | Todo lo anterior, más: carga y edita el catálogo de lotes válidos, edita la asignación diaria de almacenes por puesto, crea y administra usuarios. |

Login: nombre de usuario genérico (no la cédula, para no exponerla) + contraseña inicial igual a la cédula de cada persona.

## 4. Modelo de datos (entidades principales)

- **Usuario**: id, nombre de usuario, cédula, rol, contraseña (hash), activo/inactivo.
- **Puesto**: id, número (1, 2, 3, 4, 5, 6, 8, 10, 11, 22, 44...), región o descripción (ej. "Bogotá", "Satélites", "Cali", "Medellín").
- **Almacén**: id, código, nombre (ej. "091 - Éxito Occidente").
- **AsignaciónDiariaPuestoAlmacén**: fecha, puesto, almacén — refleja que la relación puesto↔almacén cambia día a día.
- **Lote**: código, fecha de registro, activo — catálogo maestro cargado por el administrador.
- **Producto/Material**: código, descripción, tipo de unidad (UN o KG).
- **LíneaPicking**: fecha, puesto, almacén, material, cantidad pedida, cantidad despachada, lote, fecha de vencimiento, canastillas, unidades, usuario que editó, hora de la última edición.
- **SesiónPuesto**: puesto, usuario, fecha, hora de inicio, hora de fin — controla el bloqueo/ocupación en tiempo real.

## 5. Reglas de negocio clave

- Un puesto solo puede estar ocupado por un usuario a la vez; se libera cuando esa persona cierra ese puesto o cierra sesión.
- El lote se elige de un catálogo (autocompletado); no se permite escribirlo libremente.
- La fecha de vencimiento debe ser real y estar en un rango razonable; si está próxima a vencer, se resalta para los supervisores.
- La unidad (UN o KG) la define el producto, no la escoge el operario.
- Cada edición se asocia automáticamente al usuario de la sesión activa.
- Cada cambio se guarda de inmediato; no existe un estado "sin guardar" que se pueda perder.

## 6. Arquitectura técnica recomendada

Contexto que define la arquitectura:

- Varios operarios trabajan a la vez, desde computadores distintos, sobre los mismos datos.
- Los computadores del punto son de gama baja / lentos.
- El usuario está aprendiendo Python y quiere entender y construir el código él mismo.

**Recomendación: aplicación web local, tipo cliente-servidor, dentro de la red del punto (sin depender de internet).**

- **Backend**: Python con FastAPI — liviano, natural viniendo de Python puro, y con soporte para WebSockets (comunicación en tiempo real), útil para que todos vean al instante qué puesto está ocupado.
- **Base de datos**: SQLite para empezar — un solo archivo, sin necesidad de instalar un servidor de base de datos aparte, más que suficiente para un punto. Se puede migrar a PostgreSQL más adelante si el proyecto crece a varios puntos a la vez.
- **Frontend**: HTML + JavaScript simple, con una librería de cuadrícula tipo Excel ligera (por ejemplo Tabulator.js, que tiene versión gratuita). Se evita a propósito un framework pesado (React completo, Angular) para que la app cargue rápido en equipos lentos.
- Cada operario abre la app desde el navegador de su propio computador, apuntando a la dirección del computador que actúa de servidor (puede ser el mismo equipo del administrador, o uno dedicado).

Con esta arquitectura, tres problemas se resuelven "gratis", por cómo funciona el diseño, sin trabajo extra:

- **Guardado**: cada cambio se escribe de inmediato en la base de datos — no hay archivo que se corrompa a mitad de una escritura por un corte de luz.
- **Bloqueo de puestos**: el servidor sabe en todo momento quién tiene abierto cada puesto.
- **Trazabilidad**: cada escritura queda ligada al usuario de la sesión activa, sin digitar nada a mano.

## 7. Pantallas

1. **Login** — usuario + contraseña.
2. **Selección de puesto** — lista de puestos disponibles; los ocupados aparecen bloqueados/atenuados.
3. **Cuadrícula de picking** — la pantalla principal, tipo Excel, para el puesto elegido.
4. **Panel de supervisor** — KPIs generales, alertas de vencimiento, todos los puestos.
5. **Panel de administrador** — carga de lotes, asignación diaria de almacenes por puesto, gestión de usuarios.

## 8. Autoguardado y resiliencia

Cada cambio en una celda se envía y se confirma contra la base de datos en el momento — no existe un archivo único que se pueda corromper a medio guardar, como pasa hoy con el Excel. Al ser un servidor local (misma red del punto), tampoco depende de que haya internet para funcionar; internet solo haría falta si en el futuro se quisiera acceso remoto.

## 9. Roadmap sugerido de construcción

Pensado para ir avanzando en pasos pequeños y probables dentro de Claude Code:

1. **Fase 0** — Modelo de datos: crear la base de datos y las tablas vacías.
2. **Fase 1** — Login básico y roles (todavía sin bloqueo de puestos).
3. **Fase 2** — Cuadrícula de picking básica para un puesto, con datos de prueba cargados a mano (sin autocompletado ni validaciones aún).
4. **Fase 3** — Autocompletado de lotes + validación de fecha de vencimiento + aviso visual.
5. **Fase 4** — Selección de puesto + bloqueo/ocupación en tiempo real.
6. **Fase 5** — Panel de administrador: carga de lotes y asignación diaria de almacenes.
7. **Fase 6** — Barra de KPIs y panel de supervisor.
8. **Fase 7** — Modo oscuro/claro, atajos de teclado, pulido visual general.

## 10. Preguntas abiertas para más adelante

- ¿Forzar el cambio de contraseña en el primer ingreso de cada usuario?
- ¿Cómo registrar la ubicación física de los productos, si se decide incluirla?
- ¿Para qué sirven realmente las columnas RU, # COD_UCR y las numeradas de picking secuencial? Se evalúan si en algún momento hacen falta.

## 11. Prompt inicial para Claude Code

No hace falta ninguna skill especial para este proyecto: es una app web estándar (Python + base de datos + HTML/JS), algo que Claude Code puede construir con sus capacidades normales. Lo único que necesitas es este archivo (`plan-app-picking.md`) dentro de la carpeta del proyecto, y darle a Claude Code un primer mensaje claro. Puedes copiar y pegar esto tal cual, o ajustarlo a tu gusto:

```
Quiero que me ayudes a construir, paso a paso, la aplicación de picking descrita
en el archivo plan-app-picking.md de este proyecto. Léelo primero completo antes
de escribir nada.

Reglas para trabajar conmigo:
- Estoy aprendiendo Python y quiero entender cada parte del código, no solo
  recibirlo. Antes de escribir código en cada fase, explícame brevemente qué
  vamos a construir, por qué, y qué conceptos nuevos aparecen.
- Sigue el roadmap de la sección 9 del plan, fase por fase, en orden. No
  adelantes trabajo de fases futuras aunque parezca más eficiente.
- Al terminar cada fase, dime cómo probar que funciona antes de seguir con la
  siguiente.
- Si algo del plan no está claro o crees que hay una mejor forma de hacerlo,
  pregúntame antes de decidir por tu cuenta.

Empecemos por la Fase 0: el modelo de datos y la base de datos vacía.
```

Cuando termines una fase y quieras seguir con la siguiente, simplemente dile algo como "sigamos con la Fase 1" — no necesitas repetir todo el contexto, Claude Code ya lo tiene del archivo del plan.
