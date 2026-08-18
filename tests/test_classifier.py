from __future__ import annotations

from pathlib import Path

import pytest

from organizer.classifier import classify_file
from organizer.models import FileCategory


@pytest.mark.parametrize(
    "filename,expected",
    [
        # Common image extensions
        ("photo.jpg", FileCategory.PICTURE),
        ("photo.jpeg", FileCategory.PICTURE),
        ("photo.png", FileCategory.PICTURE),
        ("photo.gif", FileCategory.PICTURE),
        ("photo.bmp", FileCategory.PICTURE),
        ("photo.tiff", FileCategory.PICTURE),
        ("photo.tif", FileCategory.PICTURE),
        ("photo.webp", FileCategory.PICTURE),
        ("photo.heic", FileCategory.PICTURE),
        ("photo.heif", FileCategory.PICTURE),
        # RAW extensions
        ("photo.cr2", FileCategory.PICTURE),
        ("photo.cr3", FileCategory.PICTURE),
        ("photo.nef", FileCategory.PICTURE),
        ("photo.arw", FileCategory.PICTURE),
        ("photo.dng", FileCategory.PICTURE),
        ("photo.orf", FileCategory.PICTURE),
        ("photo.rw2", FileCategory.PICTURE),
        # Case-insensitivity
        ("PHOTO.JPG", FileCategory.PICTURE),
        ("Photo.Jpg", FileCategory.PICTURE),
        ("photo.CR2", FileCategory.PICTURE),
        # Video extensions
        ("movie.mp4", FileCategory.VIDEO),
        ("movie.mov", FileCategory.VIDEO),
        ("movie.avi", FileCategory.VIDEO),
        ("movie.mkv", FileCategory.VIDEO),
        ("movie.wmv", FileCategory.VIDEO),
        ("movie.m4v", FileCategory.VIDEO),
        ("movie.3gp", FileCategory.VIDEO),
        ("movie.mts", FileCategory.VIDEO),
        ("movie.m2ts", FileCategory.VIDEO),
        ("movie.vod", FileCategory.VIDEO),
        ("MOVIE.MP4", FileCategory.VIDEO),
        ("MOVIE.VOD", FileCategory.VIDEO),
        # Misc: unrelated extensions
        ("document.txt", FileCategory.MISC),
        ("document.pdf", FileCategory.MISC),
        ("archive.zip", FileCategory.MISC),
        ("spreadsheet.xlsx", FileCategory.MISC),
        # Misc: no extension at all
        ("README", FileCategory.MISC),
        ("Makefile", FileCategory.MISC),
        # Misc: dotfiles (Path.suffix is '' for these, not '.bashrc')
        (".bashrc", FileCategory.MISC),
        (".gitignore", FileCategory.MISC),
        (".hidden", FileCategory.MISC),
    ],
)
def test_classify_file(filename: str, expected: FileCategory) -> None:
    assert classify_file(Path(filename)) == expected


def test_dotfile_suffix_is_empty() -> None:
    # Sanity-check the exact Path behavior this classifier depends on.
    assert Path(".bashrc").suffix == ""


def test_classify_file_with_full_path() -> None:
    # classify_file should work the same regardless of how much of a
    # path precedes the filename.
    assert classify_file(Path("/a/b/c/photo.JPG")) == FileCategory.PICTURE
    assert classify_file(Path("/a/b/c/.bashrc")) == FileCategory.MISC
