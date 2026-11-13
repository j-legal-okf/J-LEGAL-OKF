"""Linux no-replace publication contract, using synthetic directories only."""

import ctypes
import errno
import os
import sys

import pytest

from jlegal_okf.errors import JLegalError
from jlegal_okf import publication


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux renameat2 contract")


def _source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_bytes(b"synthetic payload")
    return source


def _error(code, operation):
    with pytest.raises(JLegalError) as caught:
        operation()
    assert str(caught.value) == code
    assert caught.value.__cause__ is None


def _install_errno(monkeypatch, number):
    calls = []

    def rename(*args):
        calls.append(args)
        ctypes.set_errno(number)
        return -1

    monkeypatch.setattr(publication, "_load_renameat2", lambda: rename)
    return calls


def test_real_rename_preserves_directory_inode_and_content(tmp_path):
    source = _source(tmp_path)
    before = source.stat().st_ino
    destination = tmp_path / "destination"
    result = publication.publish_directory_noreplace(str(source) + "/", str(destination) + "/")
    assert result == destination
    assert result.is_absolute()
    assert result.stat().st_ino == before
    assert (result / "payload").read_bytes() == b"synthetic payload"
    assert not source.exists()


@pytest.mark.parametrize("kind", ["empty_directory", "nonempty_directory", "file", "symlink", "dangling_symlink"])
def test_existing_destination_is_preserved(tmp_path, kind):
    source = _source(tmp_path)
    source_inode = source.stat().st_ino
    destination = tmp_path / "destination"
    target = tmp_path / "target"
    target.write_bytes(b"target")
    if kind in {"empty_directory", "nonempty_directory"}:
        destination.mkdir()
        if kind == "nonempty_directory":
            (destination / "keep").write_bytes(b"keep")
    elif kind == "file":
        destination.write_bytes(b"keep")
    else:
        destination.symlink_to(target if kind == "symlink" else tmp_path / "absent")
    before = destination.lstat().st_ino

    _error("PUBLICATION_DESTINATION_EXISTS", lambda: publication.publish_directory_noreplace(source, destination))

    assert source.stat().st_ino == source_inode
    assert (source / "payload").read_bytes() == b"synthetic payload"
    assert destination.lstat().st_ino == before
    if kind == "nonempty_directory":
        assert (destination / "keep").read_bytes() == b"keep"
    elif kind == "file":
        assert destination.read_bytes() == b"keep"
    elif kind in {"symlink", "dangling_symlink"}:
        assert destination.is_symlink()
        assert target.read_bytes() == b"target"


def test_race_after_early_lexists_is_rejected_by_real_syscall(tmp_path, monkeypatch):
    source = _source(tmp_path)
    source_inode = source.stat().st_ino
    destination = tmp_path / "destination"
    real = publication._load_renameat2()
    calls = []

    def competing_rename(*args):
        calls.append(args)
        destination.write_bytes(b"competitor")
        return real(*args)

    monkeypatch.setattr(publication, "_load_renameat2", lambda: competing_rename)
    _error("PUBLICATION_DESTINATION_EXISTS", lambda: publication.publish_directory_noreplace(source, destination))
    assert len(calls) == 1
    assert calls[0] == (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    assert source.stat().st_ino == source_inode
    assert (source / "payload").read_bytes() == b"synthetic payload"
    assert destination.read_bytes() == b"competitor"


@pytest.mark.parametrize("kind", ["missing", "file", "directory_symlink", "dangling_symlink"])
def test_source_must_be_non_symlink_directory(tmp_path, kind):
    source = tmp_path / "source"
    target = tmp_path / "target"
    target.mkdir()
    if kind == "file":
        source.write_bytes(b"source")
    elif kind == "directory_symlink":
        source.symlink_to(target, target_is_directory=True)
    elif kind == "dangling_symlink":
        source.symlink_to(tmp_path / "absent", target_is_directory=True)
    destination = tmp_path / "destination"
    _error("PUBLICATION_SOURCE_INVALID", lambda: publication.publish_directory_noreplace(source, destination))
    assert not destination.exists()
    assert target.is_dir()
    if kind == "file":
        assert source.read_bytes() == b"source"
    elif "symlink" in kind:
        assert source.is_symlink()


@pytest.mark.parametrize("name", ["", ".", "..", "/", "item/.", "item/..", "item\x00bad", 42])
def test_bad_final_path_is_refused(tmp_path, name):
    source = _source(tmp_path)
    _error("PUBLICATION_PATH_INVALID", lambda: publication.publish_directory_noreplace(source, name))
    assert source.is_dir()


@pytest.mark.parametrize("kind", ["missing", "file", "loop"])
def test_invalid_parent_is_refused(tmp_path, kind):
    source = _source(tmp_path)
    parent = tmp_path / "parent"
    if kind == "file":
        parent.write_bytes(b"file")
    elif kind == "loop":
        parent.symlink_to(parent)
    _error("PUBLICATION_PATH_INVALID", lambda: publication.publish_directory_noreplace(source, parent / "destination"))
    assert source.is_dir()


def test_parent_symlink_resolves_but_final_symlink_does_not(tmp_path):
    source = _source(tmp_path)
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    destination = alias / "destination"
    returned = publication.publish_directory_noreplace(source, destination)
    assert returned == real_parent / "destination"
    assert (returned / "payload").read_bytes() == b"synthetic payload"


def test_invalid_source_path_precedes_destination_type(tmp_path):
    destination = tmp_path / "destination"
    destination.write_bytes(b"keep")
    _error("PUBLICATION_PATH_INVALID", lambda: publication.publish_directory_noreplace(tmp_path / "absent" / "source", destination))
    assert destination.read_bytes() == b"keep"


def test_source_type_precedes_existing_destination(tmp_path):
    destination = tmp_path / "destination"
    destination.write_bytes(b"keep")
    _error("PUBLICATION_SOURCE_INVALID", lambda: publication.publish_directory_noreplace(tmp_path / "absent", destination))
    assert destination.read_bytes() == b"keep"


def test_existing_destination_precedes_platform_check(tmp_path, monkeypatch):
    source = _source(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    monkeypatch.setattr(publication.sys, "platform", "darwin")
    _error("PUBLICATION_DESTINATION_EXISTS", lambda: publication.publish_directory_noreplace(source, destination))
    assert source.is_dir()


def test_non_linux_platform_refused_without_fallback(tmp_path, monkeypatch):
    source = _source(tmp_path)
    destination = tmp_path / "destination"
    monkeypatch.setattr(publication.sys, "platform", "darwin")
    _error("PUBLICATION_UNSUPPORTED", lambda: publication.publish_directory_noreplace(source, destination))
    assert source.is_dir()
    assert not destination.exists()


def test_missing_libc_symbol_refused_without_fallback(tmp_path, monkeypatch):
    source = _source(tmp_path)
    destination = tmp_path / "destination"
    monkeypatch.setattr(publication.ctypes, "CDLL", lambda *args, **kwargs: object())
    _error("PUBLICATION_UNSUPPORTED", lambda: publication.publish_directory_noreplace(source, destination))
    assert source.is_dir()
    assert not destination.exists()


def test_unavailable_libc_refused_without_fallback(tmp_path, monkeypatch):
    source = _source(tmp_path)
    destination = tmp_path / "destination"

    def unavailable(*args, **kwargs):
        raise OSError("synthetic libc failure with private details")

    monkeypatch.setattr(publication.ctypes, "CDLL", unavailable)
    _error("PUBLICATION_UNSUPPORTED", lambda: publication.publish_directory_noreplace(source, destination))
    assert source.is_dir()
    assert not destination.exists()


@pytest.mark.parametrize("number,code", [
    (errno.EEXIST, "PUBLICATION_DESTINATION_EXISTS"),
    (errno.ENOTEMPTY, "PUBLICATION_DESTINATION_EXISTS"),
    (errno.ENOSYS, "PUBLICATION_UNSUPPORTED"),
    (errno.EINVAL, "PUBLICATION_UNSUPPORTED"),
    (errno.EOPNOTSUPP, "PUBLICATION_UNSUPPORTED"),
    (errno.EXDEV, "PUBLICATION_FAILED"),
    (errno.EACCES, "PUBLICATION_FAILED"),
])
def test_syscall_errno_mapping_has_no_fallback(tmp_path, monkeypatch, number, code):
    source = _source(tmp_path)
    source_inode = source.stat().st_ino
    destination = tmp_path / "destination"
    calls = _install_errno(monkeypatch, number)

    def forbidden(*args, **kwargs):
        pytest.fail("ordinary rename fallback is forbidden")

    with monkeypatch.context() as guard:
        guard.setattr(publication.os, "rename", forbidden)
        guard.setattr(publication.os, "replace", forbidden)
        _error(code, lambda: publication.publish_directory_noreplace(source, destination))
    assert len(calls) == 1
    assert calls[0] == (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    assert source.stat().st_ino == source_inode
    assert (source / "payload").read_bytes() == b"synthetic payload"
    assert not destination.exists()


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_interruption_before_syscall_keeps_source(tmp_path, monkeypatch, exception_type):
    source = _source(tmp_path)
    destination = tmp_path / "destination"
    failure = exception_type("before syscall")

    def interrupt(*args):
        raise failure

    monkeypatch.setattr(publication, "_load_renameat2", lambda: interrupt)
    with pytest.raises(exception_type) as caught:
        publication.publish_directory_noreplace(source, destination)
    assert caught.value is failure
    assert (source / "payload").read_bytes() == b"synthetic payload"
    assert not destination.exists()


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_interruption_after_syscall_keeps_complete_final(tmp_path, monkeypatch, exception_type):
    source = _source(tmp_path)
    source_inode = source.stat().st_ino
    destination = tmp_path / "destination"
    real = publication._load_renameat2()
    failure = exception_type("after syscall")

    def interrupt(*args):
        assert real(*args) == 0
        raise failure

    monkeypatch.setattr(publication, "_load_renameat2", lambda: interrupt)
    with pytest.raises(exception_type) as caught:
        publication.publish_directory_noreplace(source, destination)
    assert caught.value is failure
    assert not source.exists()
    assert destination.stat().st_ino == source_inode
    assert (destination / "payload").read_bytes() == b"synthetic payload"
