"""Keeps DIAGNOSTIC_LAYERS, the codes validation.py actually emits, and
docs/validator-layers.md from drifting apart. See that document for what
each code and layer means.
"""

from __future__ import annotations

import re
from pathlib import Path

from jlegal_okf.validation import DIAGNOSTIC_LAYERS, Diagnostic

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VALIDATION_SOURCE = _REPO_ROOT / "src" / "jlegal_okf" / "validation.py"
_DOC = _REPO_ROOT / "docs" / "validator-layers.md"

# Matches add("SOME_CODE" literal calls; codes are ASCII upper-snake-case
# and may contain digits (e.g. SOURCE_SHA256), so digits must stay in the
# character class -- omitting them previously caused that exact code to be
# silently skipped during authoring of this table.
_ADD_CALL = re.compile(r'add\("([A-Z0-9_]+)"')
_DOC_CODE_CELL = re.compile(r"^\| `([A-Z0-9_]+)` \|", re.MULTILINE)
# Each layer lives under its own "### N. <Title>" heading in the doc; matching
# on the numbered heading (not just any "###") skips the unnumbered
# "### Classification principle" subsection, which has no code table.
_SECTION_HEADER = re.compile(r"^### \d+\. (.+)$", re.MULTILINE)
_H2_HEADER = re.compile(r"^## ", re.MULTILINE)
_HEADER_TITLE_TO_LAYER = {
    "Syntax": "syntax",
    "Structure": "structure",
    "Source fidelity": "source_fidelity",
    "Semantic and temporal relations": "semantic_temporal",
}
_FOUR_LAYERS = set(_HEADER_TITLE_TO_LAYER.values())


def _codes_emitted_by_validation_py() -> set[str]:
    return set(_ADD_CALL.findall(_VALIDATION_SOURCE.read_text(encoding="utf-8")))


def _doc_code_to_layer() -> dict[str, str]:
    """{code: layer}, read from which numbered section each code's table row is under.

    This catches a code's row being moved to the wrong section (a layer
    reassignment) as well as a code being added, removed, or renamed only in
    the doc -- a plain code-set comparison against DIAGNOSTIC_LAYERS would
    miss a same-code-set-different-section edit.
    """
    text = _DOC.read_text(encoding="utf-8")
    headers = list(_SECTION_HEADER.finditer(text))
    assert len(headers) == 4, f"expected exactly 4 numbered layer sections, found {len(headers)}"
    mapping: dict[str, str] = {}
    for index, header in enumerate(headers):
        title = header.group(1).strip()
        layer = _HEADER_TITLE_TO_LAYER[title]
        next_h2 = next((m.start() for m in _H2_HEADER.finditer(text) if m.start() > header.end()), len(text))
        section_end = headers[index + 1].start() if index + 1 < len(headers) else next_h2
        section_codes = _DOC_CODE_CELL.findall(text[header.end():section_end])
        assert section_codes, f"section {title!r} lists no diagnostic codes"
        for code in section_codes:
            assert code not in mapping, f"{code} appears under more than one layer section"
            mapping[code] = layer
    return mapping


def test_diagnostic_layers_key_set_matches_codes_validation_py_can_emit() -> None:
    emitted = _codes_emitted_by_validation_py()
    assert len(emitted) >= 30, "sanity: the add(...) extraction regex should find most diagnostic codes"
    assert set(DIAGNOSTIC_LAYERS) == emitted


def test_diagnostic_layers_values_are_exactly_the_four_documented_layers() -> None:
    assert set(DIAGNOSTIC_LAYERS.values()) == _FOUR_LAYERS


def test_docs_validator_layers_sections_match_diagnostic_layers_exactly() -> None:
    """Not just the same codes -- the same code-to-layer assignment, section by section."""
    assert _doc_code_to_layer() == DIAGNOSTIC_LAYERS


def test_diagnostic_to_dict_includes_its_layer() -> None:
    diagnostic = Diagnostic("ROOT_KIND", "node_x", "")
    assert diagnostic.to_dict() == {"code": "ROOT_KIND", "subject": "node_x", "detail": "", "layer": "structure"}
