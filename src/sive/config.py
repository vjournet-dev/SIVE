import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR_ENV_VAR = "SIVE_DATA_DIR"


def _is_source_checkout(project_root: Path) -> bool:
	return (project_root / "pyproject.toml").is_file() and (project_root / "src" / "sive").is_dir()


def _has_entries(path: Path) -> bool:
	return path.is_dir() and any(path.iterdir())


def user_data_dir(*, env: Mapping[str, str], platform: str, home: Path) -> Path:
	"""Return the per-user data directory, which survives reinstalls and upgrades of the package."""
	if platform == "win32":
		local_app_data = env.get("LOCALAPPDATA", "").strip()
		return (Path(local_app_data) if local_app_data else home / "AppData" / "Local") / "sive"
	if platform == "darwin":
		return home / "Library" / "Application Support" / "sive"
	xdg_data_home = env.get("XDG_DATA_HOME", "").strip()
	if xdg_data_home and Path(xdg_data_home).is_absolute():
		return Path(xdg_data_home) / "sive"
	return home / ".local" / "share" / "sive"


def resolve_data_dir(
	*,
	project_root: Path = PROJECT_ROOT,
	env: Mapping[str, str] | None = None,
	platform: str | None = None,
	home: Path | None = None,
) -> Path:
	"""Pick where the index, raw documents and job state live.

	Order: the ``SIVE_DATA_DIR`` override, ``<repo>/data`` for a source checkout, then a per-user directory.
	Earlier releases always wrote to ``<project_root>/data``, which is inside the virtualenv for a regular
	install and is wiped on upgrade; a non-empty one keeps being used until the per-user directory exists.
	"""
	environment = os.environ if env is None else env
	override = environment.get(DATA_DIR_ENV_VAR, "").strip()
	if override:
		return Path(override).expanduser().resolve()
	legacy_dir = project_root / "data"
	if _is_source_checkout(project_root):
		return legacy_dir
	user_dir = user_data_dir(
		env=environment,
		platform=sys.platform if platform is None else platform,
		home=Path.home() if home is None else home,
	)
	if not user_dir.exists() and _has_entries(legacy_dir):
		return legacy_dir
	return user_dir


DATA_DIR = resolve_data_dir()
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
INGEST_JOBS_STATE_PATH = RAW_DIR / "ingest_jobs.json"
TOPIC_ROUTES_STATE_PATH = RAW_DIR / "topic_routes.json"
SITE_SYNC_STATE_PATH = RAW_DIR / "site_sync_state.json"

DEFAULT_START_URL = "https://docs.haystack.deepset.ai/docs/intro"
DEFAULT_ALLOWED_HOST = "docs.haystack.deepset.ai"
DEFAULT_ALLOWED_PATH_PREFIX = "/docs/"
DEFAULT_COLLECTION_NAME = "haystack_docs"
DEFAULT_SITE_ID = "haystack"
DEFAULT_SITE_NAME = "Haystack"


def site_raw_docs_path(site_id: str) -> Path:
	return RAW_DIR / f"{site_id}.jsonl"


def site_index_state_path(site_id: str) -> Path:
	return RAW_DIR / f"{site_id}.state.json"
