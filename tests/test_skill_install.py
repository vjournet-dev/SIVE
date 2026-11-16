import json
import tomllib

import pytest

from sive.__main__ import build_parser, cmd_install
from sive.domain.client_install import service as skill_install
from sive.infra.vector_store.embedding_loader import DEFAULT_EMBEDDING_MODEL_NAME


def test_rendered_skill_is_discoverable_and_uses_discovery_then_query(tmp_path):
    written = skill_install.install_skill_files("all", tmp_path)

    assert written == [tmp_path / "sive" / "SKILL.md", tmp_path / "opencode" / "commands" / "sive.md"]
    skill = written[0].read_text(encoding="utf-8")
    frontmatter, body = skill.removeprefix("---\n").split("\n---\n", 1)
    flat_frontmatter = " ".join(frontmatter.split())
    flat = " ".join(body.split())
    description = flat_frontmatter.split("description: >- ", 1)[1].split(" argument-hint:", 1)[0]
    assert "name: sive" in frontmatter
    assert "description: >-" in frontmatter
    assert len(description) <= 1024
    assert "before answering questions or writing code" in description
    for dependency in ("library", "framework", "SDK", "API", "CLI", "cloud service"):
        assert dependency in description
    for task in ("usage", "configuration", "setup", "migration", "errors", "version differences"):
        assert task in description
    assert "/sive command" in description
    assert 'argument-hint: "add <url|topic|path> | update <site_id|path> | list | remove <doc_id> | help"' in frontmatter
    assert body.index("list_documentation_sites_in_database") < body.index("search_documentation")
    assert "mcp__sive__<tool>" in flat
    assert "sive-<tool>" in flat
    assert "sive_<tool>" in flat
    assert "reuse the site identifiers" in flat
    assert "separate searches, in parallel" in flat
    assert "first call after the server starts that reads the index" in flat
    assert "source URLs" in flat
    assert "sive ingest --start-url" in flat
    assert "no standalone list/search command" in flat
    assert "needs_confirmation" in flat
    assert "never call it unless the user asked to remove that source" in flat
    assert "Never broaden prefixes" in flat
    assert "absolute paths" in flat
    assert "wait_for_ingest_completion" in flat
    assert "never ask for passwords" in flat
    assert "system_prompt" not in skill.lower()
    assert not list(tmp_path.rglob("*PROMPT*"))

    command = written[1].read_text(encoding="utf-8")
    assert command.startswith("---\ndescription: ")
    assert "`sive` skill" in command
    assert "/sive $ARGUMENTS" in command


def test_default_install_uses_native_skill_paths_and_mcp_formats(tmp_path):
    written = skill_install.install_skill_files_default_locations(
        "all",
        home=tmp_path,
        which_func=lambda _: str(tmp_path / "bin" / "sive"),
    )

    assert set(written) == {"github", "claude", "codex", "opencode"}
    paths = {
        "github": [".copilot/skills/sive/SKILL.md", ".copilot/mcp-config.json"],
        "claude": [".claude/skills/sive/SKILL.md", ".claude.json"],
        "codex": [".agents/skills/sive/SKILL.md", ".codex/config.toml"],
        "opencode": [
            ".config/opencode/skills/sive/SKILL.md",
            ".config/opencode/commands/sive.md",
            ".config/opencode/opencode.json",
        ],
    }
    for target, relative_paths in paths.items():
        assert written[target] == [tmp_path / path for path in relative_paths]
        assert (tmp_path / relative_paths[0]).read_text(encoding="utf-8").startswith("---\n")
    assert "$ARGUMENTS" in (tmp_path / ".config/opencode/commands/sive.md").read_text(encoding="utf-8")

    # No cwd is written by default: each client starts the server from the project directory.
    command = str((tmp_path / "bin" / "sive").resolve())
    github = json.loads((tmp_path / ".copilot/mcp-config.json").read_text(encoding="utf-8"))
    assert github["mcpServers"]["sive"] == {
        "type": "local",
        "command": command,
        "args": ["serve"],
        "tools": ["*"],
        "timeout": 900_000,
    }
    claude = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["sive"] == {"type": "stdio", "command": command, "args": ["serve"]}
    codex = tomllib.loads((tmp_path / ".codex/config.toml").read_text(encoding="utf-8"))
    assert codex["mcp_servers"]["sive"] == {
        "command": command,
        "args": ["serve"],
        "startup_timeout_sec": 60,
        "tool_timeout_sec": 900,
    }
    opencode = json.loads((tmp_path / ".config/opencode/opencode.json").read_text(encoding="utf-8"))
    assert opencode["$schema"] == "https://opencode.ai/config.json"
    assert set(opencode["mcp"]) == {"servers"}
    assert opencode["mcp"]["servers"]["sive"] == {"type": "local", "command": [command, "serve"]}
    assert not list(tmp_path.rglob("*PROMPT*"))


@pytest.mark.parametrize("target", ["github", "claude", "codex", "opencode"])
def test_custom_output_uses_native_format_and_python_override(target, tmp_path):
    command = str(tmp_path / "Python Tools" / "python.exe")
    cwd = str(tmp_path / "workspace")
    written = skill_install.install_client_mcp_configs(
        target,
        tmp_path,
        python_executable=command,
        cwd=cwd,
    )
    content = written[0].read_text(encoding="utf-8")
    if target == "codex":
        assert written[0].name == "codex.mcp.toml"
        server = tomllib.loads(content)["mcp_servers"]["sive"]
    elif target == "opencode":
        server = json.loads(content)["mcp"]["servers"]["sive"]
        assert server["command"] == [command, "-m", "sive", "serve"]
        assert server["cwd"] == cwd
        return
    else:
        server = json.loads(content)["mcpServers"]["sive"]
    assert server["command"] == command
    assert server["args"] == ["-m", "sive", "serve"]
    if target != "claude":
        assert server["cwd"] == cwd


@pytest.mark.parametrize(
    ("target", "config_path", "payload", "server_key"),
    [
        (
            "github",
            ".copilot/mcp-config.json",
            {"theme": "dark", "mcpServers": {"other": {"command": "other"}}},
            "mcpServers",
        ),
        (
            "claude",
            ".claude.json",
            {"projects": {"workspace": {"trusted": True}}, "mcpServers": {"other": {"command": "other"}}},
            "mcpServers",
        ),
    ],
)
def test_json_install_preserves_other_settings_and_is_idempotent(target, config_path, payload, server_key, tmp_path):
    path = tmp_path / config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    kwargs = {"home": tmp_path, "which_func": lambda _: None, "sys_executable": str(tmp_path / "python")}
    skill_install.install_skill_files_default_locations(target, **kwargs)
    first = path.read_text(encoding="utf-8")
    skill_install.install_skill_files_default_locations(target, **kwargs)
    assert path.read_text(encoding="utf-8") == first
    updated = json.loads(first)
    updated[server_key].pop("sive")
    assert updated == payload


def test_reinstall_keeps_extra_json_options_and_drops_stale_cwd(tmp_path):
    path = tmp_path / ".copilot" / "mcp-config.json"
    path.parent.mkdir()
    previous = {"type": "local", "command": "old", "cwd": "C:/old", "env": {"SIVE_DATA_DIR": "D:/sive"}}
    path.write_text(json.dumps({"mcpServers": {"sive": previous}}), encoding="utf-8")

    skill_install.install_skill_files_default_locations(
        "github",
        home=tmp_path,
        which_func=lambda _: None,
        sys_executable=str(tmp_path / "python"),
    )

    server = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["sive"]
    assert server["env"] == {"SIVE_DATA_DIR": "D:/sive"}
    assert server["command"] == str(tmp_path / "python")
    assert server["args"] == ["-m", "sive", "serve"]
    assert "cwd" not in server


def test_codex_reinstall_keeps_extra_options_and_drops_stale_cwd_idempotently(tmp_path):
    path = tmp_path / ".codex" / "config.toml"
    path.parent.mkdir()
    path.write_text(
        '[mcp_servers.sive]\ncommand = "old"\ncwd = "C:/old"\n\n[mcp_servers.sive.env]\nSIVE_DATA_DIR = "D:/sive"\n',
        encoding="utf-8",
    )
    kwargs = {"home": tmp_path, "which_func": lambda _: None, "sys_executable": str(tmp_path / "python")}

    skill_install.install_skill_files_default_locations("codex", **kwargs)
    first = path.read_text(encoding="utf-8")
    skill_install.install_skill_files_default_locations("codex", **kwargs)

    assert path.read_text(encoding="utf-8") == first
    server = tomllib.loads(first)["mcp_servers"]["sive"]
    assert server["env"] == {"SIVE_DATA_DIR": "D:/sive"}
    assert server["command"] == str(tmp_path / "python")
    assert server["tool_timeout_sec"] == 900
    assert "cwd" not in server


def test_codex_install_preserves_toml_settings_comments_and_other_servers(tmp_path):
    path = tmp_path / ".codex" / "config.toml"
    path.parent.mkdir()
    original = (
        '# Keep my preferences\nmodel = "my-model"\n'
        '\n[mcp_servers.other]\ncommand = "other" # existing server\n'
        '\n[mcp_servers.sive]\ncommand = "old"\nargs = ["old"]\n'
        '\n[projects."C:\\\\Workspace"]\ntrust_level = "trusted"\n'
    )
    path.write_text(original, encoding="utf-8")
    for _ in range(2):
        skill_install.install_skill_files_default_locations(
            "codex",
            home=tmp_path,
            python_executable=str(tmp_path / "Python" / "python.exe"),
            cwd=str(tmp_path / "work"),
            which_func=lambda _: None,
        )
    updated = path.read_text(encoding="utf-8")
    before = tomllib.loads(original)
    after = tomllib.loads(updated)
    assert after["model"] == before["model"]
    assert after["projects"] == before["projects"]
    assert after["mcp_servers"]["other"] == before["mcp_servers"]["other"]
    assert after["mcp_servers"]["sive"]["args"] == ["-m", "sive", "serve"]
    assert after["mcp_servers"]["sive"]["cwd"] == str(tmp_path / "work")
    assert "# Keep my preferences" in updated
    assert "# existing server" in updated


def test_opencode_install_updates_existing_jsonc_without_shadow_config(tmp_path):
    path = tmp_path / ".config" / "opencode" / "opencode.jsonc"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{ // user preferences\n "model": "my-model", "mcp": {"servers": {'
        '"other": {"type": "local", "command": ["other"]},}},}',
        encoding="utf-8",
    )
    written = skill_install.install_skill_files_default_locations(
        "opencode",
        home=tmp_path,
        which_func=lambda _: None,
        sys_executable=str(tmp_path / "python"),
    )
    assert path in written["opencode"]
    assert not path.with_suffix(".json").exists()
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["model"] == "my-model"
    assert after["mcp"]["servers"]["other"]["command"] == ["other"]
    assert after["mcp"]["servers"]["sive"]["command"] == [str(tmp_path / "python"), "-m", "sive", "serve"]


def test_opencode_install_migrates_deprecated_direct_mcp_entry(tmp_path):
    path = tmp_path / ".config" / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    legacy_other = {"type": "local", "command": ["other"]}
    path.write_text(
        json.dumps({"mcp": {"sive": {"type": "local", "command": ["old"]}, "other": legacy_other}}),
        encoding="utf-8",
    )
    skill_install.install_skill_files_default_locations(
        "opencode",
        home=tmp_path,
        which_func=lambda _: None,
        sys_executable=str(tmp_path / "python"),
    )
    mcp = json.loads(path.read_text(encoding="utf-8"))["mcp"]
    assert "sive" not in mcp
    assert mcp["other"] == legacy_other
    assert mcp["servers"]["sive"]["command"] == [str(tmp_path / "python"), "-m", "sive", "serve"]


@pytest.mark.parametrize(
    ("target", "config_path", "content"),
    [
        ("github", ".copilot/mcp-config.json", '{"mcpServers": []}'),
        ("claude", ".claude.json", '{"broken":'),
        ("claude", ".claude.json", "[]"),
        ("codex", ".codex/config.toml", "mcp_servers = []"),
        ("codex", ".codex/config.toml", "[broken"),
        ("opencode", ".config/opencode/opencode.jsonc", '{"mcp": {"servers": []}}'),
    ],
)
def test_invalid_existing_config_is_reported_without_overwrite_or_partial_install(
    target,
    config_path,
    content,
    tmp_path,
):
    path = tmp_path / config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid MCP configuration"):
        skill_install.install_skill_files_default_locations(
            target,
            home=tmp_path,
            which_func=lambda _: None,
            sys_executable=str(tmp_path / "python"),
        )
    assert path.read_text(encoding="utf-8") == content
    assert not list(tmp_path.rglob("SKILL.md"))


@pytest.mark.parametrize("target", ["copilot", "gpt", "gemini", "mistral", "microsoft-cowork"])
def test_removed_targets_are_rejected_by_cli_and_service(target):
    with pytest.raises(ValueError, match="target must be one of"):
        skill_install.render_skill_files(target)
    with pytest.raises(SystemExit):
        build_parser().parse_args(["install", "--target", target])


def test_cli_default_install_passes_python_and_cwd_overrides(monkeypatch, tmp_path):
    def install(target, **kwargs):
        assert target == "github"
        assert kwargs["python_executable"] == str(tmp_path / "python.exe")
        assert kwargs["cwd"] == str(tmp_path / "work")
        return {}

    monkeypatch.setattr("sive.__main__.install_skill_files_default_locations", install)
    args = build_parser().parse_args(
        [
            "install",
            "--target",
            "github",
            "--python-executable",
            str(tmp_path / "python.exe"),
            "--mcp-cwd",
            str(tmp_path / "work"),
            "--skip-model-download",
        ]
    )
    cmd_install(args)


def _record_model_loads(monkeypatch, *, error: Exception | None = None) -> list[str]:
    loaded: list[str] = []

    def load(model_name):
        loaded.append(model_name)
        if error is not None:
            raise error
        return object()

    monkeypatch.setattr("sive.__main__.get_sentence_transformer_embedding_function", load)
    monkeypatch.setattr("sive.__main__.install_skill_files_default_locations", lambda target, **kwargs: {})
    return loaded


def test_cli_default_install_prefetches_server_embedding_model(monkeypatch):
    loaded = _record_model_loads(monkeypatch)

    cmd_install(build_parser().parse_args(["install", "--target", "codex"]))

    assert loaded == [DEFAULT_EMBEDDING_MODEL_NAME]


@pytest.mark.parametrize("extra_args", [["--skip-model-download"], ["--output-dir", "{tmp}"]])
def test_cli_install_skips_model_prefetch(monkeypatch, tmp_path, extra_args):
    loaded = _record_model_loads(monkeypatch)
    argv = ["install", "--target", "github", *(arg.replace("{tmp}", str(tmp_path)) for arg in extra_args)]

    cmd_install(build_parser().parse_args(argv))

    assert loaded == []


def test_cli_install_model_prefetch_failure_is_not_fatal(monkeypatch, capsys):
    loaded = _record_model_loads(monkeypatch, error=OSError("network unreachable"))

    cmd_install(build_parser().parse_args(["install", "--target", "claude"]))

    assert loaded == [DEFAULT_EMBEDDING_MODEL_NAME]
    output = capsys.readouterr().out
    assert "network unreachable" in output
    assert "premier appel MCP" in output


def test_windows_executable_detection_and_module_fallback(tmp_path):
    executable = str(tmp_path / "bin" / "sive.exe")
    skill_install.install_client_mcp_configs(
        "github",
        tmp_path,
        which_func=lambda name: executable if name == "sive.exe" else None,
    )
    path = tmp_path / "github.mcp.json"
    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["sive"]["command"] == executable
    skill_install.install_client_mcp_configs(
        "github",
        tmp_path,
        which_func=lambda _: None,
        sys_executable=str(tmp_path / "python.exe"),
    )
    server = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["sive"]
    assert server["command"] == str(tmp_path / "python.exe")
    assert server["args"] == ["-m", "sive", "serve"]
