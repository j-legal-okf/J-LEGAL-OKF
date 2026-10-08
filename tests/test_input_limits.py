"""Small synthetic XML inputs exercise resource boundaries without stress loads."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from defusedxml.common import DefusedXmlException
import pytest

from jlegal_okf import egov, input_limits as limits
from jlegal_okf.adapters import html_adapter, xml_adapter
from jlegal_okf.errors import AdapterError, JLegalError


FIXTURE = Path(__file__).resolve().parents[1] / "examples/synthetic_egov_law.xml"
MAPPING = {"row": "unused", "fields": {key: key for key in (
    "jurisdiction", "authority", "law_number_key", "locator", "kind", "depth", "text")}}


@pytest.mark.parametrize("size", [15, 16, 17])
def test_read_and_parse_byte_boundaries(tmp_path, size):
    raw = b"<r/>" + b" " * (size - 4)
    path = tmp_path / "small.xml"
    path.write_bytes(raw)
    if size <= 16:
        assert limits.read_xml_bytes(path, max_bytes=16) == raw
        assert limits.parse_xml(raw, max_bytes=16).tag == "r"
    else:
        with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
            limits.read_xml_bytes(path, max_bytes=16)
        with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
            limits.parse_xml(raw, max_bytes=16)


@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("dimension", ["depth", "elements"])
def test_tree_boundaries_include_root(count, dimension):
    raw = (b"<r>" * count + b"</r>" * count if dimension == "depth"
           else b"<r>" + b"<c/>" * (count - 1) + b"</r>")
    keyword = {"max_" + dimension: 3}
    if count <= 3:
        assert len(list(limits.parse_xml(raw, **keyword).iter())) == count
    else:
        code = "INPUT_XML_DEPTH_LIMIT" if dimension == "depth" else "INPUT_XML_ELEMENT_LIMIT"
        with pytest.raises(AdapterError, match="^" + code + "$"):
            limits.parse_xml(raw, **keyword)


@pytest.mark.parametrize("keyword", ["max_bytes", "max_depth", "max_elements"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2"])
def test_invalid_limits_fail_with_stable_code(tmp_path, keyword, value):
    with pytest.raises(AdapterError, match="^INPUT_LIMIT_VALUE$"):
        limits.parse_xml(b"<r/>", **{keyword: value})
    if keyword == "max_bytes":
        with pytest.raises(AdapterError, match="^INPUT_LIMIT_VALUE$"):
            limits.read_xml_bytes(tmp_path / "not-opened.xml", max_bytes=value)


def test_single_root_and_runtime_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(limits, "MAX_XML_DEPTH", 1)
    monkeypatch.setattr(limits, "MAX_XML_ELEMENTS", 1)
    monkeypatch.setattr(limits, "MAX_XML_BYTES", 4)
    path = tmp_path / "root.xml"
    path.write_bytes(b"<r/>")
    assert limits.read_xml_bytes(path) == b"<r/>"
    assert limits.parse_xml(b"<r/>").tag == "r"
    with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
        limits.parse_xml(b"<r/> ")
    path.write_bytes(b"<r/> ")
    with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
        limits.read_xml_bytes(path)
    with pytest.raises(AdapterError, match="^INPUT_XML_DEPTH_LIMIT$"):
        limits.parse_xml(b"<r><c/></r>", max_bytes=20)
    with pytest.raises(AdapterError, match="^INPUT_XML_ELEMENT_LIMIT$"):
        limits.parse_xml(b"<r><c/></r>", max_bytes=20, max_depth=2)


@pytest.mark.parametrize("dimension", ["depth", "elements"])
def test_excess_element_is_rejected_before_construction(monkeypatch, dimension):
    original = ET.Element
    constructed = []

    def element(tag, attributes):
        constructed.append(tag)
        return original(tag, attributes)

    monkeypatch.setattr(limits.ET, "Element", element)
    with pytest.raises(AdapterError, match="^INPUT_XML_"):
        limits.parse_xml(b"<r><c/></r>", **{"max_" + dimension: 1})
    assert constructed == ["r"]


@pytest.mark.parametrize("declaration", [
    b"<!DOCTYPE r>",
    b'<!DOCTYPE r [<!ENTITY e "small invented text">]>',
    b'<!DOCTYPE r SYSTEM "https://example.invalid/not-requested.dtd">',
    b'<!DOCTYPE r [<!ENTITY e SYSTEM "file:///nonexistent-synthetic-input">]>',
])
def test_dtd_entities_and_external_references_are_forbidden(declaration):
    with pytest.raises(DefusedXmlException):
        limits.parse_xml(declaration + b"<r/>")


def test_parser_preserves_character_data_attributes_and_tails():
    raw = b'<r a="x&#xD;y">A&#xD;\r\n<c> B </c> tail&#xD;\n&amp;<?pi ignored?><!--comment--></r>'
    before, after = ET.fromstring(raw), limits.parse_xml(raw)
    assert ET.tostring(after) == ET.tostring(before)
    assert after.text == "A\r\n" and after[0].tail == " tail\r\n&"


@pytest.mark.parametrize("growth", [False, True])
def test_reader_uses_same_fd_and_bounded_read_despite_stale_size(tmp_path, monkeypatch, growth):
    path = tmp_path / "small.xml"
    path.write_bytes(b"<r/>" if growth else b"<r/>" + b" " * 40)
    real_open, real_fstat, real_fdopen = os.open, os.fstat, os.fdopen
    opened, inspected, requested, returned = [], [], [], []

    def open_fd(name, flags):
        fd = real_open(name, flags)
        opened.append(fd)
        return fd

    def fstat(fd):
        inspected.append(fd)
        actual = real_fstat(fd)
        if growth:
            with path.open("ab") as out:
                out.write(b" " * 40)
        return SimpleNamespace(st_mode=actual.st_mode, st_size=4)

    class Reader:
        def __init__(self, *args, **kwargs):
            assert kwargs["buffering"] == 0
            self.file = real_fdopen(*args, **kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        def read(self, size):
            requested.append(size)
            raw = self.file.read(size)
            returned.append(len(raw))
            return raw

    def no_path_read(*args, **kwargs):
        pytest.fail("reader must inspect and read the opened descriptor")

    with monkeypatch.context() as patch:
        patch.setattr(limits.os, "open", open_fd)
        patch.setattr(limits.os, "fstat", fstat)
        patch.setattr(limits.os, "fdopen", Reader)
        patch.setattr(Path, "stat", no_path_read)
        patch.setattr(Path, "read_bytes", no_path_read)
        with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
            limits.read_xml_bytes(path, max_bytes=16)
    assert opened == inspected and len(opened) == 1
    assert requested == [17] and returned == [17]
    with pytest.raises(OSError):
        real_fstat(opened[0])


def test_short_reads_use_only_remaining_budget_and_preserve_all_bytes(tmp_path, monkeypatch):
    path = tmp_path / "short.xml"
    raw = b"<r/>"
    path.write_bytes(raw)
    real_fdopen = os.fdopen
    requested = []

    class ShortReader:
        def __init__(self, *args, **kwargs):
            assert kwargs["buffering"] == 0
            self.file = real_fdopen(*args, **kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        def read(self, size):
            requested.append(size)
            return self.file.read(min(size, 2))

    monkeypatch.setattr(limits.os, "fdopen", ShortReader)
    assert limits.read_xml_bytes(path, max_bytes=4) == raw
    assert requested == [5, 3, 1]


@pytest.mark.parametrize("failure", ["fstat", "fdopen", "read", "oversize", "empty"])
def test_reader_closes_descriptor_on_failures(tmp_path, monkeypatch, failure):
    path = tmp_path / "input.xml"
    path.write_bytes(b"" if failure == "empty" else b"<r/>")
    real_open, real_fstat, real_fdopen = os.open, os.fstat, os.fdopen
    opened = []

    def open_fd(name, flags):
        fd = real_open(name, flags)
        opened.append(fd)
        return fd

    def fail(*args, **kwargs):
        raise OSError("synthetic failure")

    class FailingReader:
        def __init__(self, *args, **kwargs):
            self.file = real_fdopen(*args, **kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        read = fail

    monkeypatch.setattr(limits.os, "open", open_fd)
    if failure in {"fstat", "fdopen"}:
        monkeypatch.setattr(limits.os, failure, fail)
    elif failure == "read":
        monkeypatch.setattr(limits.os, "fdopen", FailingReader)
    expected = {"oversize": "TOO_LARGE", "empty": "EMPTY"}.get(failure, "UNAVAILABLE")
    for _ in range(3):
        with pytest.raises(AdapterError, match="^INPUT_" + expected + "$"):
            limits.read_xml_bytes(path, max_bytes=3 if failure == "oversize" else 16,
                                  allow_empty=False)
        with pytest.raises(OSError):
            real_fstat(opened[-1])


def test_missing_directory_symlink_and_empty_diagnostics(tmp_path):
    with pytest.raises(AdapterError, match="^INPUT_UNAVAILABLE$"):
        limits.read_xml_bytes(tmp_path / "missing")
    with pytest.raises(AdapterError, match="^INPUT_NOT_REGULAR$"):
        limits.read_xml_bytes(tmp_path)
    path = tmp_path / "empty.xml"
    path.write_bytes(b"")
    assert limits.read_xml_bytes(path) == b""
    with pytest.raises(AdapterError, match="^EGOV_XML_INPUT_EMPTY$"):
        egov._read_admissible_xml(path)
    with pytest.raises(AdapterError, match="^EGOV_XML_INPUT_UNAVAILABLE$"):
        egov._read_admissible_xml(tmp_path / "missing")
    with pytest.raises(AdapterError, match="^EGOV_XML_INPUT_NOT_REGULAR$"):
        egov._read_admissible_xml(tmp_path)
    path.write_bytes(b"<r/>")
    link = tmp_path / "link.xml"
    link.symlink_to(path)
    assert limits.read_xml_bytes(link) == b"<r/>"
    assert egov._read_admissible_xml(link) == b"<r/>"


@pytest.mark.skipif(os.name != "posix", reason="POSIX nonblocking descriptor contract")
def test_fifo_is_rejected_without_waiting_for_writer(tmp_path):
    fifo = tmp_path / "input.xml"
    os.mkfifo(fifo)
    script = (
        "import os,sys\nfrom pathlib import Path\n"
        "from jlegal_okf import input_limits as m\n"
        "from jlegal_okf.errors import AdapterError\n"
        "fds=[]\noriginal=m.os.open\n"
        "def track(path,flags):\n"
        " assert flags & os.O_NONBLOCK\n"
        " fd=original(path,flags); fds.append(fd); return fd\n"
        "m.os.open=track\n"
        "try: m.read_xml_bytes(Path(sys.argv[1]))\n"
        "except AdapterError as exc: assert str(exc)=='INPUT_NOT_REGULAR'\n"
        "else: raise AssertionError('FIFO was accepted')\n"
        "assert len(fds)==1\n"
        "try: os.fstat(fds[0])\n"
        "except OSError: pass\n"
        "else: raise AssertionError('descriptor leaked')\n"
    )
    result = subprocess.run([sys.executable, "-B", "-c", script, str(fifo)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("dimension,constant,code", [
    ("depth", "MAX_XML_DEPTH", "INPUT_XML_DEPTH_LIMIT"),
    ("elements", "MAX_XML_ELEMENTS", "INPUT_XML_ELEMENT_LIMIT"),
])
def test_generic_and_egov_entrypoints_apply_runtime_limits(tmp_path, monkeypatch, dimension, constant, code):
    path = tmp_path / "input.xml"
    path.write_bytes(b"<r><c/></r>")
    monkeypatch.setattr(limits, constant, 1)
    for adapter in (xml_adapter, html_adapter):
        with pytest.raises(AdapterError, match="^" + code + "$"):
            adapter(path, MAPPING)
    for call in (egov.admit_egov_xml, egov.egov_xml_adapter):
        with pytest.raises(AdapterError, match="^" + code + "$"):
            call(FIXTURE)
    assert egov.is_egov_xml(FIXTURE) is False


def test_generic_and_egov_size_limit_constants_are_resolved_at_call_time(tmp_path, monkeypatch):
    path = tmp_path / "input.xml"
    path.write_bytes(b"<r/> ")
    monkeypatch.setattr(limits, "MAX_XML_BYTES", 4)
    for adapter in (xml_adapter, html_adapter):
        with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
            adapter(path, MAPPING)
    monkeypatch.setattr(egov, "MAX_EGOV_XML_BYTES", 4)
    with pytest.raises(AdapterError, match="^EGOV_XML_INPUT_TOO_LARGE$"):
        egov._read_admissible_xml(path)
    with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
        egov._safe_fromstring(b"<r/> ")


@pytest.mark.parametrize("constant", ["MAX_XML_DEPTH", "MAX_XML_ELEMENTS"])
@pytest.mark.parametrize("status", [200, 400])
def test_fetch_parse_limits_preserve_existing_error_surface(tmp_path, monkeypatch, constant, status):
    import httpx

    class Response:
        status_code = status
        headers = {}
        url = "https://example.invalid/synthetic-response"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_bytes(self):
            yield b"<Law><LawBody/></Law>" if status == 200 else b"<error_info><code>invented</code></error_info>"

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Response())
    monkeypatch.setattr(limits, constant, 1)
    output = tmp_path / "not-created.xml"
    code = "EGOV_FETCH_XML" if status == 200 else "EGOV_FETCH_HTTP_400"
    with pytest.raises(JLegalError, match="^" + code + "$"):
        egov.fetch_egov_xml("SyntheticLaw001", output)
    assert not output.exists()


def test_existing_complete_synthetic_sources_pass_default_limits():
    sources = sorted((FIXTURE.parent).rglob("*.xml"))
    assert sources
    for source in sources:
        raw = source.read_bytes()
        assert ET.tostring(limits.parse_xml(raw)) == ET.tostring(ET.fromstring(raw))
    assert egov.admit_egov_xml(FIXTURE).raw == FIXTURE.read_bytes()
    assert egov.egov_xml_adapter(FIXTURE).nodes
