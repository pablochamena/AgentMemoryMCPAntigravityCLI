"""
agent-memory-mcp — server.py (v3)
==================================
Herramientas:
  • remember(title, summary, lesson, tags, related_to?, metadata?)
  • recall(query, n?, filter_tags?, since?, related_to?)
  • modify(memory_id, title?, summary?, lesson?, tags?, related_to?, metadata?)
  • forget(query)
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from sentence_transformers import SentenceTransformer

# ─────────────────────────────────────────────────────────────────────────────
# ProjectContext
# ─────────────────────────────────────────────────────────────────────────────

class ProjectContext:
    """
    Detecta la raíz del proyecto subiendo por el árbol de directorios.
    Criterios: .git/ (directorio) o .gemini_memory (archivo).
    start_path: argumento explícito > MEMORY_CWD env > os.getcwd()
    """
    _MARKERS = (".git", ".gemini_memory")

    def __init__(self, start_path: str | None = None) -> None:
        raw = start_path or os.environ.get("MEMORY_CWD") or os.getcwd()
        start = Path(raw).resolve()
        self._root = self._find_project_root(start)

    def _find_project_root(self, start: Path) -> Path:
        current = start if start.is_dir() else start.parent
        while True:
            for marker in self._MARKERS:
                if (current / marker).exists():
                    return current
            parent = current.parent
            if parent == current:
                return start if start.is_dir() else start.parent
            current = parent

    @property
    def root(self) -> Path:
        return self._root

    @property
    def slug(self) -> str:
        name = self._root.name.lower()
        name = re.sub(r"[\s\-]+", "_", name)
        name = re.sub(r"[^\w]", "", name)
        return name or "default_project"

    @property
    def memory_dir(self) -> Path:
        path = self._root / ".memory"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def __repr__(self) -> str:
        return f"ProjectContext(root={self._root}, slug={self.slug!r})"


# ─────────────────────────────────────────────────────────────────────────────
# MiniLMEmbeddingFunction
# ─────────────────────────────────────────────────────────────────────────────

class MiniLMEmbeddingFunction(EmbeddingFunction):
    """Singleton wrapper de all-MiniLM-L6-v2 para ChromaDB."""

    _instance: MiniLMEmbeddingFunction | None = None
    _model: SentenceTransformer | None = None
    MODEL_NAME = "all-MiniLM-L6-v2"

    @classmethod
    def get(cls) -> MiniLMEmbeddingFunction:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if MiniLMEmbeddingFunction._model is None:
            MiniLMEmbeddingFunction._model = SentenceTransformer(self.MODEL_NAME)

    def name(self) -> str:
        return self.MODEL_NAME

    def get_config(self) -> dict:
        return {"model_name": self.MODEL_NAME}

    @classmethod
    def build_from_config(cls, config: dict) -> "MiniLMEmbeddingFunction":
        return cls.get()

    def __call__(self, input: Documents) -> Embeddings:
        assert MiniLMEmbeddingFunction._model is not None
        vectors = MiniLMEmbeddingFunction._model.encode(
            list(input), convert_to_numpy=True, show_progress_bar=False
        )
        return vectors.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# MemoryEngine
# ─────────────────────────────────────────────────────────────────────────────

class MemoryEngine:
    """CRUD sobre ChromaDB para un proyecto dado."""

    def __init__(self, context: ProjectContext) -> None:
        self._context = context
        self._collection: chromadb.Collection | None = None

    # ── Colección ──────────────────────────────────────────────────────────

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = chromadb.PersistentClient(path=str(self._context.memory_dir))
            self._collection = client.get_or_create_collection(
                name=self._context.slug,
                embedding_function=MiniLMEmbeddingFunction.get(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── Git helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _get_git_branch(root: Path) -> str | None:
        if not (root / ".git").is_dir():
            return None
        try:
            out = subprocess.check_output(
                ["git", "-C", str(root), "branch", "--show-current"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            return out or None
        except Exception:
            return None

    @staticmethod
    def _get_git_commit(root: Path) -> str | None:
        if not (root / ".git").is_dir():
            return None
        try:
            out = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            return out or None
        except Exception:
            return None

    @staticmethod
    def _build_id() -> str:
        return str(uuid.uuid4())

    # ── Tags & related_to serialization ───────────────────────────────────
    # ChromaDB metadata only supports str/int/float/bool — lists must be serialized.
    # Tags use pipe delimiters (|tag|) to avoid substring collisions.

    @staticmethod
    def _tags_to_str(tags: list[str]) -> str:
        """['decision', 'auth'] → '|decision|auth|'"""
        normalized = [t.lower().strip() for t in tags if t.strip()]
        return "|" + "|".join(normalized) + "|" if normalized else ""

    @staticmethod
    def _str_to_tags(tags_str: str) -> list[str]:
        return [t for t in tags_str.strip("|").split("|") if t]

    @staticmethod
    def _related_to_str(ids: list[str]) -> str:
        return ",".join(ids)

    # ── Freshness decay ───────────────────────────────────────────────────

    @staticmethod
    def _freshness_factor(created_at_str: str) -> float:
        """
        ≤ 30d  → 1.0
        30–365d → linear 1.0 → 0.85
        > 365d → 0.7
        """
        try:
            created = datetime.fromisoformat(created_at_str)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).days
        except Exception:
            return 1.0

        if age_days <= 30:
            return 1.0
        elif age_days <= 365:
            progress = (age_days - 30) / 335
            return round(1.0 - progress * 0.15, 4)
        else:
            return 0.7

    # ── Where clause builder ──────────────────────────────────────────────

    @staticmethod
    def _build_where(since: str | None) -> dict | None:
        """
        Construye el where clause de ChromaDB.
        Solo filtra por fecha (soportado nativamente).
        El filtro por tags y related_to se aplica en Python post-query
        porque ChromaDB 1.5.x no soporta $contains en strings de metadata.
        """
        if since:
            return {"created_at": {"$gte": since}}
        return None

    @staticmethod
    def _matches_tags(tags_str: str, filter_tags: list[str]) -> bool:
        """OR: al menos uno de los filter_tags debe estar en tags_str."""
        for t in filter_tags:
            needle = f"|{t.lower().strip()}|"
            if needle in tags_str:
                return True
        return False

    # ── remember ──────────────────────────────────────────────────────────

    def remember(
        self,
        title: str,
        summary: str,
        lesson: str,
        tags: list[str],
        related_to: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Guarda un recuerdo estructurado (Formato v3).
        Document embebido: '{summary} Lección: {lesson}'
        Tags almacenados como '|tag1|tag2|' para $contains filtering.
        related_to almacenado como UUIDs separados por coma.
        """
        col = self._get_collection()
        doc_id = self._build_id()
        document = f"{summary.strip()} Lección: {lesson.strip()}"

        enriched: dict[str, Any] = {
            **(metadata or {}),
            "schema_version": "3",
            "title": title.strip(),
            "summary": summary.strip(),
            "lesson": lesson.strip(),
            "tags_str": self._tags_to_str(tags),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_branch": self._get_git_branch(self._context.root),
            "git_commit": self._get_git_commit(self._context.root),
            "project_slug": self._context.slug,
        }
        if related_to:
            enriched["related_to_str"] = self._related_to_str(related_to)

        enriched = {k: v for k, v in enriched.items() if v is not None}
        col.add(ids=[doc_id], documents=[document], metadatas=[enriched])
        return doc_id

    # ── recall ────────────────────────────────────────────────────────────

    def recall(
        self,
        query: str,
        n: int = 5,
        filter_tags: list[str] | None = None,
        since: str | None = None,
        related_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Búsqueda semántica con filtros opcionales y decaimiento por antigüedad.

        Si related_to es provisto: devuelve directamente fragmentos que lo
        referencian (sin búsqueda vectorial).

        Freshness reranking: recupera n*3 candidatos, aplica factor de
        decaimiento, reordena y devuelve top n.
        """
        col = self._get_collection()
        if col.count() == 0:
            return []

        # Path 1: lookup por relación — fetch todo y filtra en Python
        if related_to:
            try:
                raw = col.get(include=["documents", "metadatas"])
                hits = [
                    {"id": doc_id, "content": doc, "score": 1.0,
                     "base_score": 1.0, "freshness": 1.0, "metadata": meta}
                    for doc_id, doc, meta in zip(
                        raw["ids"], raw["documents"], raw["metadatas"]
                    )
                    if related_to in meta.get("related_to_str", "")
                ]
                return hits[:n]
            except Exception:
                return []

        # Path 2: búsqueda vectorial con filtro de fecha (ChromaDB nativo)
        where = self._build_where(since)
        n_candidates = min(n * 3, col.count())

        try:
            query_kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": n_candidates,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_kwargs["where"] = where
            results = col.query(**query_kwargs)
        except Exception:
            return []

        memories: list[dict[str, Any]] = []
        for doc_id, doc, meta, dist in zip(
            results["ids"][0], results["documents"][0],
            results["metadatas"][0], results["distances"][0],
        ):
            # Filtro de tags en Python (ChromaDB 1.5.x no soporta $contains en metadata)
            if filter_tags and not self._matches_tags(meta.get("tags_str", ""), filter_tags):
                continue
            base = 1.0 - (dist / 2.0)
            fresh = self._freshness_factor(meta.get("created_at", ""))
            memories.append({
                "id": doc_id, "content": doc,
                "score": round(base * fresh, 4),
                "base_score": round(base, 4),
                "freshness": round(fresh, 3),
                "metadata": meta,
            })

        memories.sort(key=lambda x: x["score"], reverse=True)
        return memories[:n]

    # ── modify ────────────────────────────────────────────────────────────

    def modify(
        self,
        memory_id: str,
        title: str | None = None,
        summary: str | None = None,
        lesson: str | None = None,
        tags: list[str] | None = None,
        related_to: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Actualiza campos de un recuerdo existente (merge parcial).
        Si summary o lesson cambian, re-embede el documento.
        Siempre setea updated_at.
        Retorna dict con 'updated_fields' o 'error'.
        """
        col = self._get_collection()
        try:
            existing = col.get(ids=[memory_id], include=["documents", "metadatas"])
        except Exception as e:
            return {"error": f"Error al buscar fragmento: {e}"}

        if not existing["ids"]:
            return {"error": f"Fragmento '{memory_id}' no encontrado."}

        current_doc = existing["documents"][0]
        new_meta = dict(existing["metadatas"][0])
        updated_fields: list[str] = []

        if title is not None:
            new_meta["title"] = title.strip()
            updated_fields.append("title")
        if summary is not None:
            new_meta["summary"] = summary.strip()
            updated_fields.append("summary")
        if lesson is not None:
            new_meta["lesson"] = lesson.strip()
            updated_fields.append("lesson")
        if tags is not None:
            new_meta["tags_str"] = self._tags_to_str(tags)
            updated_fields.append("tags")
        if related_to is not None:
            new_meta["related_to_str"] = self._related_to_str(related_to)
            updated_fields.append("related_to")
        if metadata is not None:
            new_meta.update(metadata)
            updated_fields.append("metadata")

        # Rebuild document if summary or lesson changed
        if summary is not None or lesson is not None:
            new_doc = f"{new_meta.get('summary', '')} Lección: {new_meta.get('lesson', '')}"
        else:
            new_doc = current_doc

        new_meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        new_meta = {k: v for k, v in new_meta.items() if v is not None}

        col.update(ids=[memory_id], documents=[new_doc], metadatas=[new_meta])
        return {"updated_fields": updated_fields, "memory_id": memory_id}

    # ── forget ────────────────────────────────────────────────────────────

    def forget(self, query: str) -> int:
        col = self._get_collection()
        candidates = self.recall(query, n=10)
        if not candidates:
            return 0
        col.delete(ids=[candidates[0]["id"]])
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# MCP Handlers
# ─────────────────────────────────────────────────────────────────────────────

server = Server("agent-memory")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="remember",
            description=(
                "Guarda un recuerdo estructurado en la memoria del proyecto. "
                "Requiere title, summary, lesson y al menos un tag. "
                "El proyecto y contexto Git se detectan automáticamente."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Título corto (≤60 chars). Ej: 'Migrar JWT a OAuth2'.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Qué ocurrió o qué se decidió (1-2 oraciones). Se embede para búsqueda semántica.",
                    },
                    "lesson": {
                        "type": "string",
                        "description": "Conclusión accionable (≤120 chars). Ej: 'OAuth2 reduce superficie de ataque.'",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Categorías del recuerdo. Al menos 1. Valores sugeridos: decision, bug, fix, architecture, pattern, dependency, requirement, general.",
                        "minItems": 1,
                    },
                    "related_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de IDs (UUIDs) de recuerdos relacionados.",
                        "default": [],
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Metadatos adicionales. Ej: {\"ticket\": \"PROJ-42\", \"agent_id\": \"codebase-investigator\"}.",
                        "default": {},
                    },
                },
                "required": ["title", "summary", "lesson", "tags"],
            },
        ),
        Tool(
            name="recall",
            description=(
                "Recupera recuerdos relevantes con búsqueda semántica y decaimiento por antigüedad. "
                "Soporta filtros por tags, fecha y relaciones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Qué estás buscando."},
                    "n": {"type": "integer", "description": "Máximo de resultados.", "default": 5, "minimum": 1, "maximum": 20},
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filtrar por tags (OR entre ellos). Ej: ['bug', 'fix'].",
                    },
                    "since": {
                        "type": "string",
                        "description": "Solo recuerdos posteriores a esta fecha ISO. Ej: '2026-01-01'.",
                    },
                    "related_to": {
                        "type": "string",
                        "description": "ID de un recuerdo — devuelve los que lo referencian (sin búsqueda vectorial).",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="modify",
            description=(
                "Actualiza campos de un recuerdo existente (actualización parcial). "
                "Solo los campos provistos se modifican. Siempre registra updated_at."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "UUID del recuerdo a modificar."},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "lesson": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "related_to": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="forget",
            description="Borra el recuerdo más similar a la consulta dada.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Descripción del recuerdo a eliminar."},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    args = arguments or {}
    ctx = ProjectContext()
    engine = MemoryEngine(ctx)

    match name:
        # ── remember ────────────────────────────────────────────────────
        case "remember":
            title = args.get("title", "").strip()
            summary = args.get("summary", "").strip()
            lesson = args.get("lesson", "").strip()
            tags = args.get("tags", [])

            missing = [f for f, v in [("title", title), ("summary", summary), ("lesson", lesson)] if not v]
            if missing:
                return [TextContent(type="text", text=f"Error: campos faltantes: {', '.join(missing)}")]
            if not tags:
                return [TextContent(type="text", text="Error: se requiere al menos un tag.")]

            related_to = args.get("related_to") or None
            metadata = args.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            doc_id = engine.remember(
                title=title, summary=summary, lesson=lesson,
                tags=tags, related_to=related_to or None, metadata=metadata,
            )
            tags_display = " ".join(f"[{t}]" for t in tags)
            return [TextContent(type="text", text=(
                f"✅ Recuerdo guardado en '{ctx.slug}'\n"
                f"   Título : {title}\n"
                f"   Tags   : {tags_display}\n"
                f"   Lección: {lesson}\n"
                f"   ID     : {doc_id}"
            ))]

        # ── recall ──────────────────────────────────────────────────────
        case "recall":
            query = args.get("query", "").strip()
            if not query:
                return [TextContent(type="text", text="Error: 'query' es obligatorio.")]

            n = int(args.get("n", 5))
            filter_tags = args.get("filter_tags") or None
            since = args.get("since") or None
            related_to = args.get("related_to") or None

            results = engine.recall(query, n=n, filter_tags=filter_tags, since=since, related_to=related_to)

            if not results:
                return [TextContent(type="text", text=f"🔍 Sin resultados en '{ctx.slug}'.")]

            lines = [f"🧠 {len(results)} recuerdo(s) en '{ctx.slug}':\n"]
            for i, r in enumerate(results, 1):
                meta = r["metadata"]
                schema = meta.get("schema_version", "1")
                mtype_or_tags = meta.get("tags_str", meta.get("memory_type", "general"))
                created = meta.get("created_at", "—")[:10]

                if schema in ("2", "3"):
                    title_disp = meta.get("title", "(sin título)")
                    lesson_disp = meta.get("lesson", "")
                    tags_disp = ""
                    if schema == "3" and meta.get("tags_str"):
                        tag_list = MemoryEngine._str_to_tags(meta["tags_str"])
                        tags_disp = " " + " ".join(f"[{t}]" for t in tag_list)
                    related_count = ""
                    if meta.get("related_to_str"):
                        n_rel = len(meta["related_to_str"].split(","))
                        related_count = f"  🔗{n_rel}"
                    commit = meta.get("git_commit", "")
                    branch = meta.get("git_branch", "")
                    git_ref = f"  git={branch}@{commit}" if commit else (f"  git={branch}" if branch else "")
                    fresh_info = f"  ⏱{r.get('freshness', 1.0):.2f}" if r.get("freshness", 1.0) < 1.0 else ""
                    lines.append(
                        f"── [{i}] score={r['score']:.3f}{fresh_info} | {created}{git_ref}{related_count}\n"
                        f"   📌 {title_disp}{tags_disp}\n"
                        f"   → {lesson_disp}"
                    )
                else:
                    lines.append(
                        f"── [{i}] score={r['score']:.3f} | {created}\n"
                        f"{r['content']}"
                    )

            return [TextContent(type="text", text="\n\n".join(lines))]

        # ── modify ──────────────────────────────────────────────────────
        case "modify":
            memory_id = args.get("memory_id", "").strip()
            if not memory_id:
                return [TextContent(type="text", text="Error: 'memory_id' es obligatorio.")]

            result = engine.modify(
                memory_id=memory_id,
                title=args.get("title") or None,
                summary=args.get("summary") or None,
                lesson=args.get("lesson") or None,
                tags=args.get("tags") or None,
                related_to=args.get("related_to") or None,
                metadata=args.get("metadata") or None,
            )

            if "error" in result:
                return [TextContent(type="text", text=f"❌ {result['error']}")]

            fields = ", ".join(result["updated_fields"]) if result["updated_fields"] else "(ninguno)"
            return [TextContent(type="text", text=(
                f"✏️ Recuerdo actualizado en '{ctx.slug}'\n"
                f"   ID             : {memory_id}\n"
                f"   Campos actualizados: {fields}"
            ))]

        # ── forget ──────────────────────────────────────────────────────
        case "forget":
            query = args.get("query", "").strip()
            if not query:
                return [TextContent(type="text", text="Error: 'query' es obligatorio.")]
            deleted = engine.forget(query)
            if deleted:
                return [TextContent(type="text", text=f"🗑️ Recuerdo eliminado de '{ctx.slug}'.")]
            return [TextContent(type="text", text=f"ℹ️ No se encontraron recuerdos para eliminar en '{ctx.slug}'.")]

        case _:
            return [TextContent(type="text", text=f"Error: herramienta desconocida '{name}'.")]


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
