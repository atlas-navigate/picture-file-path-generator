"""Small human-readable formatting helpers shared by the GUI dialogs.

Kept dependency-free (no Qt imports) so these are trivially unit
testable on their own, though they're only ever called from
preview_dialog.py / report_dialog.py today.
"""
from __future__ import annotations


def format_bytes(num_bytes: int) -> str:
    """Render a byte count as a human-readable string, e.g. 1536 -> '1.5 KB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    """Render an elapsed-seconds count as e.g. '2m 14s' or '1h 3m 12s'."""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
