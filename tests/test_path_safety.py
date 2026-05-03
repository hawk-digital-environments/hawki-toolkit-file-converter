from __future__ import annotations

from pathlib import Path

import pytest

from workers.failure_classifier import MissingLocalFileError, UnsafePathError
from workers.file_conversion_worker import validate_local_path


def test_validate_local_path_accepts_file_within_root(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    root.mkdir()
    file_path = root / "docs" / "a.pdf"
    file_path.parent.mkdir()
    file_path.write_bytes(b"ok")

    resolved = validate_local_path(str(file_path), root)
    assert resolved == file_path.resolve()


def test_validate_local_path_rejects_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    root.mkdir()

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"x")

    with pytest.raises(UnsafePathError):
        validate_local_path(str(outside), root)


def test_validate_local_path_rejects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    root.mkdir()

    with pytest.raises(MissingLocalFileError):
        validate_local_path(str(root / "missing.pdf"), root)
