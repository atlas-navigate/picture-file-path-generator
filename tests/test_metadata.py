from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from organizer.image_metadata import get_image_datetime
from organizer.metadata import get_capture_datetime
from organizer.models import FileCategory
from organizer.video_metadata import get_video_datetime


def test_get_image_datetime_reads_exif_date_time_original(
    tmp_path: Path, piexif_module
) -> None:
    """A JPEG with DateTimeOriginal set via piexif in the Exif sub-IFD
    must yield exactly that datetime."""
    from PIL import Image

    expected = datetime(2012, 6, 15, 14, 30, 0)
    img_path = tmp_path / "with_exif.jpg"

    img = Image.new("RGB", (8, 8), color="red")
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_dict["Exif"][piexif_module.ExifIFD.DateTimeOriginal] = (
        expected.strftime("%Y:%m:%d %H:%M:%S").encode("ascii")
    )
    exif_bytes = piexif_module.dump(exif_dict)
    img.save(img_path, exif=exif_bytes)

    result = get_image_datetime(img_path)
    assert result == expected


def test_get_image_datetime_via_pillow_native_exif_ifd(
    tmp_path: Path, make_jpeg_with_exif_datetime
) -> None:
    """Same scenario, written via Pillow's own Exif/get_ifd API (doesn't
    require piexif) -- exercises the exact sub-IFD lookup path."""
    expected = datetime(2019, 11, 3, 8, 5, 12)
    img_path = tmp_path / "pillow_exif.jpg"
    make_jpeg_with_exif_datetime(img_path, expected)

    result = get_image_datetime(img_path)
    assert result == expected


def test_capture_datetime_falls_back_to_mtime_when_no_exif(
    tmp_path: Path, make_plain_jpeg, set_mtime
) -> None:
    img_path = tmp_path / "no_exif.jpg"
    make_plain_jpeg(img_path)

    forced_mtime = datetime(2015, 3, 22, 9, 0, 0)
    set_mtime(img_path, forced_mtime)

    # get_image_datetime should find nothing.
    assert get_image_datetime(img_path) is None

    # get_capture_datetime should fall back to the exact forced mtime.
    dt, source = get_capture_datetime(img_path, FileCategory.PICTURE)
    assert source == "filesystem_mtime"
    assert dt == forced_mtime


def test_get_image_datetime_handles_corrupt_file_without_raising(
    tmp_path: Path,
) -> None:
    corrupt_path = tmp_path / "corrupt.jpg"
    corrupt_path.write_bytes(b"this is not a real jpeg, just garbage bytes")

    # Must not raise.
    result = get_image_datetime(corrupt_path)
    assert result is None


def test_capture_datetime_still_works_on_corrupt_file(
    tmp_path: Path, set_mtime
) -> None:
    corrupt_path = tmp_path / "corrupt2.jpg"
    corrupt_path.write_bytes(b"garbage garbage garbage")
    forced_mtime = datetime(2018, 1, 1, 0, 0, 0)
    set_mtime(corrupt_path, forced_mtime)

    dt, source = get_capture_datetime(corrupt_path, FileCategory.PICTURE)
    assert source == "filesystem_mtime"
    assert dt == forced_mtime


def test_get_video_datetime_handles_garbage_file_without_raising(
    tmp_path: Path,
) -> None:
    fake_mp4 = tmp_path / "fake.mp4"
    fake_mp4.write_bytes(b"not actually a valid mp4 container, just bytes")

    # Must not raise, regardless of whether hachoir is installed.
    result = get_video_datetime(fake_mp4)
    assert result is None


def test_capture_datetime_for_misc_uses_mtime_directly(
    tmp_path: Path, set_mtime
) -> None:
    misc_path = tmp_path / "notes.txt"
    misc_path.write_text("hello")
    forced_mtime = datetime(2021, 7, 4, 12, 0, 0)
    set_mtime(misc_path, forced_mtime)

    dt, source = get_capture_datetime(misc_path, FileCategory.MISC)
    assert source == "filesystem_mtime"
    assert dt == forced_mtime


def test_get_image_datetime_missing_file_does_not_raise(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.jpg"
    assert get_image_datetime(missing) is None


def test_get_video_datetime_missing_file_does_not_raise(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.mp4"
    assert get_video_datetime(missing) is None
