"""
Tests for ProjectContext — Fase 2
"""
import os
import pytest
from pathlib import Path

# Ensure we can import server from parent dir without installing the package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import ProjectContext


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    """Directorio con .git/"""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture()
def gemini_project(tmp_path: Path) -> Path:
    """Directorio con .gemini_memory"""
    (tmp_path / ".gemini_memory").touch()
    return tmp_path


@pytest.fixture()
def nested_git_project(tmp_path: Path) -> Path:
    """Repo git con un subdirectorio anidado"""
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "src" / "module"
    nested.mkdir(parents=True)
    return tmp_path, nested  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Detección de raíz
# ─────────────────────────────────────────────────────────────────────────────

def test_detects_git_root(git_project: Path):
    ctx = ProjectContext(start_path=str(git_project))
    assert ctx.root == git_project


def test_detects_gemini_memory_root(gemini_project: Path):
    ctx = ProjectContext(start_path=str(gemini_project))
    assert ctx.root == gemini_project


def test_detects_root_from_nested_dir(tmp_path: Path):
    """Dado un subdirectorio, debe subir hasta encontrar .git"""
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "deep" / "path"
    nested.mkdir(parents=True)

    ctx = ProjectContext(start_path=str(nested))
    assert ctx.root == tmp_path


def test_fallback_to_start_when_no_markers(tmp_path: Path):
    """Sin marcadores, la raíz debe ser el start_path mismo."""
    ctx = ProjectContext(start_path=str(tmp_path))
    assert ctx.root == tmp_path


def test_uses_memory_cwd_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("MEMORY_CWD", str(tmp_path))
    ctx = ProjectContext()  # sin argumento
    assert ctx.root == tmp_path


def test_falls_back_to_cwd_when_no_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MEMORY_CWD", raising=False)
    monkeypatch.chdir(tmp_path)
    ctx = ProjectContext()
    assert ctx.root == tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Slug
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dir_name, expected_slug", [
    ("my-project", "my_project"),
    ("My Cool API", "my_cool_api"),
    ("agent-memory-mcp", "agent_memory_mcp"),
    ("simple", "simple"),
    ("123_numbers", "123_numbers"),
])
def test_slug_normalization(tmp_path: Path, dir_name: str, expected_slug: str):
    project_dir = tmp_path / dir_name
    project_dir.mkdir()
    (project_dir / ".git").mkdir()

    ctx = ProjectContext(start_path=str(project_dir))
    assert ctx.slug == expected_slug


# ─────────────────────────────────────────────────────────────────────────────
# memory_dir
# ─────────────────────────────────────────────────────────────────────────────

def test_memory_dir_is_created(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    ctx = ProjectContext(start_path=str(tmp_path))

    memory_dir = ctx.memory_dir
    assert memory_dir.exists()
    assert memory_dir.is_dir()
    assert memory_dir == tmp_path / ".memory"


def test_memory_dir_idempotent(tmp_path: Path):
    """Llamar memory_dir dos veces no debe fallar ni duplicar."""
    (tmp_path / ".git").mkdir()
    ctx = ProjectContext(start_path=str(tmp_path))

    _ = ctx.memory_dir
    _ = ctx.memory_dir  # segunda llamada no debe lanzar excepción
    assert (tmp_path / ".memory").is_dir()
