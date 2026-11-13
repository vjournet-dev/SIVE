import json
import tomllib

import pytest

from sive.__main__ import build_parser, cmd_install
from sive.domain.client_install import service as skill_install


def test_rendered_skill_is_discoverable_and_uses_discovery_then_query(tmp_path):
    written = skill_install.install_skill_files("all", tmp_path)

    assert written == [tmp_path / "sive" / "SKILL.md"]
    skill = written[0].read_text(encoding="utf-8")
    frontmatter, body = skill.removeprefix("---\n").split("\n---\n", 1)
    assert "name: sive" in frontmatter
    assert "description: >-" in frontmatter
    assert "when relevant documentation is discovered" in frontmatter
    assert body.index("list_documentation_sites_in_database") < body.index("search_documentation")
    assert "separate searches" in body
    assert "source URLs" in body
    assert "sive ingest --start-url" in body
    assert "no standalone list/search command" in body
    assert "needs_confirmation" in body
    assert "Never broaden prefixes" in body
    assert "wait_for_ingest_completion" in body
    assert "never\nask for passwords" in body
    assert "system_prompt" not in skill.lower()
    assert not list(tmp_path.rglob("*PROMPT*"))


def test_default_install_uses_native_skill_paths_and_mcp_formats(tmp_path):
    written = skill_install.install_skill_files_default_locations(
        "all",
        home=tmp_path,
        which_func=lambda _: str(tmp_path / "bin" / "sive"),
    )

    assert set(written) == {"github", "claude", "codex", "opencode"}
    paths = {
        "github": (".copilot/skills/sive/SKILL.md", ".copilot/mcp-config.json"),
        "claude": (".claude/skills/sive/SKILL.md", ".claude.json"),
        "codex": (".agents/skills/sive/SKILL.md", ".codex/config.toml"),
        "opencode": (".config/opencode/skills/sive/SKILL.md", ".config/opencode/opencode.json"),
    }
    for target, (skill_path, config_path) in paths.items():
        assert written[target] == [tmp_path / skill_path, tmp_path / config_path]
        assert (tmp_path / skill_path).read_text(encoding="utf-8").startswith("---\n")

    command = str((tmp_path / "bin" / "sive").resolve())
    cwd = str((tmp_path / "bin").resolve())
    github = json.loads((tmp_path / paths["github"][1]).read_text(encoding="utf-8"))
    assert github["mcpServers"]["sive"] == {
        "type": "local",
        "command": command,
        "args": ["serve"],
        "cwd": cwd,
        "tools": ["*"],
    }
    claude = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["sive"] == {"type": "stdio", "command": command, "args": ["serve"]}
    codex = tomllib.loads((tmp_path / paths["codex"][1]).read_text(encoding="utf-8"))
    assert codex["mcp_servers"]["sive"] == {"command": command, "args": ["serve"], "cwd": cwd}
    opencode = json.loads((tmp_path / paths["opencode"][1]).read_text(encoding="utf-8"))
    assert opencode["$schema"] == "https://opencode.ai/config.json"
    assert set(opencode["mcp"]) == {"servers"}
    assert opencode["mcp"]["servers"]["sive"] == {
        "type": "local",
        "command": [command, "serve"],
        "cwd": cwd,
    }
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
        ]
    )
    cmd_install(args)


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
