from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

TEMPLATES_FILE_NAME = "skill_templates.json"
MCP_CONFIG_SPECIAL_SOURCE = "mcp_config"
ASSETS_DIR_NAME = "assets"

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
        asset = spec.get("asset")
        if isinstance(source, str) and source.strip():
            normalized_specs[str(relative_path)] = {"source": source}
            continue
        if isinstance(special, str) and special.strip():
            normalized_specs[str(relative_path)] = {"special": special}
            continue
        if isinstance(asset, str) and asset.strip():
            normalized_specs[str(relative_path)] = {"asset": asset}
            continue

        raise ValueError(
            "default install spec must define a non-empty 'source', 'special', or 'asset' field"
        )

    return normalized_specs


def _read_asset_bytes(asset_relative_path: str) -> bytes:
    assets_dir = Path(__file__).with_name(ASSETS_DIR_NAME)
    candidate = (assets_dir / asset_relative_path).resolve()
    try:
        candidate.relative_to(assets_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"asset path escapes assets directory: {asset_relative_path}") from exc

    if not candidate.is_file():
        raise ValueError(f"asset file not found: {asset_relative_path}")
    return candidate.read_bytes()


def _detect_onedrive_dir(home: Path) -> Path:
    env_candidates = [
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveCommercial"),
        os.environ.get("OneDriveConsumer"),
    ]
    for candidate in env_candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path

    discovered: list[Path] = []
    for pattern in ("OneDrive - *", "OneDrive*"):
        discovered.extend(path for path in home.glob(pattern) if path.is_dir())

    if discovered:
        discovered = sorted(set(discovered), key=lambda p: (0 if (p / "Documents").is_dir() else 1, len(p.name)))
        return discovered[0]

    return home / "OneDrive"


def _resolve_install_path(relative_path: str, *, home: Path) -> Path:
    rel_path = Path(relative_path)
    if rel_path.is_absolute():
        return rel_path

    parts = rel_path.parts
    if parts and parts[0].lower() == "onedrive":
        onedrive_dir = _detect_onedrive_dir(home)
        return onedrive_dir.joinpath(*parts[1:])

    return home / rel_path


def _resolve_default_mcp_command(
    *,
    which_func: Callable[[str], str | None],
    sys_executable: str,
) -> tuple[str, str, list[str]]:
    for candidate in SIVE_EXECUTABLE_CANDIDATES:
        executable_path = which_func(candidate)
        if executable_path:
            command_path = str(Path(executable_path).resolve())
            return command_path, str(Path(command_path).parent), ["serve"]

    command_path = sys_executable
    return command_path, str(Path(command_path).resolve().parent), ["-m", "sive", "serve"]


def _build_mcp_server_config(command: str, cwd: str, args: list[str]) -> str:
    payload = {
        "mcpServers": {
            "sive": {
                "command": command,
                "args": args,
                "cwd": cwd,
            }
        }
    }
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
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def install_skill_files_default_locations(
    target: str,
    *,
    home: Path | None = None,
    which_func: Callable[[str], str | None] | None = None,
    sys_executable: str | None = None,
) -> dict[str, list[Path]]:
    templates = _load_skill_templates()
    resolved_home = home if home is not None else Path.home()
    resolved_which = which_func if which_func is not None else shutil.which
    resolved_sys_executable = sys_executable if sys_executable is not None else sys.executable

    selected_targets = _selected_targets(target, templates)
    default_command, default_cwd, default_args = _resolve_default_mcp_command(
        which_func=resolved_which,
        sys_executable=resolved_sys_executable,
    )
    mcp_config = _build_mcp_server_config(command=default_command, cwd=default_cwd, args=default_args)

    written_by_target: dict[str, list[Path]] = {}
    for selected_target in selected_targets:
        rendered_files = _resolve_target_render_files(templates, selected_target)
        install_specs = _resolve_default_install_specs(templates, selected_target)

        written_by_target[selected_target] = []
        for relative_path, spec in install_specs.items():
            file_path = _resolve_install_path(relative_path, home=resolved_home)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if spec.get("special") == MCP_CONFIG_SPECIAL_SOURCE:
                content = mcp_config
                file_path.write_text(content, encoding="utf-8")
                written_by_target[selected_target].append(file_path)
                continue

            asset_name = spec.get("asset")
            if isinstance(asset_name, str) and asset_name.strip():
                file_path.write_bytes(_read_asset_bytes(asset_name))
                written_by_target[selected_target].append(file_path)
                continue

            source_name = spec.get("source", "")
            rendered_content = rendered_files.get(source_name)
            if rendered_content is None:
                raise ValueError(
                    f"source file '{source_name}' not found in rendered templates for target '{selected_target}'"
                )

            file_path.write_text(rendered_content, encoding="utf-8")
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

    if python_executable:
        command = python_executable
        args = ["-m", "sive", "serve"]
        resolved_cwd = cwd or str(Path(command).resolve().parent)
    else:
        command, default_cwd, args = _resolve_default_mcp_command(
            which_func=resolved_which,
            sys_executable=resolved_sys_executable,
        )
        resolved_cwd = cwd or default_cwd

    mcp_config = _build_mcp_server_config(command=command, cwd=resolved_cwd, args=args)
    written: list[Path] = []
    for selected_target in selected_targets:
        path = output_dir / f"{selected_target}.mcp.json"
        path.write_text(mcp_config, encoding="utf-8")
        written.append(path)

    return written
