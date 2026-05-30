#!/usr/bin/env python3
"""
smoke_test.py — Prueba manual del servidor agent-memory-mcp
============================================================
Simula lo que hace Gemini CLI: instancia las clases directamente
y ejercita remember → recall → forget → recall.

Uso:
    # Desde el directorio de cualquier proyecto Git:
    cd ~/mi-proyecto
    MEMORY_CWD=$PWD python3 /path/to/agent-memory-mcp/smoke_test.py

    # O desde el propio repo (usa agent-memory-mcp como proyecto):
    cd ~/Programacion/personal/agent-memory-mcp
    python3 smoke_test.py
"""

import os
import sys
from pathlib import Path

# Aseguramos que el venv del repo esté en el path
REPO_DIR = Path(__file__).parent
VENV_SITE = REPO_DIR / "venv" / "lib"

# Añadir site-packages del venv si no estamos ya dentro de él
if str(VENV_SITE) not in sys.path and VENV_SITE.exists():
    import glob
    for sp in glob.glob(str(VENV_SITE / "python3.*" / "site-packages")):
        sys.path.insert(0, sp)
        break

sys.path.insert(0, str(REPO_DIR))

# ─── Imports después de ajustar el path ────────────────────────────────────
from server import ProjectContext, MemoryEngine  # noqa: E402

SEP = "─" * 60

def header(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg: str):
    print(f"  ✅ {msg}")

def info(msg: str):
    print(f"  ℹ️  {msg}")

def result(label: str, value):
    print(f"  {label}: {value}")


def main():
    print("\n🧪 agent-memory-mcp — Smoke Test")
    print("=" * 60)

    # ── 1. Detección de proyecto ──────────────────────────────────
    header("1. Detección de proyecto (ProjectContext)")

    cwd = os.environ.get("MEMORY_CWD") or os.getcwd()
    info(f"Directorio de inicio: {cwd}")

    ctx = ProjectContext(start_path=cwd)
    result("Raíz detectada", ctx.root)
    result("Slug del proyecto", repr(ctx.slug))
    result("Directorio .memory", ctx.memory_dir)
    ok("ProjectContext inicializado correctamente")

    # ── 2. Guardar recuerdos ──────────────────────────────────────
    header("2. remember() — Guardar recuerdos")

    engine = MemoryEngine(ctx)

    id1 = engine.remember(
        title="Selección de ChromaDB",
        summary="Usamos ChromaDB como vector store embebido porque no requiere servidor externo.",
        lesson="ChromaDB local evita depender de infraestructura o Docker en desarrollo.",
        tags=["decision", "dependency"],
        metadata={"context": "selección de base de datos"},
    )
    ok(f"Recuerdo 1 guardado: id={id1[:8]}...")

    id2 = engine.remember(
        title="Modelo de Embeddings",
        summary="El modelo de embeddings es all-MiniLM-L6-v2, liviano (~90 MB), sin GPU.",
        lesson="sentence-transformers local es rápido y no consume recursos de nube.",
        tags=["architecture", "dependency"],
    )
    ok(f"Recuerdo 2 guardado: id={id2[:8]}...")

    id3 = engine.remember(
        title="Bug deprecación ChromaDB",
        summary="Error resuelto: ChromaDB DeprecationWarning por falta de name() en EmbeddingFunction.",
        lesson="Implementar name() en la clase de embeddings evita avisos de deprecación.",
        tags=["fix", "bug"],
        metadata={"ticket": "internal-001"},
    )
    ok(f"Recuerdo 3 guardado: id={id3[:8]}...")

    # ── 3. Recuperar recuerdos ────────────────────────────────────
    header("3. recall() — Búsqueda semántica")

    query = "base de datos vectorial"
    info(f"Query: '{query}'")
    results = engine.recall(query, n=3)

    if not results:
        print("  ⚠️  No se encontraron resultados — algo falló")
        sys.exit(1)

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] score={r['score']:.3f}  tipo={r['metadata'].get('memory_type', '?')}")
        print(f"       {r['content'][:80]}{'...' if len(r['content']) > 80 else ''}")

    ok(f"{len(results)} resultado(s) encontrados")

    # ── 4. Borrar un recuerdo ─────────────────────────────────────
    header("4. forget() — Borrar el más relevante")

    query_forget = "ChromaDB vector store embebido"
    info(f"Query de borrado: '{query_forget}'")
    deleted = engine.forget(query_forget)

    if deleted:
        ok("Recuerdo eliminado correctamente")
    else:
        print("  ⚠️  No se eliminó ningún recuerdo")

    # ── 5. Verificar aislamiento ──────────────────────────────────
    header("5. Verificar que el borrado fue efectivo")

    results_after = engine.recall("ChromaDB vector store", n=5)
    contents_after = [r["content"] for r in results_after]
    deleted_still_present = any("no requiere servidor externo" in c for c in contents_after)

    if not deleted_still_present:
        ok("El recuerdo borrado ya no aparece en recall ✓")
    else:
        print("  ⚠️  El recuerdo aún aparece — el borrado no funcionó correctamente")

    # ── 6. Resumen ────────────────────────────────────────────────
    header("Resumen final")
    result("Proyecto", f"{ctx.slug} ({ctx.root})")
    result("Colección ChromaDB", ctx.memory_dir / "chroma.sqlite3")
    docs_remaining = engine._get_collection().count()
    result("Documentos en colección", docs_remaining)
    print()
    print("  🎉 Smoke test completado. El servidor está listo para Gemini CLI.")
    print()


if __name__ == "__main__":
    main()
