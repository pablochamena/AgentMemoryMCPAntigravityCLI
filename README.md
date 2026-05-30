# agent-memory-mcp

> Memoria vectorial persistente y aislada por proyecto para agentes MCP (Gemini CLI).  
> Un único script Python. Sin Docker. Sin servicios externos.

---

## ¿Qué es?

`agent-memory-mcp` es un servidor [MCP](https://modelcontextprotocol.io/) que le da a tu agente de IA (Gemini CLI u otro cliente MCP compatible) una **memoria semántica persistente**, organizada automáticamente por proyecto.

Cada proyecto Git o carpeta marcada con `.gemini_memory` tiene su propia base de datos vectorial aislada, almacenada en `<proyecto>/.memory/`. No hay datos compartidos entre proyectos.

### ¿Para qué sirve?

| Sin memoria | Con agent-memory-mcp |
|---|---|
| El agente olvida todo al cerrar la sesión | Decisiones, errores y patrones persisten entre sesiones |
| Debes re-explicar el contexto en cada conversación | El agente puede hacer `recall` para recuperar contexto relevante |
| No hay trazabilidad de decisiones técnicas | Cada recuerdo tiene timestamp, rama Git y tipo de memoria |

---

## Arquitectura

```
gemini cli  ──stdio──►  server.py
                             │
                    ProjectContext   ← detecta .git / .gemini_memory
                    MemoryEngine     ← ChromaDB PersistentClient
                    EmbeddingFn      ← all-MiniLM-L6-v2 (singleton)
                             │
                   <proyecto>/.memory/   ← base de datos en disco
```

**Stack de producción:** `mcp` · `chromadb` · `sentence-transformers` · `torch`  
**Sin:** Docker, PostgreSQL, FastAPI, servicios externos.

---

## Requisitos

- Python 3.10 o superior
- `git` instalado (para detección automática de proyecto)
- ~500 MB de espacio libre (torch + modelo de embeddings)
- ~90–200 MB de RAM por proceso

---

## Instalación rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/agent-memory-mcp.git ~/agent-memory-mcp
cd ~/agent-memory-mcp

# 2. Ejecutar el instalador (crea venv + instala dependencias)
bash install.sh
```

El instalador muestra al final el bloque JSON exacto para copiar en `settings.json`.

---

## Configuración en Gemini CLI

Editá el archivo `~/.gemini/settings.json` y agregá (o fusioná) la sección `mcpServers`:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/home/pablo/agent-memory-mcp/venv/bin/python",
      "args": ["/home/pablo/agent-memory-mcp/server.py"],
      "env": {
        "MEMORY_CWD": "${workspaceFolder}"
      }
    }
  }
}
```

> **Nota:** `${workspaceFolder}` es la variable que Gemini CLI expande al directorio  
> del proyecto activo. Asegúrate de que la ruta al intérprete y al script coincidan  
> con la salida de `bash install.sh`.

---

## Uso desde Gemini CLI

Una vez configurado, el agente puede usar las herramientas directamente en la conversación:

### `remember` — Guardar un recuerdo

```
Recuerda que decidimos usar ChromaDB como vector store porque es embebido 
y no requiere servidor separado.
```

El agente ejecutará internamente:
```python
remember(
    content="Decidimos usar ChromaDB como vector store porque es embebido...",
    memory_type="decision",
    metadata={"context": "selección de base de datos"}
)
```

### `recall` — Recuperar recuerdos relevantes

```
¿Qué decidimos sobre la base de datos de vectores?
```

El agente buscará semánticamente en la memoria del proyecto actual y retornará los resultados más relevantes con su score de similitud.

### `forget` — Borrar un recuerdo

```
Olvidá lo que guardamos sobre usar FastAPI, ya no es relevante.
```

Borra el recuerdo más similar a la consulta.

---

## Tipos de memoria recomendados

| `memory_type` | Cuándo usarlo |
|---|---|
| `general` | Información genérica, notas sueltas |
| `architecture` | Decisiones de diseño, patrones elegidos, trade-offs |
| `error` | Errores encontrados, stack traces relevantes, bugs conocidos |
| `fix` | Soluciones aplicadas, workarounds que funcionaron |
| `decision` | Decisiones importantes del proyecto (tecnología, enfoque, descarte) |

---

## Detección automática de proyecto

El servidor detecta el proyecto actual buscando hacia arriba en el árbol de directorios:

1. Directorio `.git/` (repositorio Git)
2. Archivo `.gemini_memory` (marcador manual para proyectos sin Git)
3. Fallback: el directorio de trabajo actual

Para proyectos sin Git, creá el marcador manualmente:

```bash
touch /ruta/a/mi-proyecto/.gemini_memory
```

---

## Estructura de archivos generados

```
mi-proyecto/
└── .memory/               ← Creado automáticamente por agent-memory-mcp
    ├── chroma.sqlite3     ← Base de datos ChromaDB
    └── ...                ← Índices HNSW internos de ChromaDB
```

> `.memory/` vive **dentro de cada proyecto cliente**, no en el repositorio de `agent-memory-mcp`.  
> Podés agregarlo a `.gitignore` de tus proyectos o versionarlo si querés compartir la memoria.

---

## Desarrollo y tests

```bash
# Instalar dependencias de desarrollo
source venv/bin/activate
pip install -r requirements-dev.txt

# Ejecutar todos los tests
pytest tests/ -v

# Ejecutar solo los tests de ProjectContext
pytest tests/test_project_context.py -v
```

---

## Licencia

MIT License — ver [LICENSE](LICENSE).
