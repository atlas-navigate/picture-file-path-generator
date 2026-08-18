"""Pure file-classification logic (no I/O beyond inspecting the path itself)."""
from __future__ import annotations

from pathlib import Path

from organizer.constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from organizer.models import FileCategory


def classify_file(path: Path) -> FileCategory:
    """Classify a file purely by its extension.

    ``Path.suffix`` already does the right thing for dotfiles with no
    real extension: ``Path('.bashrc').suffix == ''`` because a leading
    dot with nothing after it (other than more of the name) is treated
    as part of the stem, not an extension. Extensionless files therefore
    naturally fall through to MISC below, as required.
    """
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return FileCategory.PICTURE
    if suffix in VIDEO_EXTENSIONS:
        return FileCategory.VIDEO
    return FileCategory.MISC
