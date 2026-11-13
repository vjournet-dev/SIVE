from __future__ import annotations

import os

HF_TOKEN_ENV_CANDIDATES = (
    "HUGGINGFACE_HUB_TOKEN",
    "HF_TOKEN",
    "HUGGINGFACE_TOKEN",
)


def apply_hf_token_from_env() -> str | None:
    """Ensure Hugging Face auth token is available via HUGGINGFACE_HUB_TOKEN.

    The embedding stack relies on Hugging Face Hub conventions. This helper accepts
    common aliases (HF_TOKEN, HUGGINGFACE_TOKEN) and maps them to
    HUGGINGFACE_HUB_TOKEN when needed.
    """
    for name in HF_TOKEN_ENV_CANDIDATES:
        value = os.getenv(name)
        if value and value.strip():
            token = value.strip()
            if not os.getenv("HUGGINGFACE_HUB_TOKEN"):
                os.environ["HUGGINGFACE_HUB_TOKEN"] = token
            return token
    return None