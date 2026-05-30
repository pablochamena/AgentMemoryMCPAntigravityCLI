# server_http.py
import os
import sys
from typing import Any, List, Optional
from fastmcp import FastMCP

# Aseguramos que la raíz del proyecto esté en el sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importamos la lógica ya testeada del server actual
from server import ProjectContext, MemoryEngine, MiniLMEmbeddingFunction

# Inicializamos FastMCP
mcp = FastMCP("agent-memory")

def get_engine(project_path: Optional[str] = None) -> tuple[MemoryEngine, ProjectContext]:
    """Resuelve el contexto adecuado de proyecto."""
    start_path = project_path or os.environ.get("MEMORY_CWD") or os.getcwd()
    ctx = ProjectContext(start_path=start_path)
    return MemoryEngine(ctx), ctx

@mcp.tool()
def remember(
    title: str,
    summary: str,
    lesson: str,
    tags: List[str],
    related_to: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
    project_path: Optional[str] = None
) -> str:
    """
    Guarda un recuerdo estructurado en la memoria del proyecto.
    Requiere title, summary, lesson y al menos un tag.
    """
    engine, ctx = get_engine(project_path)
    
    if not tags:
        return "Error: se requiere al menos un tag."
        
    doc_id = engine.remember(
        title=title,
        summary=summary,
        lesson=lesson,
        tags=tags,
        related_to=related_to,
        metadata=metadata
    )
    
    tags_display = " ".join(f"[{t}]" for t in tags)
    return (
        f"✅ Recuerdo guardado en '{ctx.slug}'\n"
        f"   Título : {title}\n"
        f"   Tags   : {tags_display}\n"
        f"   Lección: {lesson}\n"
        f"   ID     : {doc_id}"
    )

@mcp.tool()
def recall(
    query: str,
    n: int = 5,
    filter_tags: Optional[List[str]] = None,
    since: Optional[str] = None,
    related_to: Optional[str] = None,
    project_path: Optional[str] = None
) -> str:
    """
    Recupera recuerdos relevantes con búsqueda semántica y decaimiento por antigüedad.
    Soporta filtros por tags, fecha y relaciones.
    """
    engine, ctx = get_engine(project_path)
    results = engine.recall(
        query=query,
        n=n,
        filter_tags=filter_tags,
        since=since,
        related_to=related_to
    )
    
    if not results:
        return f"🔍 Sin recuerdos coincidentes en '{ctx.slug}'."
        
    lines = [f"🧠 {len(results)} recuerdo(s) en '{ctx.slug}':\n"]
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        schema = meta.get("schema_version", "1")
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
            lines.append(f"── [{i}] score={r['score']:.3f} | {created}\n{r['content']}")
            
    return "\n\n".join(lines)

@mcp.tool()
def modify(
    memory_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    lesson: Optional[str] = None,
    tags: Optional[List[str]] = None,
    related_to: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
    project_path: Optional[str] = None
) -> str:
    """Actualiza parcialmente un recuerdo existente (merge parcial)."""
    engine, ctx = get_engine(project_path)
    result = engine.modify(
        memory_id=memory_id,
        title=title,
        summary=summary,
        lesson=lesson,
        tags=tags,
        related_to=related_to,
        metadata=metadata
    )
    
    if "error" in result:
        return f"❌ {result['error']}"
        
    fields = ", ".join(result["updated_fields"]) if result["updated_fields"] else "(ninguno)"
    return (
        f"✏️ Recuerdo actualizado en '{ctx.slug}'\n"
        f"   ID             : {memory_id}\n"
        f"   Campos modificados: {fields}"
    )

@mcp.tool()
def forget(query: str, project_path: Optional[str] = None) -> str:
    """Borra el recuerdo más similar que coincida con la consulta dada."""
    engine, ctx = get_engine(project_path)
    deleted = engine.forget(query)
    if deleted:
        return f"🗑️ Recuerdo eliminado de '{ctx.slug}'."
    return f"ℹ️ No se encontraron recuerdos para eliminar en '{ctx.slug}'."

if __name__ == "__main__":
    # Arranca FastMCP usando transporte streamable-http, escuchando en todas las interfaces
    port = int(os.environ.get("MEMORY_PORT", 8009))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
