import json

from sive.domain.client_install import service as skill_install


def test_render_skill_files_all_contains_expected_keys():
    files = skill_install.render_skill_files("all")

    assert "sive.skill.md" in files
    assert "claude-system-prompt.txt" in files
    assert "copilot-instructions.md" in files
    assert "gpt-system-prompt.txt" in files
    assert "gemini-system-prompt.txt" in files
    assert "mistral-system-prompt.txt" in files
    assert "cowork-skill.md" in files
    assert "cowork-manifest.json" in files
    assert "cowork-readme.md" in files


def test_install_skill_files_writes_to_output_dir(tmp_path):
    written = skill_install.install_skill_files("all", tmp_path)

    written_names = {path.name for path in written}
    assert written_names == {
        "sive.skill.md",
        "claude-system-prompt.txt",
        "copilot-instructions.md",
        "gpt-system-prompt.txt",
        "gemini-system-prompt.txt",
        "mistral-system-prompt.txt",
        "cowork-skill.md",
        "cowork-manifest.json",
        "cowork-readme.md",
    }
    for path in written:
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip()


def test_install_skill_files_default_locations_all(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_install.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(skill_install.shutil, "which", lambda name: "C:/Users/test/.local/bin/sive.exe")
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    monkeypatch.delenv("OneDriveConsumer", raising=False)

    written_by_target = skill_install.install_skill_files_default_locations("all")

    assert set(written_by_target.keys()) == {
        "claude",
        "copilot",
        "gpt",
        "gemini",
        "mistral",
        "microsoft-cowork",
    }

    expected_paths = {
        "claude": {
            tmp_path / ".claude" / "skills" / "sive" / "SKILL.md",
            tmp_path / ".claude" / "skills" / "sive" / "SYSTEM_PROMPT.txt",
            tmp_path / ".claude" / "skills" / "sive" / "MCP_SERVER.json",
        },
        "copilot": {
            tmp_path / ".copilot" / "instructions" / "sive.instructions.md",
            tmp_path / ".copilot" / "instructions" / "sive.mcp.json",
        },
        "gpt": {
            tmp_path / ".sive" / "gpt" / "SYSTEM_PROMPT.txt",
            tmp_path / ".sive" / "gpt" / "MCP_SERVER.json",
        },
        "gemini": {
            tmp_path / ".sive" / "gemini" / "SYSTEM_PROMPT.txt",
            tmp_path / ".sive" / "gemini" / "MCP_SERVER.json",
        },
        "mistral": {
            tmp_path / ".sive" / "mistral" / "SYSTEM_PROMPT.txt",
            tmp_path / ".sive" / "mistral" / "MCP_SERVER.json",
        },
        "microsoft-cowork": {
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "SKILL.md",
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "references" / "README-COWORK.md",
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "references" / "manifest.json",
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "references" / "MCP_SERVER.json",
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "references" / "color.png",
            tmp_path / "OneDrive" / "Documents" / "Cowork" / "skills" / "sive" / "references" / "outline.png",
        },
    }

    for target, paths in expected_paths.items():
        assert set(written_by_target[target]) == paths
        for path in paths:
            assert path.exists()
            if path.suffix.lower() == ".png":
                assert len(path.read_bytes()) > 0
            else:
                assert path.read_text(encoding="utf-8").strip()

    mcp_config = json.loads((tmp_path / ".copilot" / "instructions" / "sive.mcp.json").read_text(encoding="utf-8"))
    server_config = mcp_config["mcpServers"]["sive"]
    assert server_config["command"].endswith("sive.exe")
    assert server_config["args"] == ["serve"]
    assert server_config["cwd"].endswith(".local\\bin")


def test_install_skill_files_default_locations_single_target(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_install.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(skill_install.shutil, "which", lambda name: "C:/Users/test/.local/bin/sive.exe")

    written_by_target = skill_install.install_skill_files_default_locations("copilot")

    assert set(written_by_target.keys()) == {"copilot"}
    installed_paths = written_by_target["copilot"]
    assert tmp_path / ".copilot" / "instructions" / "sive.instructions.md" in installed_paths
    assert tmp_path / ".copilot" / "instructions" / "sive.mcp.json" in installed_paths


def test_install_skill_files_default_locations_cowork_uses_detected_onedrive_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_install.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(skill_install.shutil, "which", lambda name: "C:/Users/test/.local/bin/sive.exe")
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("OneDriveConsumer", raising=False)

    onedrive_dir = tmp_path / "OneDrive - talan.com"
    onedrive_dir.mkdir(parents=True)
    monkeypatch.setenv("OneDriveCommercial", str(onedrive_dir))

    written_by_target = skill_install.install_skill_files_default_locations("microsoft-cowork")

    assert set(written_by_target.keys()) == {"microsoft-cowork"}
    expected_paths = {
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "SKILL.md",
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "references" / "README-COWORK.md",
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "references" / "manifest.json",
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "references" / "MCP_SERVER.json",
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "references" / "color.png",
        onedrive_dir / "Documents" / "Cowork" / "skills" / "sive" / "references" / "outline.png",
    }

    assert set(written_by_target["microsoft-cowork"]) == expected_paths
    for path in expected_paths:
        assert path.exists()


def test_install_client_mcp_configs_custom_output(tmp_path):
    written = skill_install.install_client_mcp_configs(
        "all",
        tmp_path,
        python_executable="C:/Tools/Python/python.exe",
        cwd="C:/Workspace/project",
    )

    assert {path.name for path in written} == {
        "claude.mcp.json",
        "copilot.mcp.json",
        "gpt.mcp.json",
        "gemini.mcp.json",
        "mistral.mcp.json",
        "microsoft-cowork.mcp.json",
    }
    content = json.loads((tmp_path / "copilot.mcp.json").read_text(encoding="utf-8"))
    server_config = content["mcpServers"]["sive"]
    assert server_config["command"] == "C:/Tools/Python/python.exe"
    assert server_config["cwd"] == "C:/Workspace/project"
    assert server_config["args"] == ["-m", "sive", "serve"]


def test_install_client_mcp_configs_custom_output_uses_sive_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_install.shutil, "which", lambda name: "C:/Users/test/.local/bin/sive.exe")

    written = skill_install.install_client_mcp_configs("copilot", tmp_path)

    assert [path.name for path in written] == ["copilot.mcp.json"]
    content = json.loads((tmp_path / "copilot.mcp.json").read_text(encoding="utf-8"))
    server_config = content["mcpServers"]["sive"]
    assert server_config["command"].endswith("sive.exe")
    assert server_config["cwd"].endswith(".local\\bin")
    assert server_config["args"] == ["serve"]


def test_install_client_mcp_configs_detects_windows_executable(monkeypatch, tmp_path):
    def _which(name: str) -> str | None:
        if name == "sive.exe":
            return "C:/Users/test/.local/bin/sive.exe"
        return None

    monkeypatch.setattr(skill_install.shutil, "which", _which)

    written = skill_install.install_client_mcp_configs("copilot", tmp_path)

    assert [path.name for path in written] == ["copilot.mcp.json"]
    content = json.loads((tmp_path / "copilot.mcp.json").read_text(encoding="utf-8"))
    server_config = content["mcpServers"]["sive"]
    assert server_config["command"].endswith("sive.exe")
    assert server_config["cwd"].endswith(".local\\bin")
    assert server_config["args"] == ["serve"]


def test_install_client_mcp_configs_falls_back_to_python_module(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_install.shutil, "which", lambda name: None)
    monkeypatch.setattr(skill_install.sys, "executable", "C:/Tools/Python/python.exe")

    skill_install.install_client_mcp_configs("copilot", tmp_path)

    content = json.loads((tmp_path / "copilot.mcp.json").read_text(encoding="utf-8"))
    assert content["mcpServers"]["sive"] == {
        "command": "C:/Tools/Python/python.exe",
        "cwd": "C:\\Tools\\Python",
        "args": ["-m", "sive", "serve"],
    }


def test_render_skill_files_copilot_instructions_include_listing_and_deletion_tools():
    files = skill_install.render_skill_files("copilot")

    instructions = files["copilot-instructions.md"]
    assert "/sive help" in instructions
    assert "/sive add <url | nom>" in instructions
    assert "/sive update <site_id|path>" in instructions
    assert "/sive list" in instructions
    assert "/sive remove <doc_id>" in instructions
    assert "Describe in chat the slash commands" in instructions
    assert ".md" in instructions
    assert ".docx" in instructions
    assert ".pdf" in instructions
    assert "folder containing these files" in instructions
    assert "search_documentation" in instructions
    assert "site_ids" in instructions
    assert "Do not choose one site silently" in instructions
    assert "update_documentation_source" in instructions
    assert "wait_for_ingest_completion" in instructions
    assert "list_documentation_sites_in_database(include_active=True)" in instructions
    assert "delete_documentation_site(site_id=<doc_id>, delete_raw_files=True)" in instructions
    assert "summarize the registered documentation sources" in instructions
    assert "needs_confirmation" in instructions
    assert "Ask the user in chat which URL they want" in instructions
    assert "additional_urls" in instructions
    assert "allowed_url_prefixes" in instructions
    assert "Do not broaden" in instructions
    assert "ask which branch to ingest" in instructions
    assert "final path segment as the default scope" in instructions
    assert "ask the user to provide all branch URLs" in instructions
