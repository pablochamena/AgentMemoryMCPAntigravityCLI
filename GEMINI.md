# agent-memory-mcp — Memoria del proyecto

Este proyecto cuenta con un sistema de memoria persistente y contextual. El agente puede recordar, recuperar, modificar y olvidar información relevante para el desarrollo de software.

## Herramientas disponibles

- `remember(title, summary, lesson, tags, related_to?)` — guarda un nuevo recuerdo.
- `recall(query, n, filter_tags?, since?, related_to?)` — busca recuerdos relevantes.
- `modify(memory_id, title?, summary?, lesson?, tags?, related_to?)` — actualiza campos de un recuerdo existente.
- `forget(query)` — borra el recuerdo más similar a la consulta dada.

## Cuándo recordar

Usá `remember` al:
- Tomar una decisión de arquitectura, diseño o dependencia.
- Resolver un bug que requirió más de un intento.
- Identificar un patrón o regla reusable.
- Completar una tarea significativa cuyo contexto valga la pena conservar.

No recuerdes cambios triviales (formateo, renombrar variables), tareas obvias resueltas en un solo paso, ni información que ya está en el código o en este archivo.

## Tags recomendados

Usá al menos uno. Combiná varios cuando corresponda:
`architecture`, `decision`, `bug`, `fix`, `pattern`, `dependency`, `requirement`, `performance`, `security`, `docker`, `testing`, `refactor`.

## Cómo recuperar

Antes de tomar decisiones técnicas, usá `recall` con una consulta en lenguaje natural.
- Si buscás sobre un tema específico, usá `filter_tags` para acotar.
- Si solo querés recuerdos recientes, usá `since` con fecha ISO.
- Si necesitás ver fragmentos relacionados a uno existente, usá `related_to` con su ID.

El sistema devuelve los resultados ordenados por similitud semántica y frescura (los recuerdos muy antiguos necesitan ser más relevantes para aparecer).

## Cómo modificar y olvidar

- Si un recuerdo quedó desactualizado o querés corregirlo, usá `modify` con su ID. Solo pasá los campos que cambian.
- Si un recuerdo ya no es útil o fue reemplazado, usá `forget` con su ID.

## Vinculación de recuerdos

Si un recuerdo complementa o es consecuencia de otro, vinculalos con `related_to` pasando el ID del recuerdo padre. Esto permite navegar relaciones entre decisiones y sus consecuencias.