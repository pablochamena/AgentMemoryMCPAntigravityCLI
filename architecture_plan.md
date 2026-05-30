# Plan de Implementación: `agent-memory-mcp`

> Servidor MCP liviano, sin Docker, con memoria semántica por proyecto.

---

## 1. Diagnóstico del sistema anterior

El sistema en `ai-memory-platform` tiene una **arquitectura de dos capas** (MCP server → FastAPI → PostgreSQL+pgvector) que requiere Docker Compose para funcionar. Los problemas que resuelve la nueva versión:

| Problema anterior | Solución propuesta |
|---|---|
| Depende de Docker y PostgreSQL | Todo en proceso, ChromaDB en disco |
| El MCP server es solo un proxy HTTP | El MCP server ES el motor de memoria |
| Requiere `HOST_PWD` inyectado por wrapper | Detección nativa de raíz de proyecto |
| No tiene herramienta `forget` | Implementada como búsqueda + borrado |
| Dos procesos que mantener levantados | Un único script Python |

---

## 2. Arquitectura propuesta

```
gemini cli  ──stdio──►  server.py  (único proceso)
                             │
                    ┌────────▼────────┐
                    │  ProjectContext  │   detecta .git / .gemini_memory
                    │   (subida dirs) │   → define ruta .memory/
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  MemoryEngine   │   ChromaDB persistent client
                    │                 │   colección = project slug
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  EmbeddingModel │   SentenceTransformer
                    │ all-MiniLM-L6-v2│   cargado una sola vez al inicio
                    └─────────────────┘
```

**Flujo de datos:**
1. Gemini CLI llama una herramienta vía stdio JSON-RPC.
2. `server.py` detecta el `cwd` pasado como argumento o variable de entorno.
3. `ProjectContext` sube por el árbol de directorios buscando `.git` o `.gemini_memory`.
4. `MemoryEngine` abre (o crea) la colección ChromaDB en `<project_root>/.memory/`.
5. Ejecuta `remember` / `recall` / `forget` y responde via stdio.

---

## 3. Stack de dependencias

### Dependencias de producción

| Librería | Versión mínima | Rol |
|---|---|---|
| `mcp` | ≥ 1.0 | Protocolo MCP stdio, decoradores de servidor |
| `chromadb` | ≥ 0.5 | Vector store embebido, persistencia en disco |
| `sentence-transformers` | ≥ 3.0 | Embeddings `all-MiniLM-L6-v2` (~90 MB) |
| `torch` | ≥ 2.0 (CPU) | Backend de sentence-transformers |

> [!IMPORTANT]
> `chromadb` ≥ 0.5 ya no incluye su propio embedding function por defecto para sentence-transformers; hay que pasarle la función explícitamente. Esto nos da control total sobre el modelo.

### Sin dependencias de producción
- Sin `requests` (no hay API externa).
- Sin `fastapi` / `uvicorn`.
- Sin `psycopg2` / `pgvector`.
- Sin `python-dotenv` (configuración por argumentos o env vars mínimas).

### Dependencias de desarrollo (opcionales)

| Librería | Rol |
|---|---|
| `pytest` | Tests unitarios del motor de memoria |
| `pytest-asyncio` | Tests de los handlers MCP |

---

## 4. Estructura de archivos del repositorio

```
agent-memory-mcp/
├── server.py              # Punto de entrada único — el servidor MCP completo
├── requirements.txt       # Dependencias de producción (4 líneas)
├── requirements-dev.txt   # Dependencias de desarrollo
├── install.sh             # Script de instalación en venv
├── README.md              # Instrucciones de configuración en .gemini/settings.json
└── tests/
    ├── test_project_context.py
    └── test_memory_engine.py
```

**Nota sobre `.memory/`**: Esta carpeta es creada dinámicamente dentro de cada proyecto que use la memoria. No vive en el repositorio `agent-memory-mcp`, sino en el proyecto cliente (ej: `mi-proyecto/.memory/`).

---

## 5. Módulos internos de `server.py`

El script está dividido en **4 secciones lógicas** dentro de un único archivo:

### 5.1 `ProjectContext` — Detección de raíz

```python
class ProjectContext:
    """
    Detecta la raíz del proyecto subiendo por el árbol de directorios.
    Criterios de parada: encuentra .git/ o .gemini_memory
    """

    def __init__(self, start_path: str | None = None): ...

    def _find_project_root(self, start: Path) -> Path:
        """
        Sube desde `start` buscando .git o .gemini_memory.
        Si no encuentra ninguno, usa `start` como fallback.
        Retorna: Path absoluto de la raíz del proyecto.
        """
        ...

    @property
    def root(self) -> Path: ...

    @property
    def slug(self) -> str:
        """
        Nombre canónico del proyecto: basename del root, normalizado.
        Ej: 'my-cool-api' → 'my_cool_api'
        """
        ...

    @property
    def memory_dir(self) -> Path:
        """Ruta a <project_root>/.memory/ — la crea si no existe."""
        ...
```

> [!NOTE]
> El `start_path` puede ser inyectado via variable de entorno `MEMORY_CWD` para que Gemini CLI pase el directorio activo del usuario. Si no está definida, usa `os.getcwd()`.

---

### 5.2 `EmbeddingFunction` — Adaptador para ChromaDB

```python
class MiniLMEmbeddingFunction:
    """
    Wrapper que adapta SentenceTransformer al protocolo
    chromadb.EmbeddingFunction.
    Cargado una sola vez como singleton al arrancar el servidor.
    """

    _instance: "MiniLMEmbeddingFunction | None" = None

    @classmethod
    def get(cls) -> "MiniLMEmbeddingFunction":
        """Singleton — carga el modelo solo en el primer uso."""
        ...

    def __call__(self, input: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos."""
        ...
```

---

### 5.3 `MemoryEngine` — Motor de almacenamiento

```python
class MemoryEngine:
    """
    Encapsula todas las operaciones sobre ChromaDB.
    Una instancia por llamada (o cached por slug de proyecto).
    """

    def __init__(self, context: ProjectContext): ...

    def _get_collection(self) -> chromadb.Collection:
        """
        Abre o crea la colección ChromaDB para el proyecto actual.
        nombre colección = context.slug
        path persistente = context.memory_dir
        """
        ...

    def remember(
        self,
        content: str,
        memory_type: str = "general",
        metadata: dict | None = None,
    ) -> str:
        """
        Genera embedding, construye documento con metadata enriquecida
        (timestamp, memory_type, git_branch si disponible) y lo inserta.
        Retorna: ID del documento generado.
        """
        ...

    def recall(self, query: str, n: int = 5) -> list[dict]:
        """
        Búsqueda semántica por similitud de coseno.
        Retorna lista de {content, score, metadata, id}.
        """
        ...

    def forget(self, query: str) -> int:
        """
        Estrategia: recall(query, n=10) → borra el documento más relevante.
        Retorna: cantidad de documentos borrados (0 o 1).
        """
        ...
```

> [!TIP]
> Para `forget`, una primera versión borra solo el match más cercano (score más alto). Se puede evolucionar a borrado por umbral o interactivo sin cambiar la interfaz.

---

### 5.4 Handlers MCP — Interfaz con Gemini CLI

```python
server = Server("agent-memory")

@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    Declara las 3 herramientas al cliente MCP.
    Esquemas JSON de cada tool definidos aquí.
    """
    # remember, recall, forget
    ...

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Router principal. Instancia ProjectContext y MemoryEngine,
    delega al método correspondiente y formatea la respuesta.
    """
    ctx = ProjectContext()          # detecta proyecto desde cwd
    engine = MemoryEngine(ctx)      # abre ChromaDB del proyecto

    match name:
        case "remember": ...
        case "recall":   ...
        case "forget":   ...
        case _: ...

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, ...)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 6. Esquema de metadata por recuerdo

Cada documento almacenado en ChromaDB llevará esta metadata:

```python
{
    "memory_type": str,       # "general" | "architecture" | "error" | "fix" | "decision"
    "created_at": str,        # ISO 8601 UTC
    "git_branch": str | None, # rama actual si hay .git
    "project_slug": str,      # nombre normalizado del proyecto
    # + cualquier campo extra pasado por el usuario en `metadata`
}
```

---

## 7. Configuración en Gemini CLI

Entrada a agregar en `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/ruta/a/agent-memory-mcp/venv/bin/python",
      "args": ["/ruta/a/agent-memory-mcp/server.py"],
      "env": {
        "MEMORY_CWD": "${workspaceFolder}"
      }
    }
  }
}
```

> [!IMPORTANT]
> `${workspaceFolder}` es la variable que Gemini CLI expande al directorio del proyecto activo. Esto hace que `ProjectContext` detecte el proyecto correcto sin necesidad de pasar `project_id` explícitamente.

---

## 8. Plan de implementación paso a paso

### Fase 1 — Setup del repositorio (30 min)
- [ ] Inicializar `agent-memory-mcp/` con `.gitignore` adecuado (excluir `venv/`, `*.pyc`, `.memory/` no)
- [ ] Crear `requirements.txt` con las 4 dependencias
- [ ] Crear `install.sh`: crea venv, instala dependencias, descarga modelo al caché

### Fase 2 — `ProjectContext` (45 min)
- [ ] Implementar la clase completa con tests en `tests/test_project_context.py`
- [ ] Casos de prueba: `.git` encontrado, `.gemini_memory` encontrado, fallback a cwd, slugificación

### Fase 3 — `EmbeddingFunction` + `MemoryEngine` (1 h)
- [ ] Implementar singleton de SentenceTransformer
- [ ] Implementar `remember`, `recall`, `forget` con ChromaDB
- [ ] Tests unitarios con ChromaDB en modo efímero (`chromadb.EphemeralClient`)

### Fase 4 — Handlers MCP (30 min)
- [ ] Definir schemas JSON de las 3 tools
- [ ] Implementar `call_tool` con `match/case`
- [ ] Validación de argumentos y mensajes de error descriptivos

### Fase 5 — Integración y validación E2E (45 min)
- [ ] Script `install.sh` funcional
- [ ] Configurar entrada en `settings.json` de Gemini CLI
- [ ] Prueba manual: `remember` → `recall` → `forget` → `recall` (debe retornar vacío)
- [ ] Verificar aislamiento: dos proyectos distintos no comparten recuerdos

### Fase 6 — README y empaquetado (20 min)
- [ ] Instrucciones de instalación en una sola sección
- [ ] Ejemplo de configuración `settings.json`
- [ ] Tipos de memoria recomendados para el agente
