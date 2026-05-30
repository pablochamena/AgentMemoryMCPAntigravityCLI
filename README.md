# agent-memory-mcp

> **Memoria vectorial persistente, semántica y aislada por proyecto para agentes MCP y Antigravity CLI.**  
> Un único servicio en Python. Sin dependencias externas pesadas, sin Docker y diseñado para integrarse de forma instantánea.

---

## 🚀 ¿Qué es `agent-memory-mcp`?

Es un servidor [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) que dota a tus agentes de IA (como **Antigravity CLI** u otros clientes MCP) de una **memoria a largo plazo estructurada y semántica**. 

A diferencia de los enfoques globales, este sistema implementa **aislamiento automático por proyecto**. Cada repositorio Git o carpeta que contenga un marcador `.gemini_memory` tendrá su propia base de datos ChromaDB local guardada en `<proyecto>/.memory/`. Así, tus conversaciones en el proyecto *A* nunca interferirán con el contexto del proyecto *B*.

---

## 💎 Características Principales

*   **Esquema de Memoria v3 Avanzado:** Adiós al texto plano desordenado. Los recuerdos son estructurados (`title`, `summary`, `lesson`, `tags`, `related_to`), optimizando el consumo de tokens y permitiendo al agente buscar, modificar y borrar recuerdos con precisión milimétrica.
*   **Arquitectura Dual de Transporte:**
    *   **Modo HTTP/SSE (FastMCP):** Protocolo `streamable-http` optimizado nativamente para **Antigravity CLI** (`agy`).
    *   **Modo STDIO Clásico:** Entrada/salida estándar para clientes tradicionales (Gemini CLI, Claude Desktop, etc.).
*   **Arranque Ultra Rápido (Lazy Loading):** Los modelos de embeddings de `sentence-transformers` se cargan de forma diferida (lazy loading). El servidor web bindea el puerto en **menos de 100ms**, evitando de raíz los errores de timeout en los handshakes de los clientes.
*   **Integración Git Pasiva y Transparente:** Captura la rama Git y el commit hash actuales automáticamente al guardar memorias, anclando cada decisión al estado exacto del código.
*   **Relacionamiento y Freshness (Decaimiento):**
    *   Relaciona recuerdos secuenciales usando enlaces `related_to`.
    *   Algoritmo de puntuación híbrida que pondera la similitud semántica con la frescura (los recuerdos muy antiguos decaen gradualmente a menos que su relevancia sea extrema).

---

## 📐 Arquitectura del Sistema

### 1. Integración con Antigravity CLI (Modo HTTP/SSE)

Este es el flujo por defecto para `agy`, ejecutándose en segundo plano en el puerto `8009` (o configurable mediante `MEMORY_PORT`):

```
                        ┌────────────────────────┐
                        │   Antigravity CLI (agy)│
                        └───────────┬────────────┘
                                    │ (streamable-http, puerto 8009)
                                    ▼
                        ┌────────────────────────┐
                        │     server_http.py     │
                        └───────────┬────────────┘
                                    │ (Lazy Loading < 100ms)
                                    ▼
                        ┌────────────────────────┐
                        │      MemoryEngine      │
                        │    (ChromaDB + v3)     │
                        └───────────┬────────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
         /proyecto-A/.memory/          /proyecto-B/.memory/
```

### 2. Integración Tradicional (Modo STDIO)

Ideal para clientes clásicos de MCP que lanzan el proceso de manera directa en cada conversación:

```
                        ┌────────────────────────┐
                        │       Gemini CLI       │
                        └───────────┬────────────┘
                                    │ (stdio pipeline via venv)
                                    ▼
                        ┌────────────────────────┐
                        │       server.py        │
                        └───────────┬────────────┘
                                    │ (Eager Loading)
                                    ▼
                        ┌────────────────────────┐
                        │      MemoryEngine      │
                        └───────────────┬────────┘
                                        │
                                        ▼
                              /proyecto/.memory/
```

---

## 🛠️ Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone https://github.com/tu-usuario/agent-memory-mcp.git ~/agent-memory-mcp
    cd ~/agent-memory-mcp
    ```

2.  **Ejecutar el instalador automatizado:**
    ```bash
    bash install.sh
    ```
    *Este script creará un entorno virtual (`venv`) e instalará las dependencias de producción (`mcp`, `chromadb`, `sentence-transformers`, `torch`, `fastmcp`, `uvicorn`) de forma optimizada.*

---

## ⚙️ Configuración y Uso

> [!IMPORTANT]
> El sistema está diseñado para que el servidor conozca el directorio del proyecto del programador. Para ello, se utiliza la variable de entorno `MEMORY_CWD`.

### Opción A: Servidor en Segundo Plano HTTP (Recomendado para Antigravity CLI)

Este modo levanta un servidor FastMCP persistente que escucha en el puerto `8009` y atiende las llamadas de la CLI de Antigravity.

#### 1. Iniciar/Detener el servidor
Utiliza los scripts de control incluidos en la raíz:
```bash
# Iniciar el servidor (captura automáticamente tu directorio actual como contexto de arranque)
./start_memory.sh

# Detener el servidor de forma segura
./stop_memory.sh

# Ver logs en tiempo real
tail -f server_http.log
```

#### 2. Configurar Antigravity CLI
Escribe (o edita) tu archivo de configuración en `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "agent-memory": {
      "serverUrl": "http://localhost:8009/mcp"
    }
  }
}
```

---

### Opción B: Cliente STDIO Clásico (Gemini CLI)

Si deseas utilizar el canal `stdio` clásico, añade la siguiente configuración a tu `~/.gemini/settings.json` o equivalente del cliente MCP:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/home/pablo/Programacion/personal/agent-memory-mcp/venv/bin/python",
      "args": ["/home/pablo/Programacion/personal/agent-memory-mcp/server.py"],
      "env": {
        "MEMORY_CWD": "${workspaceFolder}"
      }
    }
  }
}
```
> [!NOTE]
> `${workspaceFolder}` es reemplazado dinámicamente por la CLI para apuntar a la raíz del proyecto que tengas abierto.

---

## 🧠 Esquema de Memoria v3 (Alternativa B)

Para evitar la redundancia, la saturación del contexto y los fallos al eliminar registros, el motor almacena la información estructurada bajo el formato **v3**:

1.  **Lo que se indexa semánticamente (ChromaDB `document`):**
    El motor concatena de forma automática el resumen y la lección aprendida:
    `"{summary} Lección: {lesson}"`
2.  **Lo que se guarda en la metadata:**
    Se guardan campos exactos para filtrado lógico y visualización compacta:
    ```json
    {
      "schema_version": "3",
      "title": "Título corto y descriptivo",
      "summary": "1 o 2 oraciones en lenguaje natural con la descripción del hecho.",
      "lesson": "Acción o conclusión futura de valor técnico.",
      "tags_str": "|tag1|tag2|",
      "created_at": "ISO 8601 UTC timestamp",
      "git_branch": "feature-rama-actual",
      "git_commit": "a7b3c2d",
      "project_slug": "nombre_de_tu_proyecto"
    }
    ```

---

## 🧰 Especificación de Herramientas (MCP Tools)

Tanto en modo HTTP como STDIO, el servidor expone las siguientes herramientas para el Agente:

### 1. `remember`
Guarda un nuevo fragmento estructurado en la memoria del proyecto.
*   **Parámetros:**
    *   `title` (string, **requerido**): Título corto y descriptivo (≤ 60 caracteres). Ej: `"Migración a OAuth2"`.
    *   `summary` (string, **requerido**): Qué ocurrió o qué decisión técnica se tomó (1-2 oraciones).
    *   `lesson` (string, **requerido**): Conclusión accionable a futuro (≤ 120 caracteres).
    *   `tags` (array de strings, **requerido**): Categorías asociadas (mínimo 1). Ej: `["decision", "security"]`.
    *   `related_to` (array de strings, opcional): Lista de IDs (UUIDs) de recuerdos con los que se vincula este fragmento.
    *   `metadata` (object, opcional): Datos adicionales específicos que quieras adjuntar.
    *   `project_path` (string, opcional): Sobrescribe la ruta de resolución automática del proyecto.

### 2. `recall`
Recupera los recuerdos semánticamente más relevantes ordenados mediante puntuación de similitud atenuada por su frescura cronológica.
*   **Parámetros:**
    *   `query` (string, **requerido**): Consulta en lenguaje natural. Ej: `"OAuth2 dependencias"`.
    *   `n` (integer, opcional, default: `5`): Número máximo de resultados a retornar.
    *   `filter_tags` (array de strings, opcional): Filtrado tipo OR. Solo retorna recuerdos que tengan al menos uno de estos tags.
    *   `since` (string, opcional): Fecha en formato ISO (`YYYY-MM-DD`). Filtra memorias creadas después de este instante.
    *   `related_to` (string, opcional): ID de un recuerdo padre. Si se provee, retorna directamente los fragmentos relacionados sin hacer búsqueda vectorial (ideal para navegar hilos de decisiones).

### 3. `modify`
Permite al agente actualizar campos puntuales (actualización parcial o *patch*) de un recuerdo existente. Si cambian `summary` o `lesson`, el motor re-calcula los embeddings de forma transparente y actualiza la metadata `updated_at`.
*   **Parámetros:**
    *   `memory_id` (string, **requerido**): UUID del recuerdo a modificar.
    *   `title` / `summary` / `lesson` / `tags` / `related_to` / `metadata` (opcionales): Valores nuevos a reemplazar.

### 4. `forget`
Borra de la base de datos el recuerdo más similar que coincida con la consulta semántica dada.
*   **Parámetros:**
    *   `query` (string, **requerido**): Frase o título descriptivo del recuerdo que se desea eliminar.

---

## 🏷️ Tags Recomendados para Desarrollo

Para mantener un orden óptimo en tus consultas y filtros, se aconseja indicarle a tu Agente usar etiquetas normalizadas:
*   `architecture` (decisiones de diseño, trade-offs de componentes).
*   `decision` (elecciones tecnológicas, enfoques descartados).
*   `bug` (errores identificados, comportamientos inesperados).
*   `fix` (soluciones de bugs, parches aplicados).
*   `dependency` (librerías añadidas, versiones, problemas de paquetes).
*   `requirement` (necesidades de negocio o especificaciones).
*   `performance` (mejoras de velocidad, consumo de recursos).
*   `testing` (configuración de testeo, mocks, casos de uso).

---

## 📁 Aislamiento y Estructura de Archivos

Al interactuar con un proyecto, el servidor buscará jerárquicamente hacia arriba en busca de un marcador:
1.  Un directorio `.git/`
2.  Un archivo vacío `.gemini_memory` (ideal para proyectos que no usan Git)

Una vez resuelto, creará una base de datos local aislada:
```
mi-proyecto/
├── .git/
├── ...
└── .memory/                   ◄ Directorio de memoria local (exclusivo)
    ├── chroma.sqlite3         ◄ Base de datos e índices
    └── ...
```
> [!TIP]
> Se recomienda añadir `.memory/` a tu `.gitignore` global o de cada proyecto para evitar subir índices binarios pesados al repositorio remoto.

---

## 🧪 Desarrollo y Pruebas Unitarias

El proyecto cuenta con una amplia suite de tests unitarios que validan la persistencia, la frescura, el hashing de Git y la lógica de negocio del servidor.

```bash
# Activar entorno virtual
source venv/bin/activate

# Instalar dependencias de testeo
pip install -r requirements-dev.txt

# Ejecutar todos los tests
pytest tests/ -v
```

---

## 🛠️ Resolución de Problemas (Troubleshooting)

*   **Error: `unexpected end of JSON input` en el arranque de la CLI:**
    Ocurre cuando el archivo de configuración `~/.gemini/config/mcp_config.json` existe pero tiene 0 bytes. Asegúrate de que contenga un bloque JSON válido, por ejemplo:
    `{ "mcpServers": {} }`.
*   **Handshake Timeout (El agente tarda en conectar):**
    Este problema ha sido solventado implementando **Lazy Loading** del modelo SentenceTransformer en `server_http.py`. El servidor se levanta al instante y solo procesa el modelo pesado al invocar la primera herramienta.
*   **El servidor no responde / Puerto ocupado:**
    Comprueba si existe un proceso huérfano con `cat .memory_server.pid` y elimínalo, o ejecuta `./stop_memory.sh` para restaurar el estado limpio.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Para más detalles, consulta el archivo [LICENSE](LICENSE).
