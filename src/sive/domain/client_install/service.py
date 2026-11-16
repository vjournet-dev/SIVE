from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

import json5
import tomlkit

TEMPLATES_FILE_NAME = "skill_templates.json"
MCP_CONFIG_SPECIAL_SOURCE = "mcp_config"

# The first search waits for the embedding model to load, which exceeds the default client timeouts
# (Codex: 10 s startup and 60 s per tool call, Copilot CLI: 180 s per tool call).
CODEX_STARTUP_TIMEOUT_SEC = 60
CODEX_TOOL_TIMEOUT_SEC = 900
COPILOT_TIMEOUT_MS = 900_000

SIVE_EXECUTABLE_CANDIDATES = [
    "sive",
    "sive.exe",
    "sive.cmd",
    "sive.bat",
]


def _load_skill_templates() -> dict[str, Any]:
    templates_path = Path(__file__).with_name(TEMPLATES_FILE_NAME)
    payload = json.loads(templates_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("skill templates must be a JSON object")

    targets = payload.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise ValueError("skill templates must define a non-empty 'targets' object")

    common_render_files = payload.get("common_render_files", {})
    if not isinstance(common_render_files, dict):
        raise TypeError("skill templates 'common_render_files' must be an object")

    shared_texts = payload.get("shared_texts", {})
    if not isinstance(shared_texts, dict):
        raise TypeError("skill templates 'shared_texts' must be an object")

    return payload


def _resolve_text_spec(spec: Any, *, shared_texts: dict[str, Any]) -> str:
    if isinstance(spec, str):
        return spec

    if not isinstance(spec, dict):
        raise TypeError("text spec must be a string or object")

    if "ref" in spec:
        ref = spec["ref"]
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("text ref must be a non-empty string")
        referenced = shared_texts.get(ref)
        if referenced is None:
            raise ValueError(f"unknown text ref: {ref}")
        return _resolve_text_spec(referenced, shared_texts=shared_texts)

    if "lines" in spec:
        lines = spec["lines"]
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            raise ValueError("text lines must be a list of strings")
        return "\n".join(lines)

    if "text" in spec:
        text = spec["text"]
        if not isinstance(text, str):
            raise ValueError("text field must be a string")
        return text

    raise ValueError("text spec must define one of: ref, lines, text")


def _available_targets(templates: dict[str, Any]) -> list[str]:
    targets = templates.get("targets", {})
    return sorted(str(name) for name in targets)


def _selected_targets(target: str, templates: dict[str, Any]) -> list[str]:
    selected = target.strip().lower()
    available = _available_targets(templates)
    if selected == "all":
        return available
    if selected not in available:
        allowed = ", ".join(["all", *available])
        raise ValueError(f"target must be one of: {allowed}")
    return [selected]


def _resolve_target_render_files(templates: dict[str, Any], target: str) -> dict[str, str]:
    shared_texts = templates.get("shared_texts", {})
    common_render_files = templates.get("common_render_files", {})
    targets = templates.get("targets", {})
    target_payload = targets.get(target, {})

    render_files: dict[str, str] = {}

    for file_name, spec in common_render_files.items():
        render_files[str(file_name)] = _resolve_text_spec(spec, shared_texts=shared_texts)

    target_render_files = target_payload.get("render_files", {})
    if not isinstance(target_render_files, dict):
        raise TypeError(f"target '{target}' render_files must be an object")

    for file_name, spec in target_render_files.items():
        render_files[str(file_name)] = _resolve_text_spec(spec, shared_texts=shared_texts)

    return render_files


def _resolve_default_install_specs(templates: dict[str, Any], target: str) -> dict[str, dict[str, str]]:
    targets = templates.get("targets", {})
    target_payload = targets.get(target, {})
    install_specs = target_payload.get("default_install_files", {})

    if not isinstance(install_specs, dict):
        raise TypeError(f"target '{target}' default_install_files must be an object")

    normalized_specs: dict[str, dict[str, str]] = {}
    for relative_path, spec in install_specs.items():
        if not isinstance(spec, dict):
            raise TypeError(f"default install spec for '{target}' must be an object")

        source = spec.get("source")
        special = spec.get("special")
        if isinstance(source, str) and source.strip():
            normalized_specs[str(relative_path)] = {"source": source}
            continue
        if isinstance(special, str) and special.strip():
            normalized_specs[str(relative_path)] = {"special": special}
            continue
        raise ValueError("default install spec must define a non-empty 'source' or 'special' field")

    return normalized_specs


def _resolve_install_path(relative_path: str, *, home: Path) -> Path:
    rel_path = Path(relative_path)
    if rel_path.is_absolute():
        return rel_path

    return home / rel_path


def _resolve_mcp_command(
    *,
    python_executable: str | None,
    which_func: Callable[[str], str | None],
    sys_executable: str,
) -> tuple[str, list[str]]:
    if python_executable:
        return python_executable, ["-m", "sive", "serve"]

    for candidate in SIVE_EXECUTABLE_CANDIDATES:
        executable_path = which_func(candidate)
        if executable_path:
            return str(Path(executable_path).resolve()), ["serve"]

    return sys_executable, ["-m", "sive", "serve"]


def _apply_server_entry(servers: MutableMapping[str, Any], values: dict[str, Any], cwd: str | None) -> None:
    # Update an existing entry in place so options the user added (env, enabled tools...) survive a reinstall.
    # Without an explicit cwd the client keeps its own project directory, so a stale cwd is dropped.
    if cwd:
        values = {**values, "cwd": cwd}
    entry = servers.get("sive")
    if not isinstance(entry, MutableMapping):
        servers["sive"] = values
        return
    entry.update(values)
    if not cwd:
        entry.pop("cwd", None)


def _build_mcp_server_config(
    command: str,
    args: list[str],
    *,
    config_format: str,
    cwd: str | None = None,
    existing: str | None = None,
    jsonc: bool = False,
) -> str:
    values: dict[str, Any]
    if config_format == "codex":
        document = tomlkit.parse(existing) if existing is not None else tomlkit.document()
        servers = document.get("mcp_servers")
        if servers is None:
            document["mcp_servers"] = tomlkit.table()
            servers = document["mcp_servers"]
        if not isinstance(servers, (tomlkit.items.Table, tomlkit.items.InlineTable)):
            raise TypeError("MCP config 'mcp_servers' must be a table")
        values = {
            "command": command,
            "args": args,
            "startup_timeout_sec": CODEX_STARTUP_TIMEOUT_SEC,
            "tool_timeout_sec": CODEX_TOOL_TIMEOUT_SEC,
        }
        _apply_server_entry(servers, values, cwd)
        return tomlkit.dumps(document)

    payload = (
        (json5.loads(existing, allow_duplicate_keys=False) if jsonc else json.loads(existing))
        if existing is not None
        else {}
    )
    if not isinstance(payload, dict):
        raise TypeError("MCP config must be an object")

    if config_format == "opencode":
        payload.setdefault("$schema", "https://opencode.ai/config.json")
        mcp = payload.setdefault("mcp", {})
        if not isinstance(mcp, dict):
            raise TypeError("MCP config 'mcp' must be an object")
        # OpenCode V2 nests servers under mcp.servers; drop the deprecated direct mcp.sive entry.
        mcp.pop("sive", None)
        servers = mcp.setdefault("servers", {})
        values = {"type": "local", "command": [command, *args]}
    elif config_format in {"claude", "github"}:
        servers = payload.setdefault("mcpServers", {})
        values = {"type": "stdio", "command": command, "args": args}
        if config_format == "github":
            values.update({"type": "local", "tools": ["*"], "timeout": COPILOT_TIMEOUT_MS})
        else:
            cwd = None  # Claude Code has no cwd field for stdio servers
    else:
        raise ValueError(f"unsupported MCP config format: {config_format}")

    if not isinstance(servers, dict):
        raise TypeError("MCP servers must be an object")
    _apply_server_entry(servers, values, cwd)
    return json.dumps(payload, indent=2) + "\n"


def render_skill_files(target: str) -> dict[str, str]:
    templates = _load_skill_templates()
    selected_targets = _selected_targets(target, templates)

    files: dict[str, str] = {}
    for selected_target in selected_targets:
        files.update(_resolve_target_render_files(templates, selected_target))

    return files


def install_skill_files(target: str, output_dir: Path) -> list[Path]:
    files = render_skill_files(target)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in files.items():
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def install_skill_files_default_locations(
    target: str,
    *,
    home: Path | None = None,
    python_executable: str | None = None,
    cwd: str | None = None,
    which_func: Callable[[str], str | None] | None = None,
    sys_executable: str | None = None,
) -> dict[str, list[Path]]:
    templates = _load_skill_templates()
    resolved_home = home if home is not None else Path.home()
    resolved_which = which_func if which_func is not None else shutil.which
    resolved_sys_executable = sys_executable if sys_executable is not None else sys.executable

    selected_targets = _selected_targets(target, templates)
    command, args = _resolve_mcp_command(
        python_executable=python_executable,
        which_func=resolved_which,
        sys_executable=resolved_sys_executable,
    )

    planned_files: list[tuple[str, Path, str]] = []
    written_by_target: dict[str, list[Path]] = {}
    for selected_target in selected_targets:
        rendered_files = _resolve_target_render_files(templates, selected_target)
        install_specs = _resolve_default_install_specs(templates, selected_target)

        written_by_target[selected_target] = []
        for relative_path, spec in install_specs.items():
            file_path = _resolve_install_path(relative_path, home=resolved_home)
            if spec.get("special") == MCP_CONFIG_SPECIAL_SOURCE:
                config_format = templates["targets"][selected_target]["mcp_format"]
                if config_format == "opencode" and file_path.with_suffix(".jsonc").exists():
                    file_path = file_path.with_suffix(".jsonc")
                existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
                try:
                    content = _build_mcp_server_config(
                        command,
                        args,
                        config_format=config_format,
                        cwd=cwd,
                        existing=existing,
                        jsonc=file_path.suffix == ".jsonc",
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid MCP configuration at {file_path}: {exc}") from exc
                planned_files.append((selected_target, file_path, content))
                continue

            if "special" in spec:
                raise ValueError(f"unsupported install handler: {spec['special']}")

            source_name = spec.get("source", "")
            rendered_content = rendered_files.get(source_name)
            if rendered_content is None:
                raise ValueError(
                    f"source file '{source_name}' not found in rendered templates for target '{selected_target}'"
                )

            planned_files.append((selected_target, file_path, rendered_content))

    for selected_target, file_path, content in planned_files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        written_by_target[selected_target].append(file_path)

    return written_by_target


def install_client_mcp_configs(
    target: str,
    output_dir: Path,
    *,
    python_executable: str | None = None,
    cwd: str | None = None,
    which_func: Callable[[str], str | None] | None = None,
    sys_executable: str | None = None,
) -> list[Path]:
    templates = _load_skill_templates()
    resolved_which = which_func if which_func is not None else shutil.which
    resolved_sys_executable = sys_executable if sys_executable is not None else sys.executable

    selected_targets = _selected_targets(target, templates)
    output_dir.mkdir(parents=True, exist_ok=True)

    command, args = _resolve_mcp_command(
        python_executable=python_executable,
        which_func=resolved_which,
        sys_executable=resolved_sys_executable,
    )

    written: list[Path] = []
    for selected_target in selected_targets:
        target_spec = templates["targets"][selected_target]
        mcp_config = _build_mcp_server_config(command, args, config_format=target_spec["mcp_format"], cwd=cwd)
        path = output_dir / target_spec["mcp_output_file"]
        path.write_text(mcp_config, encoding="utf-8")
        written.append(path)

    return written
