from pathlib import Path

from sive.config import resolve_data_dir


def _make_source_checkout(root: Path) -> None:
    (root / "src" / "sive").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'sive'\n", encoding="utf-8")


def _make_legacy_data(root: Path) -> Path:
    legacy = root / "data"
    (legacy / "raw").mkdir(parents=True)
    (legacy / "raw" / "site.jsonl").write_text("{}\n", encoding="utf-8")
    return legacy


def test_env_override_wins_over_everything(tmp_path):
    _make_source_checkout(tmp_path / "repo")
    custom = tmp_path / "custom"

    resolved = resolve_data_dir(
        project_root=tmp_path / "repo",
        env={"SIVE_DATA_DIR": str(custom)},
        platform="linux",
        home=tmp_path / "home",
    )

    assert resolved == custom.resolve()


def test_blank_env_override_is_ignored(tmp_path):
    _make_source_checkout(tmp_path)

    resolved = resolve_data_dir(
        project_root=tmp_path, env={"SIVE_DATA_DIR": "  "}, platform="linux", home=tmp_path / "home"
    )

    assert resolved == tmp_path / "data"


def test_source_checkout_keeps_data_next_to_the_repository(tmp_path):
    _make_source_checkout(tmp_path)

    resolved = resolve_data_dir(project_root=tmp_path, env={}, platform="win32", home=tmp_path / "home")

    assert resolved == tmp_path / "data"


def test_installed_package_uses_a_stable_per_user_directory(tmp_path):
    root = tmp_path / "venv" / "lib"
    root.mkdir(parents=True)
    home = tmp_path / "home"
    local_app_data = tmp_path / "local"
    xdg_data_home = tmp_path / "xdg"
    cases = [
        ("win32", {"LOCALAPPDATA": str(local_app_data)}, local_app_data / "sive"),
        ("win32", {}, home / "AppData" / "Local" / "sive"),
        ("darwin", {}, home / "Library" / "Application Support" / "sive"),
        ("linux", {"XDG_DATA_HOME": str(xdg_data_home)}, xdg_data_home / "sive"),
        ("linux", {"XDG_DATA_HOME": "relative/dir"}, home / ".local" / "share" / "sive"),
        ("linux", {}, home / ".local" / "share" / "sive"),
    ]

    for platform, env, expected in cases:
        resolved = resolve_data_dir(project_root=root, env=env, platform=platform, home=home)
        assert resolved == expected, (platform, env)


def test_non_empty_legacy_directory_is_kept_until_the_user_directory_exists(tmp_path):
    root = tmp_path / "venv" / "lib"
    legacy = _make_legacy_data(root)
    home = tmp_path / "home"
    user_dir = home / ".local" / "share" / "sive"

    assert resolve_data_dir(project_root=root, env={}, platform="linux", home=home) == legacy

    user_dir.mkdir(parents=True)

    assert resolve_data_dir(project_root=root, env={}, platform="linux", home=home) == user_dir


def test_empty_legacy_directory_does_not_block_the_user_directory(tmp_path):
    root = tmp_path / "venv" / "lib"
    (root / "data").mkdir(parents=True)
    home = tmp_path / "home"

    resolved = resolve_data_dir(project_root=root, env={}, platform="linux", home=home)

    assert resolved == home / ".local" / "share" / "sive"
