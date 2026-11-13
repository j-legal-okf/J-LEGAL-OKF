"""Publish a prepared directory with Linux's atomic no-replace rename."""

import ctypes
import errno
import os
from pathlib import Path
import stat
import sys

from .errors import JLegalError


_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


def _refuse(code: str) -> None:
    raise JLegalError(code) from None


def _absolute_path(value: str | Path) -> tuple[Path, bytes]:
    """Resolve an existing parent while leaving the final name untouched."""
    if not isinstance(value, (str, Path)):
        _refuse("PUBLICATION_PATH_INVALID")
    raw = str(value)
    # Path objects have already normalized their spelling; preserve every final
    # component still visible in the input, including a trailing slash on str.
    raw = raw.rstrip("/")
    if not raw or "\x00" in raw or raw.rsplit("/", 1)[-1] in {"", ".", ".."}:
        _refuse("PUBLICATION_PATH_INVALID")
    try:
        path = Path(raw)
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir():
            _refuse("PUBLICATION_PATH_INVALID")
        absolute = parent / path.name
        encoded = os.fsencode(absolute)
    except (OSError, ValueError, RuntimeError, UnicodeError):
        _refuse("PUBLICATION_PATH_INVALID")
    return absolute, encoded


def _load_renameat2():
    if sys.platform != "linux":
        _refuse("PUBLICATION_UNSUPPORTED")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
    except (OSError, AttributeError, TypeError, ValueError):
        _refuse("PUBLICATION_UNSUPPORTED")
    return renameat2


def publish_directory_noreplace(source: str | Path, destination: str | Path) -> Path:
    """Move a directory to a vacant final name without replacing any entry.

    The caller owns preparation, content validation, and cleanup. This function
    makes no change until the single renameat2 call and never retries it.
    """
    source_path, source_bytes = _absolute_path(source)
    destination_path, destination_bytes = _absolute_path(destination)
    try:
        source_mode = source_path.lstat().st_mode
    except (OSError, ValueError):
        _refuse("PUBLICATION_SOURCE_INVALID")
    if not stat.S_ISDIR(source_mode):
        _refuse("PUBLICATION_SOURCE_INVALID")
    if os.path.lexists(destination_path):
        _refuse("PUBLICATION_DESTINATION_EXISTS")

    renameat2 = _load_renameat2()
    ctypes.set_errno(0)
    result = renameat2(
        _AT_FDCWD, source_bytes, _AT_FDCWD, destination_bytes,
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            _refuse("PUBLICATION_DESTINATION_EXISTS")
        if error in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            _refuse("PUBLICATION_UNSUPPORTED")
        _refuse("PUBLICATION_FAILED")
    return destination_path
