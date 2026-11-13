from __future__ import annotations


def format_progress_bar(percent: int, width: int = 20) -> str:
    safe_percent = max(0, min(100, int(percent)))
    filled = int((safe_percent / 100) * width)
    return f"[{'#' * filled}{'-' * (width - filled)}] {safe_percent}%"
