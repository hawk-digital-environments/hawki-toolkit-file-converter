import pytest

from utils.helper import sanitize_filename


def test_normal_filename() -> None:
    assert sanitize_filename("document.pdf") == "document.pdf"


def test_strips_whitespace() -> None:
    assert sanitize_filename("  hello.txt  ") == "hello.txt"


def test_strips_null_bytes() -> None:
    assert sanitize_filename("test\x00.py") == "test.py"


def test_path_traversal_reduced_to_basename() -> None:
    assert sanitize_filename("../../../etc/passwd") == "passwd"


def test_path_traversal_with_dirs() -> None:
    assert sanitize_filename("foo/bar/baz.txt") == "baz.txt"


def test_backslash_path() -> None:
    assert sanitize_filename("foo\\bar\\baz.txt") == "foo\\bar\\baz.txt"


def test_empty_after_sanitization() -> None:
    with pytest.raises(ValueError):
        sanitize_filename("")


def test_dot_only() -> None:
    with pytest.raises(ValueError):
        sanitize_filename(".")


def test_double_dot_basename() -> None:
    with pytest.raises(ValueError):
        sanitize_filename("..")
