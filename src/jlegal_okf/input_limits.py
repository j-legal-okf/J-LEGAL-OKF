"""Bound source reads and structured inputs; no process resource isolation."""

from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Iterator
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import DefusedXMLParser
import yaml

from .errors import AdapterError, ValidationError


MAX_XML_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 128
MAX_XML_ELEMENTS = 250_000
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_JSON_TOKENS = 250_000
MAX_OPTION_BYTES = 1024 * 1024
MAX_OPTION_DEPTH = 32
MAX_OPTION_TOKENS = 10_000
MAX_OPTION_INTEGER_BITS = 4096


def _positive_limit(value: int | None, default: int) -> int:
    resolved = default if value is None else value
    if type(resolved) is not int or resolved <= 0:
        raise AdapterError("INPUT_LIMIT_VALUE")
    return resolved


def read_bounded_bytes(path: Path, *, max_bytes: int,
                       diagnostic_prefix: str = "INPUT", allow_empty: bool = True) -> bytes:
    """Inspect and read the same regular-file descriptor, at most limit + 1 bytes.

    Nonblocking open prevents waiting for a POSIX FIFO writer before fstat can
    reject it. Symlinks to regular files remain usable. This does not impose a
    timeout on a filesystem operation or a process memory limit.
    """
    # No implicit default here: callers must select the source/option budget.
    limit = _positive_limit(max_bytes, 0)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if os.name == "posix":
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise AdapterError(f"{diagnostic_prefix}_NOT_REGULAR")
            if metadata.st_size > limit:
                raise AdapterError(f"{diagnostic_prefix}_TOO_LARGE")
            # The size is only an early rejection. A stale size or growth after
            # fstat cannot turn this into an unbounded allocation/read.
            # Unbuffered I/O avoids BufferedReader prefetch beyond the budget.
            # Short reads consume only part of the same cumulative allowance.
            raw = bytearray()
            with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as source:
                while len(raw) <= limit:
                    chunk = source.read(limit + 1 - len(raw))
                    if not chunk:
                        break
                    raw.extend(chunk)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise AdapterError(f"{diagnostic_prefix}_UNAVAILABLE") from exc
    if len(raw) > limit:
        raise AdapterError(f"{diagnostic_prefix}_TOO_LARGE")
    if not raw and not allow_empty:
        raise AdapterError(f"{diagnostic_prefix}_EMPTY")
    return bytes(raw)


def read_xml_bytes(path: Path, *, max_bytes: int | None = None,
                   diagnostic_prefix: str = "INPUT", allow_empty: bool = True) -> bytes:
    """Keep the XML reader API and resolve its default at call time."""
    return read_bounded_bytes(path, max_bytes=_positive_limit(max_bytes, MAX_XML_BYTES),
                              diagnostic_prefix=diagnostic_prefix, allow_empty=allow_empty)


def _utf8_size(text: str, limit: int | None = None, code: str = "INPUT_TOO_LARGE") -> int:
    # Character count is a lower bound; do not first allocate an unbounded
    # UTF-8 copy of a caller-owned string. Chunking also checks lone surrogates.
    if limit is not None and len(text) > limit:
        raise AdapterError(code)
    total = 0
    try:
        for start in range(0, len(text), 8192):
            total += len(text[start:start + 8192].encode("utf-8"))
            if limit is not None and total > limit:
                raise AdapterError(code)
    except UnicodeError:
        raise AdapterError("INPUT_ENCODING") from None
    return total


def _scan_json(text: str, max_depth: int, max_tokens: int) -> None:
    """Count lexical containers/keys/scalars; json.loads owns JSON grammar."""
    index = depth = tokens = 0
    size = len(text)
    while index < size:
        char = text[index]
        if char in " \t\r\n,:":
            index += 1
            continue
        if char in "}]":
            depth -= 1
            index += 1
            continue
        tokens += 1
        if tokens > max_tokens:
            raise AdapterError("INPUT_JSON_TOKEN_LIMIT")
        if char in "{[":
            depth += 1
            if depth > max_depth:
                raise AdapterError("INPUT_JSON_DEPTH_LIMIT")
            index += 1
        elif char == '"':
            index += 1
            while index < size:
                if text[index] == "\\":
                    index += 2
                elif text[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
        else:
            # Number/true/false/null/nonfinite or invalid bare token. No
            # substring allocation or numeric conversion during preflight.
            while index < size and text[index] not in ' \t\r\n,:{}[]"':
                index += 1


def _json_integer(text: str) -> int:
    bits = _positive_limit(None, MAX_OPTION_INTEGER_BITS)
    # 4096 bits need at most 1234 decimal digits. Resolve smaller runtime
    # budgets too, with a conservative integer-only upper approximation.
    digits = (bits * 30103) // 100000 + 1
    if len(text) - int(text.startswith("-")) > digits:
        raise AdapterError("INPUT_OPTION_INTEGER_LIMIT")
    value = int(text)
    if value.bit_length() > bits:
        raise AdapterError("INPUT_OPTION_INTEGER_LIMIT")
    return value


def _json_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise AdapterError("INPUT_NONFINITE")
    return value


def _json_constant(text: str) -> Any:
    raise AdapterError("INPUT_NONFINITE")


def parse_json(raw: bytes | str, *, max_bytes: int | None = None,
               max_depth: int | None = None, max_tokens: int | None = None) -> Any:
    """Preflight bounded JSON before decoding, preserving byte encodings."""
    byte_limit = _positive_limit(max_bytes, MAX_JSON_BYTES)
    depth_limit = _positive_limit(max_depth, MAX_JSON_DEPTH)
    token_limit = _positive_limit(max_tokens, MAX_JSON_TOKENS)
    if type(raw) is bytes:
        if len(raw) > byte_limit:
            raise AdapterError("INPUT_TOO_LARGE")
        try:
            text = raw.decode(json.detect_encoding(raw), "surrogatepass")
        except UnicodeError:
            raise AdapterError("INPUT_ENCODING") from None
    elif type(raw) is str:
        _utf8_size(raw, byte_limit)
        text = raw
    else:
        raise AdapterError("INPUT_OPTION_TYPE")
    _scan_json(text, depth_limit, token_limit)
    try:
        value = json.loads(text, parse_int=_json_integer, parse_float=_json_float,
                           parse_constant=_json_constant)
    except (ValueError, RecursionError):
        raise AdapterError("INPUT_JSON_PARSE") from None
    # Check decoded strings too: an escaped lone surrogate is ASCII in the
    # raw JSON. This does not impose an option-sized canonical byte limit on
    # source JSON. Duplicate occurrences were already charged by preflight.
    _walk_options(value, None, depth_limit, token_limit,
                  _positive_limit(None, MAX_OPTION_INTEGER_BITS))
    return value


def _children(value: dict | list) -> Iterator[tuple[Any, bool]]:
    if type(value) is dict:
        for key, item in value.items():
            yield key, True
            yield item, False
    else:
        for item in value:
            yield item, False


def _walk_options(value: Any, byte_limit: int | None, depth_limit: int,
                  token_limit: int, integer_limit: int) -> None:
    # Each frame holds only an iterator, not a copy of all children. Active
    # ancestry rejects cycles while charging shared objects at every use.
    stack = [(None, iter(((value, False),)))]
    active: set[int] = set()
    tokens = characters = 0
    while stack:
        identity, children = stack[-1]
        try:
            item, is_key = next(children)
        except StopIteration:
            stack.pop()
            if identity is not None:
                active.remove(identity)
            continue
        tokens += 1
        if tokens > token_limit:
            raise AdapterError("INPUT_OPTION_TOKEN_LIMIT")
        kind = type(item)
        if is_key and kind is not str:
            raise AdapterError("INPUT_OPTION_TYPE")
        if kind is dict or kind is list:
            identity = id(item)
            if identity in active:
                raise AdapterError("INPUT_OPTION_CYCLE")
            if len(stack) > depth_limit:
                raise AdapterError("INPUT_OPTION_DEPTH_LIMIT")
            active.add(identity)
            stack.append((identity, _children(item)))
        elif kind is str:
            characters += len(item)
            if byte_limit is not None and characters > byte_limit:
                raise AdapterError("INPUT_OPTION_BYTES_LIMIT")
            _utf8_size(item)
        elif kind is int:
            if item.bit_length() > integer_limit:
                raise AdapterError("INPUT_OPTION_INTEGER_LIMIT")
        elif kind is float:
            if not math.isfinite(item):
                raise AdapterError("INPUT_NONFINITE")
        elif kind is not bool and item is not None:
            raise AdapterError("INPUT_OPTION_TYPE")


def validate_options(value: Any, *, max_bytes: int | None = None,
                     max_depth: int | None = None, max_tokens: int | None = None,
                     max_integer_bits: int | None = None) -> None:
    """Validate an exact JSON graph before any comparison/serialization hooks."""
    byte_limit = _positive_limit(max_bytes, MAX_OPTION_BYTES)
    depth_limit = _positive_limit(max_depth, MAX_OPTION_DEPTH)
    token_limit = _positive_limit(max_tokens, MAX_OPTION_TOKENS)
    integer_limit = _positive_limit(max_integer_bits, MAX_OPTION_INTEGER_BITS)
    _walk_options(value, byte_limit, depth_limit, token_limit, integer_limit)
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    total = 0
    for chunk in encoder.iterencode(value):
        total += _utf8_size(chunk, byte_limit - total, "INPUT_OPTION_BYTES_LIMIT")


def parse_options_yaml(text: str, *, max_bytes: int | None = None,
                       max_depth: int | None = None, max_tokens: int | None = None) -> Any:
    """Scan SafeLoader events before construction; every alias is forbidden."""
    byte_limit = _positive_limit(max_bytes, MAX_OPTION_BYTES)
    depth_limit = _positive_limit(max_depth, MAX_OPTION_DEPTH)
    token_limit = _positive_limit(max_tokens, MAX_OPTION_TOKENS)
    if type(text) is not str:
        raise AdapterError("INPUT_OPTION_TYPE")
    _utf8_size(text, byte_limit)
    depth = tokens = 0
    events = yaml.parse(text, Loader=yaml.SafeLoader)
    try:
        for event in events:
            if isinstance(event, yaml.events.AliasEvent):
                raise AdapterError("INPUT_YAML_ALIAS_FORBIDDEN")
            if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
                depth += 1
                tokens += 1
                if depth > depth_limit:
                    raise AdapterError("INPUT_YAML_DEPTH_LIMIT")
            elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                depth -= 1
            elif isinstance(event, yaml.events.ScalarEvent):
                tokens += 1
            if tokens > token_limit:
                raise AdapterError("INPUT_YAML_TOKEN_LIMIT")
        value = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError, RecursionError):
        raise AdapterError("INPUT_YAML_PARSE") from None
    finally:
        events.close()
    validate_options(value, max_bytes=byte_limit, max_depth=depth_limit, max_tokens=token_limit)
    return value


def _option_text(path: Path) -> str:
    raw = read_bounded_bytes(path, max_bytes=MAX_OPTION_BYTES)
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        raise AdapterError("INPUT_ENCODING") from None


def load_mapping_option(value: str | None) -> tuple[Any, Path | None]:
    if value is None:
        return None, None
    path = Path(value)
    try:
        exists = path.exists()
    except OSError as exc:
        if exc.errno != errno.ENAMETOOLONG:
            raise AdapterError("INPUT_UNAVAILABLE") from None
        exists = False
    return (parse_options_yaml(_option_text(path)), path) if exists else (parse_options_yaml(value), None)


def load_json_option(value: str | None, diagnostic: str) -> Any:
    if value is None:
        return None
    try:
        text = _option_text(Path(value))
        result = parse_json(text, max_bytes=MAX_OPTION_BYTES, max_depth=MAX_OPTION_DEPTH,
                            max_tokens=MAX_OPTION_TOKENS)
    except AdapterError as exc:
        if str(exc) == "INPUT_UNAVAILABLE" and isinstance(exc.__cause__, FileNotFoundError):
            raise ValidationError(f"{diagnostic}_FILE_REQUIRED") from None
        if str(exc) == "INPUT_JSON_PARSE":
            raise ValidationError(f"{diagnostic}_JSON") from None
        raise
    validate_options(result)
    return result


class _LimitedTreeBuilder(ET.TreeBuilder):
    def __init__(self, max_depth: int, max_elements: int) -> None:
        super().__init__(element_factory=ET.Element)
        self._depth = 0
        self._elements = 0
        self._max_depth = max_depth
        self._max_elements = max_elements

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        # Check before TreeBuilder.start creates the next element. The root
        # counts as depth 1 and as one element; both limits are inclusive.
        if self._depth + 1 > self._max_depth:
            raise AdapterError("INPUT_XML_DEPTH_LIMIT")
        if self._elements + 1 > self._max_elements:
            raise AdapterError("INPUT_XML_ELEMENT_LIMIT")
        self._depth += 1
        self._elements += 1
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        element = super().end(tag)
        self._depth -= 1
        return element


def parse_xml(raw: bytes, *, max_bytes: int | None = None,
              max_depth: int | None = None, max_elements: int | None = None) -> ET.Element:
    """Parse bounded bytes with DTDs, entities and external references forbidden.

    Defaults are resolved at call time. Depth/element checks constrain tree
    construction; they do not bound parser token allocations, CPU or RSS.
    Syntax and defusedxml exceptions remain available to each caller's existing
    diagnostic surface, while resource-limit failures are AdapterError codes.
    """
    byte_limit = _positive_limit(max_bytes, MAX_XML_BYTES)
    depth_limit = _positive_limit(max_depth, MAX_XML_DEPTH)
    element_limit = _positive_limit(max_elements, MAX_XML_ELEMENTS)
    if len(raw) > byte_limit:
        raise AdapterError("INPUT_TOO_LARGE")
    parser = DefusedXMLParser(target=_LimitedTreeBuilder(depth_limit, element_limit),
                              forbid_dtd=True, forbid_entities=True, forbid_external=True)
    parser.feed(raw)
    return parser.close()
