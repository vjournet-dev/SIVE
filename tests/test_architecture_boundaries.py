from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src/sive")
DOMAIN_ROOT = SRC_ROOT / "domain"
APP_MCP_ROOT = SRC_ROOT / "app" / "mcp_server"


def _python_files(root: Path):
    return sorted(root.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def test_domain_never_imports_application_layer():
    violations = []
    for path in _python_files(DOMAIN_ROOT):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            if any(name == "app" or name.startswith("app.") or ".app." in name for name in imported):
                violations.append(f"{path}: {', '.join(imported)}")
    assert violations == []


def test_mcp_tools_do_not_query_vector_store_directly():
    violations = []
    for path in sorted(APP_MCP_ROOT.glob("tools_*.py")):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver = node.func.value
                if (
                    node.func.attr in {"query", "get", "delete", "upsert"}
                    and isinstance(receiver, ast.Name)
                    and receiver.id == "collection"
                ):
                    violations.append(f"{path}: direct {node.func.attr}() call")
    assert violations == []


def test_application_does_not_redefine_canonical_domain_symbols():
    forbidden = {
        "derive_allowed_path_prefix",
        "find_best_topic_route",
        "format_ranked_search_results",
        "format_search_results",
        "normalize_topic",
        "rank_search_results",
        "rerank_search_results",
        "score_start_path",
        "site_from_indexed_metadatas",
        "site_from_latest_job",
        "site_from_topic_routes",
    }
    violations = []
    for path in _python_files(APP_MCP_ROOT):
        tree = _parse(path)
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        for duplicate in sorted(defined & forbidden):
            violations.append(f"{path}: {duplicate}")
    assert violations == []


def test_obsolete_app_core_module_is_removed():
    assert not (APP_MCP_ROOT / "core.py").exists()
