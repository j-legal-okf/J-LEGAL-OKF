"""Validate the fixed, source-authored examples, without producer/checker imports.

This is a fixture acceptance test, not an arbitrary-input conformance checker.
The XML strings below pin the authored inputs; expected strings live in JSON.
"""

import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


FIXTURE = Path(__file__).resolve().parents[1] / "examples/conformance/text-display-oracle.json"
XML_S = frozenset(" \t\r\n")
FORMATTING_OWNERS = {
    "Article", "Paragraph", "ParagraphSentence", "Table", "TableRow",
    "TableColumn", "StyleStruct",
}
VERSION = "ver_00000000-0000-4000-8000-000000000001"
SOURCE_XML = {
    "style": "<StyleStruct><Style>abc</Style></StyleStruct>",
    "ruby": "<Sentence>A<Ruby>B<Rt>C</Rt></Ruby>D</Sentence>",
    "sup-sub": "<Sentence>A<Sup>2</Sup>B<Sub>3</Sub>C</Sentence>",
    "empty-cell": "<TableColumn/>",
    "leaf-whitespace": "<TableColumn> \n  </TableColumn>",
    "structural-whitespace": (
        "<Article>\n <Paragraph>\n<ParagraphSentence><Sentence>x</Sentence>"
        "</ParagraphSentence>\n</Paragraph>\n</Article>"
    ),
    "unicode-whitespace": "<Sentence>\u3000a\u00a0  b\u3000</Sentence>",
    "character-references": "<Sentence>A&amp;B&#x20;C</Sentence>",
    "mixed-tails": "<Sentence>A<Ruby>B<Rt>C</Rt></Ruby> D<Sup>2</Sup> E</Sentence>",
    "table-leaf-whitespace": (
        "<Table>\n<TableRow>\n<TableColumn> </TableColumn>\n"
        "<TableColumn><Sentence>x</Sentence></TableColumn>\n</TableRow>\n</Table>"
    ),
    "header-mixed-whitespace": (
        "<TableHeaderColumn> <Ruby>B<Rt>C</Rt></Ruby> </TableHeaderColumn>"
    ),
    "unicode-not-normalized": "<Sentence>e\u0301 \uff21</Sentence>",
    "xml-newlines": "<Sentence>A\r\nB&#xD;C</Sentence>",
    "line-attribute": '<Sentence><Line Style="solid">AB</Line>C</Sentence>',
}
# Authored canonical-field examples, not complete LegalNode records. The version
# is only a well-formed example marker binding, not a computed node identity.
# Tuple order: heading, label, locator, text.
DISPLAY_INPUTS = {
    "heading": (
        "Synthetic heading", "Unused label", "/law/synthetic/article/1",
        "First line.\nSecond line.",
    ),
    "empty": ("Empty text", None, "/law/synthetic/article/2", ""),
    "whitespace-only": (
        "Whitespace text", None, "/law/synthetic/article/3", " \t\n\u3000\u00a0 ",
    ),
    "label-fallback": ("", "Synthetic label", "/law/synthetic/article/4", "Label body."),
    "locator-fallback": (None, "", "/law/synthetic/article/5", "Locator body."),
    "preserved-newlines": (
        "Preserved newlines", None, "/law/synthetic/article/7", "A\r\nB\rC",
    ),
    "literal-markers": (
        "Literal source markers", None, "/law/synthetic/article/6",
        "A<!-- jlegal-source:ver_00000000-0000-4000-8000-000000000001:begin -->"
        "B<!-- jlegal-source:ver_00000000-0000-4000-8000-000000000001:end -->C",
    ),
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, f"Duplicate JSON key: {key}"
        result[key] = value
    return result


@pytest.fixture(scope="module")
def oracle():
    return json.loads(FIXTURE.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def _by_id(oracle, field, case_id):
    return next(case for case in oracle[field] if case["id"] == case_id)


def _slots(element, path="0", parent=None):
    """All text/tail slots in document order, including absent (empty) slots.

    A text slot belongs to its element; a tail belongs to that element's parent.
    The root tail has no owner. Child indexes are zero-based.
    """
    yield f"{path}:text", element.text or "", element
    for index, child in enumerate(element):
        yield from _slots(child, f"{path}/{index}", element)
    yield f"{path}:tail", element.tail or "", parent


def _retained_character_data(case):
    slots = list(_slots(ET.fromstring(case["xml"])))
    by_name = {name: (value, owner) for name, value, owner in slots}
    omitted = case["formatting_slots"]
    assert len(omitted) == len(set(omitted)), "Repeated formatting slot"
    assert set(omitted) <= set(by_name), "Formatting slot does not exist"
    eligible = {
        name for name, value, owner in slots
        if value and set(value) <= XML_S
        and owner is not None and owner.tag in FORMATTING_OWNERS and len(owner) > 0
    }
    # Exact equality checks both illegal omissions and unlisted formatting.
    assert set(omitted) == eligible, "Formatting ownership/value disagrees with rule"
    return "".join(value for name, value, _ in slots if name not in omitted)


def test_fixture_shape_and_coverage(oracle):
    assert type(oracle) is dict
    assert set(oracle) == {
        "schema", "authorship", "rule_ids", "formatting_owners", "text_cases", "display_cases",
    }
    assert oracle["schema"] == "jlegal-text-display-oracle/v1"
    assert oracle["authorship"] == "entirely-invented"
    assert oracle["rule_ids"] == [
        "JLEGAL-TEXT-PRESERVE-1", "DB-TEXT-1", "DB-DISPLAY-1", "DB-ORACLE-1",
    ]
    owners = oracle["formatting_owners"]
    assert type(owners) is list
    assert len(owners) == len(set(owners))
    assert set(owners) == FORMATTING_OWNERS
    for field, required in (("text_cases", SOURCE_XML), ("display_cases", DISPLAY_INPUTS)):
        assert type(oracle[field]) is list
        ids = []
        for case in oracle[field]:
            assert type(case) is dict
            assert type(case["id"]) is str
            ids.append(case["id"])
        assert len(ids) == len(set(ids))
        assert set(ids) == set(required)


@pytest.mark.parametrize("case_id", SOURCE_XML)
def test_text_matches_authored_xml_slots(oracle, case_id):
    case = _by_id(oracle, "text_cases", case_id)
    assert set(case) == {"id", "xml", "expected_text", "formatting_slots"}
    assert type(case["xml"]) is str
    assert case["xml"] == SOURCE_XML[case_id]
    assert type(case["expected_text"]) is str
    assert type(case["formatting_slots"]) is list
    assert all(type(slot) is str for slot in case["formatting_slots"])
    assert _retained_character_data(case) == case["expected_text"]


@pytest.mark.parametrize("case_id,slots", [
    ("leaf-whitespace", ["0:text"]),  # A structural tag alone is insufficient.
    ("header-mixed-whitespace", ["0:text", "0/0:tail"]),
    ("mixed-tails", ["0/0:tail"]),  # Meaningful tail data cannot be omitted.
    ("style", ["0/0:text"]),
    ("empty-cell", ["0:text"]),  # Empty is not nonempty XML S whitespace.
    ("empty-cell", ["0/9:text"]),
    ("structural-whitespace", ["0:text", "0:text"]),
    ("structural-whitespace", []),
])
def test_invalid_formatting_annotations_fail(oracle, case_id, slots):
    case = copy.deepcopy(_by_id(oracle, "text_cases", case_id))
    case["formatting_slots"] = slots
    with pytest.raises(AssertionError):
        _retained_character_data(case)


@pytest.mark.parametrize("case_id", DISPLAY_INPUTS)
def test_display_literal_matches_complete_grammar(oracle, case_id):
    case = _by_id(oracle, "display_cases", case_id)
    assert set(case) == {
        "id", "version_id", "heading", "label", "locator", "text", "expected_body",
    }
    assert case["version_id"] == VERSION
    for field in ("version_id", "locator", "text", "expected_body"):
        assert type(case[field]) is str
    for field in ("heading", "label"):
        assert case[field] is None or type(case[field]) is str
    assert tuple(case[field] for field in ("heading", "label", "locator", "text")) == DISPLAY_INPUTS[case_id]
    title = next(value for value in (case["heading"], case["label"], case["locator"]) if value)
    prefix = "# " + title + "\n\n## Source text\n\n"
    begin = "<!-- jlegal-source:" + case["version_id"] + ":begin -->"
    end = "<!-- jlegal-source:" + case["version_id"] + ":end -->"
    expected = case["expected_body"]  # This literal is never replaced or generated.
    assert expected == prefix + begin + case["text"] + end + "\n"

    # Positional slices use the known payload length, never the first marker
    # occurrence. This includes literal begin/end marker strings inside payload.
    payload_start = len(prefix) + len(begin)
    payload_end = payload_start + len(case["text"])
    assert expected[payload_start:payload_end] == case["text"]
    assert expected[payload_end:] == end + "\n"

    changed_begin = begin.replace(case["version_id"], "ver_00000000-0000-4000-8000-000000000002")
    changed_end = end.replace(case["version_id"], "ver_00000000-0000-4000-8000-000000000002")
    mutations = {
        "added-prefix": "Commentary.\n" + expected,
        "added-suffix": expected + "Commentary.\n",
        "missing-begin": prefix + case["text"] + end + "\n",
        "missing-end": prefix + begin + case["text"] + "\n",
        "markerless": prefix + case["text"] + "\n",
        "changed-payload": expected[:payload_end] + "!" + expected[payload_end:],
        "changed-title": "# Different title\n\n## Source text\n\n" + begin + case["text"] + end + "\n",
        "changed-begin-version": prefix + changed_begin + case["text"] + end + "\n",
        "changed-end-version": prefix + begin + case["text"] + changed_end + "\n",
        "missing-final-newline": expected[:-1],
    }
    for mutation, body in mutations.items():
        assert body != expected, mutation
    if case_id == "preserved-newlines":
        assert expected.replace("\r\n", "\n").replace("\r", "\n") != expected
