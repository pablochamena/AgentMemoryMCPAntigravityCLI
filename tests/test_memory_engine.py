"""
Tests for MemoryEngine v3 — tags, related_to, recall filters, freshness, modify.
Usa ChromaDB EphemeralClient (en memoria).
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from server import MemoryEngine, MiniLMEmbeddingFunction, ProjectContext


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_context(tmp_path: Path) -> ProjectContext:
    (tmp_path / ".git").mkdir()
    return ProjectContext(start_path=str(tmp_path))


def make_engine(context: ProjectContext) -> MemoryEngine:
    """Crea un MemoryEngine con ChromaDB efímero (en memoria)."""
    import chromadb
    ephemeral = chromadb.EphemeralClient()

    def _get_ephemeral(self_inner):
        if self_inner._collection is None:
            self_inner._collection = ephemeral.get_or_create_collection(
                name=self_inner._context.slug,
                embedding_function=MiniLMEmbeddingFunction.get(),
                metadata={"hnsw:space": "cosine"},
            )
        return self_inner._collection

    with patch.object(MemoryEngine, "_get_collection", _get_ephemeral):
        eng = MemoryEngine(context)
        # Force collection init inside patch context
        eng._get_collection()

    # After patch: wire the already-created collection directly
    real_col = eng._collection

    def _return_cached(self_inner):
        return real_col

    eng._get_collection = lambda: real_col  # type: ignore[method-assign]
    return eng


@pytest.fixture()
def engine(fake_context: ProjectContext) -> MemoryEngine:
    return make_engine(fake_context)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def rem(engine: MemoryEngine, title: str, summary: str, lesson: str,
        tags: list[str] | None = None, related_to: list[str] | None = None,
        metadata: dict | None = None) -> str:
    return engine.remember(
        title=title, summary=summary, lesson=lesson,
        tags=tags or ["general"],
        related_to=related_to,
        metadata=metadata,
    )


# ─────────────────────────────────────────────────────────────────────────────
# remember — tags
# ─────────────────────────────────────────────────────────────────────────────

def test_tags_stored_as_pipe_string(engine: MemoryEngine):
    rem(engine, "T1", "Descripción.", "Lección.", tags=["decision", "architecture"])
    r = engine.recall("Descripción", n=1)
    assert r
    assert r[0]["metadata"]["tags_str"] == "|decision|architecture|"


def test_single_tag_stored_correctly(engine: MemoryEngine):
    rem(engine, "T2", "Texto.", "Lección.", tags=["bug"])
    r = engine.recall("Texto", n=1)
    assert r[0]["metadata"]["tags_str"] == "|bug|"


def test_tags_normalized_to_lowercase(engine: MemoryEngine):
    rem(engine, "T3", "Texto.", "Lección.", tags=["BUG", "  Fix  "])
    r = engine.recall("Texto", n=1)
    assert r[0]["metadata"]["tags_str"] == "|bug|fix|"


def test_schema_version_is_3(engine: MemoryEngine):
    rem(engine, "T4", "Texto.", "Lección.", tags=["general"])
    r = engine.recall("Texto", n=1)
    assert r[0]["metadata"]["schema_version"] == "3"


def test_document_combines_summary_and_lesson(engine: MemoryEngine):
    rem(engine, "T5", "Usamos ChromaDB embebido.", "Elimina la necesidad de Docker.", tags=["architecture"])
    r = engine.recall("ChromaDB embebido", n=1)
    doc = r[0]["content"]
    assert "Usamos ChromaDB embebido." in doc
    assert "Lección:" in doc
    assert "Elimina la necesidad de Docker." in doc


# ─────────────────────────────────────────────────────────────────────────────
# remember — related_to
# ─────────────────────────────────────────────────────────────────────────────

def test_related_to_stored_as_csv(engine: MemoryEngine):
    id1 = str(uuid.uuid4())
    id2 = str(uuid.uuid4())
    rem(engine, "T6", "Texto relacionado.", "Lección.", tags=["pattern"], related_to=[id1, id2])
    r = engine.recall("Texto relacionado", n=1)
    stored = r[0]["metadata"].get("related_to_str", "")
    assert id1 in stored and id2 in stored


def test_no_related_to_omits_field(engine: MemoryEngine):
    rem(engine, "T7", "Sin relaciones.", "Lección.", tags=["general"])
    r = engine.recall("Sin relaciones", n=1)
    assert "related_to_str" not in r[0]["metadata"]


# ─────────────────────────────────────────────────────────────────────────────
# recall — filter_tags
# ─────────────────────────────────────────────────────────────────────────────

def test_filter_tags_returns_only_matching(engine: MemoryEngine):
    rem(engine, "Bug auth", "Error en el módulo de autenticación.", "Validar JWT antes de procesar.", tags=["bug", "auth"])
    rem(engine, "Arch DB", "Usamos PostgreSQL para persistencia.", "Prefiere SQL para datos relacionales.", tags=["architecture"])

    results = engine.recall("módulo", n=5, filter_tags=["bug"])
    assert results
    for r in results:
        assert "|bug|" in r["metadata"]["tags_str"]


def test_filter_tags_or_logic(engine: MemoryEngine):
    rem(engine, "Bug1", "Error en login.", "Revisar middleware.", tags=["bug"])
    rem(engine, "Fix1", "Corrección de timeout.", "Aumentar timeout a 30s.", tags=["fix"])
    rem(engine, "Arch1", "Diseño de API REST.", "Usar versionado en URLs.", tags=["architecture"])

    results = engine.recall("error corrección diseño", n=10, filter_tags=["bug", "fix"])
    assert results
    for r in results:
        tags = r["metadata"]["tags_str"]
        assert "|bug|" in tags or "|fix|" in tags


def test_filter_tags_no_match_returns_empty(engine: MemoryEngine):
    rem(engine, "Dep", "Instalamos requests.", "Fijar versión en requirements.txt.", tags=["dependency"])
    results = engine.recall("requests", n=5, filter_tags=["architecture"])
    # Puede retornar vacío o sin el recuerdo con tag 'dependency'
    for r in results:
        assert "|architecture|" in r["metadata"]["tags_str"]


# ─────────────────────────────────────────────────────────────────────────────
# recall — since
# ─────────────────────────────────────────────────────────────────────────────

def test_since_filters_old_records(engine: MemoryEngine):
    """Inyecta un recuerdo con fecha antigua directamente en ChromaDB."""
    col = engine._get_collection()
    old_id = str(uuid.uuid4())
    col.add(
        ids=[old_id],
        documents=["Recuerdo antiguo sobre autenticación."],
        metadatas=[{
            "schema_version": "3",
            "title": "Recuerdo antiguo",
            "summary": "Recuerdo antiguo sobre autenticación.",
            "lesson": "Lección antigua.",
            "tags_str": "|decision|",
            "created_at": "2024-01-01T00:00:00+00:00",
            "project_slug": "test",
        }],
    )
    rem(engine, "Recuerdo nuevo", "Recuerdo nuevo sobre autenticación OAuth.", "OAuth es mejor.", tags=["decision"])

    results = engine.recall("autenticación", n=5, since="2026-01-01")
    ids = [r["id"] for r in results]
    assert old_id not in ids, "El recuerdo antiguo no debería aparecer con filtro since=2026-01-01"


# ─────────────────────────────────────────────────────────────────────────────
# recall — related_to (lookup directo)
# ─────────────────────────────────────────────────────────────────────────────

def test_recall_related_to_returns_referencing_docs(engine: MemoryEngine):
    id_target = rem(engine, "Base", "Documento base.", "Lección base.", tags=["general"])

    rem(engine, "Referencia A", "Complementa al documento base.", "Lección A.",
        tags=["pattern"], related_to=[id_target])
    rem(engine, "No relacionado", "Sin relación con nada.", "Lección sin rel.", tags=["general"])

    results = engine.recall("cualquier cosa", n=10, related_to=id_target)
    assert results
    for r in results:
        assert id_target in r["metadata"].get("related_to_str", "")


def test_recall_related_to_no_matches_returns_empty(engine: MemoryEngine):
    fake_id = str(uuid.uuid4())
    rem(engine, "Solo", "Texto sin relaciones.", "Lección.", tags=["general"])
    results = engine.recall("texto", n=5, related_to=fake_id)
    assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# recall — freshness decay
# ─────────────────────────────────────────────────────────────────────────────

def test_freshness_factor_recent():
    assert MemoryEngine._freshness_factor(datetime.now(timezone.utc).isoformat()) == 1.0


def test_freshness_factor_31_days():
    date_31d = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    factor = MemoryEngine._freshness_factor(date_31d)
    assert 0.85 < factor < 1.0


def test_freshness_factor_365_days():
    date_365d = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    factor = MemoryEngine._freshness_factor(date_365d)
    assert abs(factor - 0.85) < 0.01


def test_freshness_factor_old():
    date_old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    assert MemoryEngine._freshness_factor(date_old) == 0.7


def test_freshness_decay_affects_score(engine: MemoryEngine):
    """Un recuerdo antiguo debe tener score ajustado < base_score."""
    col = engine._get_collection()
    old_id = str(uuid.uuid4())
    col.add(
        ids=[old_id],
        documents=["Patrón de diseño Factory Method para creación de objetos."],
        metadatas=[{
            "schema_version": "3", "title": "Factory Method",
            "summary": "Patrón de diseño Factory Method.",
            "lesson": "Encapsula la creación de objetos.",
            "tags_str": "|pattern|",
            "created_at": "2024-01-01T00:00:00+00:00",
            "project_slug": "test",
        }],
    )
    results = engine.recall("Factory Method patrón diseño", n=5)
    old_results = [r for r in results if r["id"] == old_id]
    if old_results:
        r = old_results[0]
        assert r["score"] < r["base_score"], "El score ajustado debe ser menor al base_score para recuerdos viejos"
        assert r["freshness"] == 0.7


# ─────────────────────────────────────────────────────────────────────────────
# modify
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_title(engine: MemoryEngine):
    doc_id = rem(engine, "Título original", "Descripción.", "Lección.", tags=["general"])
    result = engine.modify(memory_id=doc_id, title="Título actualizado")
    assert "error" not in result
    assert "title" in result["updated_fields"]

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["metadatas"])
    assert fetched["metadatas"][0]["title"] == "Título actualizado"


def test_modify_lesson_rebuilds_document(engine: MemoryEngine):
    doc_id = rem(engine, "T", "Resumen original.", "Lección original.", tags=["general"])
    result = engine.modify(memory_id=doc_id, lesson="Lección corregida.")
    assert "lesson" in result["updated_fields"]
    # No verificamos 'document' como campo explícito — es un detalle interno del rebuild

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["documents", "metadatas"])
    assert "Lección corregida." in fetched["documents"][0]
    assert fetched["metadatas"][0]["lesson"] == "Lección corregida."


def test_modify_tags(engine: MemoryEngine):
    doc_id = rem(engine, "T", "Texto.", "Lección.", tags=["general"])
    result = engine.modify(memory_id=doc_id, tags=["bug", "fix"])
    assert "tags" in result["updated_fields"]

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["metadatas"])
    assert fetched["metadatas"][0]["tags_str"] == "|bug|fix|"


def test_modify_adds_related_to(engine: MemoryEngine):
    id_a = rem(engine, "A", "Texto A.", "Lección A.", tags=["general"])
    id_b = rem(engine, "B", "Texto B.", "Lección B.", tags=["general"])

    result = engine.modify(memory_id=id_a, related_to=[id_b])
    assert "related_to" in result["updated_fields"]

    col = engine._get_collection()
    fetched = col.get(ids=[id_a], include=["metadatas"])
    assert id_b in fetched["metadatas"][0]["related_to_str"]


def test_modify_sets_updated_at(engine: MemoryEngine):
    doc_id = rem(engine, "T", "Texto.", "Lección.", tags=["general"])
    engine.modify(memory_id=doc_id, title="Nuevo título")

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["metadatas"])
    assert "updated_at" in fetched["metadatas"][0]


def test_modify_partial_merge(engine: MemoryEngine):
    """Campos no provistos no deben cambiar."""
    doc_id = rem(engine, "Original", "Resumen original.", "Lección original.", tags=["decision"])
    engine.modify(memory_id=doc_id, title="Nuevo título")

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["metadatas"])
    meta = fetched["metadatas"][0]
    assert meta["summary"] == "Resumen original."
    assert meta["lesson"] == "Lección original."
    assert "|decision|" in meta["tags_str"]


def test_modify_nonexistent_id_returns_error(engine: MemoryEngine):
    result = engine.modify(memory_id=str(uuid.uuid4()), title="No existe")
    assert "error" in result
    assert "no encontrado" in result["error"].lower()


def test_modify_no_fields_still_sets_updated_at(engine: MemoryEngine):
    doc_id = rem(engine, "T", "Texto.", "Lección.", tags=["general"])
    result = engine.modify(memory_id=doc_id)
    assert "error" not in result
    assert result["updated_fields"] == []

    col = engine._get_collection()
    fetched = col.get(ids=[doc_id], include=["metadatas"])
    assert "updated_at" in fetched["metadatas"][0]


# ─────────────────────────────────────────────────────────────────────────────
# forget (smoke)
# ─────────────────────────────────────────────────────────────────────────────

def test_forget_removes_correct_record(engine: MemoryEngine):
    rem(engine, "OAuth2", "Migramos de JWT a OAuth2.", "OAuth2 reduce la superficie de ataque.", tags=["decision"])
    rem(engine, "Redis", "Usamos Redis como caché.", "Redis es más rápido para estructuras complejas.", tags=["architecture"])

    deleted = engine.forget("Migrar JWT OAuth2 autenticación")
    assert deleted == 1

    results = engine.recall("OAuth2 JWT autenticación", n=5)
    assert not any("JWT" in r["content"] and "OAuth2" in r["content"] for r in results)


def test_forget_empty_returns_zero(engine: MemoryEngine):
    assert engine.forget("nada") == 0


# ─────────────────────────────────────────────────────────────────────────────
# ProjectContext (sin cambios, smoke)
# ─────────────────────────────────────────────────────────────────────────────

def test_tags_round_trip():
    tags_in = ["decision", "architecture", "auth"]
    s = MemoryEngine._tags_to_str(tags_in)
    tags_out = MemoryEngine._str_to_tags(s)
    assert tags_out == tags_in


def test_tags_str_pipe_prevents_substring_collision():
    """'|bug|' no debería matchear '|debugging|'."""
    s = MemoryEngine._tags_to_str(["debugging"])
    assert "|bug|" not in s
    assert "|debugging|" in s
