from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
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
