# Estrategia de Formato de Recuerdos — agent-memory-mcp

> Análisis de alternativas para estructurar memorias de desarrollo de software.
> Objetivo: memoria mínima, densa y consumible por uno o múltiples agentes.

---

## Principios de diseño (invariantes)

Antes de comparar alternativas, estos principios aplican a **todas**:

1. **El embedding se hace sobre el `document`** que ChromaDB almacena. Todo lo que no esté en ese campo NO participa en la búsqueda semántica. Por lo tanto, el texto del documento debe ser rico en significado, no un dump de JSON.
2. **La metadata de ChromaDB** soporta filtrado exacto (`where={"memory_type": "bug"}`). Es el lugar correcto para campos estructurados como fechas, hashes, tipos.
3. **Fragmentos cortos** — el agente recibe todos los resultados de `recall` en un mismo bloque de contexto. Cada recuerdo debe ser auto-contenido en 2-3 oraciones.
4. **Git pasivo** — se captura lo que existe en el momento de guardar. Si no hay `.git`, simplemente no se incluye. Nunca se fuerza un commit.

---

## Alternativa A — Texto libre enriquecido (actual, mejorado)

### Estructura

```
document (lo que se embede):
  "[TIPO] TÍTULO: descripción densa de 1-2 oraciones. LECCIÓN: conclusión o acción futura."

metadata (campos estructurados, filtrable):
  memory_type   : str   # decision | bug | dependency | pattern | requirement | architecture
  title         : str   # título corto (≤ 60 chars), único identificador humano
  lesson        : str   # conclusión/lección aprendida (≤ 120 chars)
  created_at    : str   # ISO 8601 UTC
  project_slug  : str
  git_branch    : str | ausente
  git_commit    : str | ausente   # hash corto (7 chars)
  agent_id      : str | ausente   # "gemini-cli" | "subagent-X" para multiagente
```

### Ejemplo — Decisión: migrar de JWT a OAuth2

**`document`** (lo que se embede y busca):
```
[decision] Migrar autenticación de JWT a OAuth2: se reemplaza la validación manual de tokens
por el flujo Authorization Code de OAuth2 usando python-jose + authlib, eliminando la
gestión manual de expiración. LECCIÓN: JWT propio genera deuda de seguridad; delegar a OAuth2
reduce superficie de ataque y habilita SSO futuro.
```

**`metadata`**:
```json
{
  "memory_type": "decision",
  "title": "Migrar autenticación de JWT a OAuth2",
  "lesson": "JWT propio genera deuda de seguridad; OAuth2 habilita SSO futuro.",
  "created_at": "2026-05-16T19:42:03Z",
  "project_slug": "sciagent",
  "git_branch": "feature/oauth2-migration",
  "git_commit": "a3f9c12",
  "agent_id": "gemini-cli"
}
```

### Integración Git pasiva

```python
# En MemoryEngine._enrich_git():
git_commit = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
    stderr=subprocess.DEVNULL, text=True
).strip()
```

Solo se ejecuta si existe `.git/`. Si falla (repo sin commits, detached HEAD), se omite silenciosamente.

### Ventajas
- ✅ El texto del document es completamente natural → máxima calidad de embedding
- ✅ Compatible con el `remember()` actual (cambio mínimo)
- ✅ El prefijo `[tipo]` guía la búsqueda hacia recuerdos del tipo correcto
- ✅ `lesson` en metadata permite mostrarla sin repetir el texto completo
- ✅ `title` permite al agente identificar y referenciar recuerdos sin leer el cuerpo

### Desventajas
- ⚠️ El agente debe generar el texto según una convención implícita (puede variar entre sesiones)
- ⚠️ No hay validación de que `lesson` esté presente — si el agente lo omite, se pierde información
- ⚠️ Difícil de parsear programáticamente si se quiere extraer solo el título o la lección

---

## Alternativa B — Documento natural + metadata rica (recomendada)

### Estructura

El texto del document se separa explícitamente en dos campos semánticos pasados como argumentos al tool:

```
Tool remember recibe:
  summary     : str   # 1-2 oraciones densas en lenguaje natural (lo que se embede)
  lesson      : str   # conclusión/lección aprendida, corta (≤ 120 chars)
  memory_type : str
  title       : str   # obligatorio en B
  metadata    : dict  # campos adicionales del usuario

document almacenado en ChromaDB:
  f"{summary} Lección: {lesson}"   ← concatenación para embedding completo

metadata almacenada:
  title, lesson, memory_type, summary, created_at, project_slug,
  git_branch, git_commit, agent_id
```

### Ejemplo — Decisión: migrar de JWT a OAuth2

**`summary`** (argumento del tool):
```
Se reemplaza la validación manual de tokens JWT por el flujo Authorization Code
de OAuth2 usando python-jose + authlib, eliminando la gestión manual de expiración.
```

**`lesson`** (argumento del tool):
```
JWT propio genera deuda de seguridad; OAuth2 reduce superficie de ataque y habilita SSO futuro.
```

**`document`** guardado (concatenación automática):
```
Se reemplaza la validación manual de tokens JWT por el flujo Authorization Code
de OAuth2 usando python-jose + authlib, eliminando la gestión manual de expiración.
Lección: JWT propio genera deuda de seguridad; OAuth2 reduce superficie de ataque y habilita SSO futuro.
```

**`metadata`**:
```json
{
  "memory_type": "decision",
  "title": "Migrar autenticación de JWT a OAuth2",
  "summary": "Se reemplaza la validación manual de tokens JWT...",
  "lesson": "JWT propio genera deuda de seguridad; OAuth2 habilita SSO futuro.",
  "created_at": "2026-05-16T19:42:03Z",
  "project_slug": "sciagent",
  "git_branch": "feature/oauth2-migration",
  "git_commit": "a3f9c12",
  "agent_id": "gemini-cli"
}
```

### Cómo lo consume el agente en recall

El formato de salida del `recall` puede mostrar solo `title` + `lesson` (≤ 2 líneas por resultado), y dejar el `summary` completo disponible solo si el score > umbral:

```
[1] decision | "Migrar autenticación de JWT a OAuth2" (score=0.91)
    → JWT propio genera deuda de seguridad; OAuth2 habilita SSO futuro.
```

### Integración Git pasiva

Idéntica a Alternativa A. `git_commit` y `git_branch` son capturados automáticamente por `MemoryEngine` sin que el agente los provea.

### Cambios en el tool `remember`

```
inputSchema agrega:
  title   : string  (requerido)
  summary : string  (requerido, reemplaza a "content")
  lesson  : string  (requerido)
  metadata: object  (opcional)
```

### Ventajas
- ✅ **`title` es obligatorio** → el agente siempre genera un identificador humano legible
- ✅ **`lesson` es obligatorio** → nunca se pierde la conclusión accionable
- ✅ El document embebido incluye tanto summary como lesson → búsqueda semántica cubre ambos
- ✅ En `recall`, se puede mostrar solo `title + lesson` sin saturar el contexto
- ✅ `title` permite `forget("Migrar autenticación de JWT a OAuth2")` con alta precisión
- ✅ Multiagente: `agent_id` en metadata permite filtrar por fuente
- ✅ Escalable: se pueden agregar campos a metadata sin cambiar el embedding

### Desventajas
- ⚠️ Cambia la interfaz del tool `remember` (breaking change para recuerdos existentes)
- ⚠️ Requiere que el agente genere 3 campos en vez de 1 (mayor esfuerzo por llamada)
- ⚠️ `title` duplicado en document y metadata (redundancia menor)

---

## Alternativa C — Schema JSON como document (descartada técnicamente)

### Estructura

```
document (embebido):
  '{"type":"decision","title":"...","summary":"...","lesson":"..."}'

metadata:
  (campos mínimos solo para ChromaDB)
```

### Ejemplo

```json
{
  "type": "decision",
  "title": "Migrar autenticación de JWT a OAuth2",
  "summary": "Se reemplaza JWT por OAuth2 Authorization Code usando authlib.",
  "lesson": "JWT propio crea deuda de seguridad y bloquea SSO futuro.",
  "git": {"branch": "feature/oauth2", "commit": "a3f9c12"}
}
```

### Por qué se descarta

- ❌ **El modelo all-MiniLM-L6-v2 fue entrenado en lenguaje natural, NO en JSON**. Embedar JSON degrada significativamente la calidad de la búsqueda semántica (los tokens `{`, `"`, `:` consumen espacio en el vocabulario sin aportar significado).
- ❌ ChromaDB ya tiene metadata nativa — duplicar la estructura en el document es redundante.
- ⚠️ Si el JSON está malformado, el embedding es basura silenciosa.

**Única excepción válida:** si se usa un modelo de embeddings entrenado en código/JSON (como `code-search-*`), pero eso no aplica aquí.

---

## Tabla comparativa

| Criterio | A — Texto enriquecido | B — Natural + metadata rica | C — JSON como doc |
|---|---|---|---|
| Calidad de embedding | Alta | **Muy alta** | Baja |
| Estructura garantizada | Baja (convención implícita) | **Alta (campos requeridos)** | Alta |
| Saturación de contexto en recall | Media | **Baja (title+lesson)** | Media |
| Compatibilidad con código actual | **Alta (cambio mínimo)** | Media (breaking) | Baja |
| Filtrado por tipo/fecha | Sí (metadata) | **Sí + más campos** | Limitado |
| Soporte multiagente | Parcial | **Sí (agent_id)** | No |
| `forget` preciso por título | No | **Sí** | No |
| Esfuerzo del agente por `remember` | Bajo (1 campo) | Medio (3 campos) | Medio |

---

## Recomendación: Alternativa B

**Justificación para desarrollador individual → multiagente:**

1. **`title` obligatorio resuelve el problema de `forget` preciso.** Con Alternativa A, `forget("JWT")` puede borrar el recuerdo equivocado si hay varios sobre JWT. Con B, `forget("Migrar autenticación de JWT a OAuth2")` tiene score ~0.98 contra el recuerdo correcto.

2. **`lesson` obligatorio hace la memoria accionable.** Un agente que hace `recall("autenticación")` recibe inmediatamente la conclusión sin necesidad de procesar el contexto completo. Esto reduce tokens consumidos.

3. **La breaking change es manejable.** Los recuerdos existentes (formato A) siguen funcionando porque ChromaDB los almacena igual. Solo los nuevos usarán el formato B. Se puede agregar un campo `schema_version: "2"` en metadata para distinguirlos.

4. **Preparado para multiagente desde el inicio.** `agent_id` en metadata permite que en el futuro un orquestador filtre `where={"agent_id": "codebase-investigator"}` y vea solo los recuerdos de ese subagente.

5. **git_commit capturado automáticamente** → sin ningún esfuerzo del agente, cada recuerdo queda anclado al estado exacto del código cuando se tomó la decisión.

---

## Próximos pasos de implementación

- [ ] **Paso 1:** Agregar helper `_get_git_commit()` en `MemoryEngine`
- [ ] **Paso 2:** Actualizar `MemoryEngine.remember()` para aceptar `title` y `lesson`, construir el document como `f"{summary} Lección: {lesson}"`, y guardar ambos campos en metadata
- [ ] **Paso 3:** Actualizar el `inputSchema` del tool `remember` en los handlers MCP (nuevos campos requeridos + `summary` reemplaza `content`)
- [ ] **Paso 4:** Actualizar el formatter de `recall` para mostrar `title + lesson` como primera línea y `summary` solo si el agente lo pide
- [ ] **Paso 5:** Actualizar tests para el nuevo esquema
- [ ] **Paso 6:** Agregar `schema_version` a la metadata para compatibilidad con recuerdos legacy

---

*¿Confirmás que implementamos la Alternativa B? Una vez que acordemos, ajusto `server.py` y los tests.*
