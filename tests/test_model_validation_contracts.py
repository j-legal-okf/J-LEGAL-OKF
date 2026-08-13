from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from jlegal_okf.model import (
    CrosswalkRelation,
    LegalNode,
    LegacyCrosswalk,
    NodeKind,
    RetrievalDocument,
    SourceRef,
    Temporal,
    law_identifier,
    node_identifier,
    normalize_identifier,
    version_identifier,
)
from jlegal_okf.pipeline import (
    canonical_crosswalk_jsonl,
    canonical_projection_jsonl,
    read_crosswalk,
    read_jsonl,
    read_projection,
)
from jlegal_okf.validation import collect_diagnostics


def source() -> SourceRef:
    return SourceRef(
        "file:///synthetic.txt",
        hashlib.sha256(b"synthetic").hexdigest(),
        "synthetic",
        "fixture",
        1,
        0,
        9,
    )


def make_node(
    locator: str = "/law/root",
    *,
    kind: NodeKind = NodeKind.LAW,
    depth: int = 0,
    parent_id: str | None = None,
    text: str = "合成法令の本文",
    start: str | None = None,
    end: str | None = None,
    ordinal: int | None = None,
    branch: tuple[int, ...] | None = None,
) -> LegalNode:
    return LegalNode(
        "Synthetic jurisdiction",
        "LAW",
        "S 1",
        None,
        locator,
        kind,
        depth,
        text,
        Temporal(start, end),
        source(),
        parent_id,
        ordinal,
        branch,
        None,
        "Heading",
        (),
    )


def test_identifier_normalization_and_prefixes() -> None:
    a = make_node()
    b = make_node()
    assert a.law_id.startswith("law_")
    assert a.node_id.startswith("node_")
    assert a.version_id.startswith("ver_")
    assert a == b
    assert normalize_identifier("Ａ  \tＢ") == "A B"
    assert normalize_identifier(" A ", authority_or_jurisdiction=True) == "a"


def test_text_is_not_normalized() -> None:
    assert make_node(text="Ａ\u3000Ｂ").text == "Ａ\u3000Ｂ"


def test_temporal_roundtrip() -> None:
    value = Temporal("2020-01-01", None, "2020-01-01")
    assert Temporal.from_dict(value.to_dict()).promulgated == "2020-01-01"


def test_strict_node_keys() -> None:
    raw = make_node().to_dict()
    raw.pop("heading")
    with pytest.raises(ValueError, match="NODE_KEYS"):
        type(make_node()).from_dict(raw)


def test_root_contract_diagnostic() -> None:
    node = make_node(kind=NodeKind.ARTICLE)
    assert "ROOT_KIND" in {item.code for item in collect_diagnostics([node])}


def test_parent_transition_and_temporal_diagnostics() -> None:
    root = make_node(start="2020-01-01", end="2021-01-01")
    child = make_node(
        "article",
        kind=NodeKind.ARTICLE,
        depth=1,
        parent_id=root.node_id,
        start="2021-01-01",
    )
    assert "PARENT_TEMPORAL" in {
        item.code for item in collect_diagnostics([root, child])
    }


def test_diagnostics_aggregate_stably() -> None:
    with pytest.raises(ValueError, match="NODE_ORDINAL"):
        make_node(kind=NodeKind.ARTICLE, ordinal=0, branch=(0,))


def test_crosswalk_target_and_ambiguous_reason() -> None:
    node = make_node()
    crosswalk = LegacyCrosswalk(
        "old",
        node.node_id,
        "bad",
        CrosswalkRelation.AMBIGUOUS,
        None,
        node.source.sha256,
    )
    assert {item.code for item in collect_diagnostics([node], [crosswalk])} == {
        "CROSSWALK_AMBIGUOUS_REASON",
        "CROSSWALK_TARGET",
    }


def test_crosswalk_duplicate_target_diagnostic_fires_for_repeated_pairs() -> None:
    """Two crosswalk rows sharing both legacy_id and target_version_id is
    exactly what CROSSWALK_DUPLICATE_TARGET (validation.py's `old_ids`
    same-pair check) exists to catch; reachable with two plainly valid rows,
    no bypass required.
    """
    node = make_node()
    first = LegacyCrosswalk(
        "old", node.node_id, node.version_id, CrosswalkRelation.EXACT, None, node.source.sha256
    )
    second = LegacyCrosswalk(
        "old", node.node_id, node.version_id, CrosswalkRelation.EXACT, None, node.source.sha256
    )
    assert "CROSSWALK_DUPLICATE_TARGET" in {
        item.code for item in collect_diagnostics([node], [first, second])
    }


def test_duplicate_version_and_overlap() -> None:
    first = make_node()
    second = make_node(text="改正", start="2020-01-01")
    assert "TEMPORAL_OVERLAP" in {
        item.code for item in collect_diagnostics([first, second])
    }


def test_duplicate_version_diagnostic_fires_for_identical_versions() -> None:
    """Two independently constructed nodes with identical identity-bearing
    fields hash to the same version_id, which is exactly what DUPLICATE_VERSION
    (validation.py's `n.version_id in seen_versions` check) exists to catch.
    """
    first = make_node()
    second = make_node()
    assert first.version_id == second.version_id
    assert "DUPLICATE_VERSION" in {
        item.code for item in collect_diagnostics([first, second])
    }


def test_heading_changes_version_not_semantic_node() -> None:
    first = make_node()
    second = replace(first, heading="Retitled")
    assert first.node_id == second.node_id
    assert first.version_id != second.version_id


def test_label_attributes_and_delimiters_change_version_safely() -> None:
    node = make_node()
    assert node.version_id != replace(node, label="Label").version_id
    assert node.version_id != replace(node, attributes=(("x", "y"),)).version_id
    assert version_identifier("n", Temporal(), "a|b", "c") != version_identifier(
        "n", Temporal(), "a", "b|c"
    )


def test_structured_id_payloads_do_not_delimiter_collide() -> None:
    assert law_identifier("a|b", "c", "1", None) != law_identifier(
        "a", "b|c", "1", None
    )
    assert node_identifier("law_a|b", "c") != node_identifier("law_a", "b|c")


def test_official_law_key_overrides_source_provenance_for_identity() -> None:
    assert law_identifier("a", "o", "1", "source-a") == law_identifier(
        "a", "o", "1", "source-b"
    )
    assert law_identifier("a", "o", None, "source-a") != law_identifier(
        "a", "o", None, "source-b"
    )


@pytest.mark.parametrize(
    "args",
    [
        (" ", "O", "1", None),
        ("A", " ", "1", None),
        ("A", "O", "   ", "source"),
        ("A", "O", None, " \t "),
    ],
)
def test_identity_fields_reject_normalized_empty(
    args: tuple[str, str, str | None, str | None],
) -> None:
    with pytest.raises(ValueError):
        law_identifier(*args)


def test_promulgated_repealed_are_versioned() -> None:
    first = make_node()
    promulgated = replace(first, temporal=Temporal(promulgated="2020-01-01"))
    repealed = replace(first, temporal=Temporal(repealed="2021-01-01"))
    assert first.node_id == promulgated.node_id == repealed.node_id
    assert len({first.version_id, promulgated.version_id, repealed.version_id}) == 3


def test_crosswalk_source_sha_model_and_target_validation() -> None:
    node = make_node()
    with pytest.raises(ValueError):
        LegacyCrosswalk(
            "old",
            node.node_id,
            node.version_id,
            CrosswalkRelation.EXACT,
            None,
            "z" * 64,
        )
    unrelated = "b" * 64
    mismatch = LegacyCrosswalk(
        "old",
        node.node_id,
        node.version_id,
        CrosswalkRelation.EXACT,
        None,
        unrelated,
    )
    assert "CROSSWALK_SOURCE_MISMATCH" in {
        item.code for item in collect_diagnostics([node], [mismatch])
    }
    valid = LegacyCrosswalk(
        "old",
        node.node_id,
        node.version_id,
        CrosswalkRelation.EXACT,
        None,
        node.source.sha256,
    )
    assert not collect_diagnostics([node], [valid])


@pytest.mark.parametrize("field", ["legacy_id", "target_node_id", "target_version_id"])
@pytest.mark.parametrize("value", [[], {}, 1, None])
def test_crosswalk_required_fields_are_strict_strings(
    field: str, value: object
) -> None:
    node = make_node()
    raw = {
        "legacy_id": "old",
        "target_node_id": node.node_id,
        "target_version_id": node.version_id,
        "relation": CrosswalkRelation.EXACT,
        "reason": None,
        "source_sha256": node.source.sha256,
    }
    raw[field] = value
    with pytest.raises(ValueError, match="CROSSWALK_FIELDS"):
        LegacyCrosswalk(**raw)


@pytest.mark.parametrize("value", [[], {}, 1])
def test_crosswalk_reason_is_optional_string_only(value: object) -> None:
    node = make_node()
    with pytest.raises(ValueError, match="CROSSWALK_FIELDS"):
        LegacyCrosswalk(
            "old",
            node.node_id,
            node.version_id,
            CrosswalkRelation.EXACT,
            value,
            node.source.sha256,
        )


def test_crosswalk_diagnostics_are_total_for_bypassed_invalid_object() -> None:
    crosswalk = object.__new__(LegacyCrosswalk)
    for key, value in {
        "legacy_id": [],
        "target_node_id": {},
        "target_version_id": [],
        "relation": "exact",
        "reason": [],
        "source_sha256": [],
    }.items():
        object.__setattr__(crosswalk, key, value)
    assert "CROSSWALK_FIELDS" in {
        item.code for item in collect_diagnostics([make_node()], [crosswalk])
    }


def test_locator_duplicate_diagnostic_requires_bypassing_node_identity() -> None:
    """LOCATOR_DUPLICATE fires when two nodes share the same (law_id, locator)
    key but disagree on node_id (validation.py's `locator_law` same-key
    check). For any normally constructed LegalNode, node_id is always
    node_identifier(law_id, locator) -- a pure function of that same key -- so
    two nodes sharing the key can never disagree on node_id through the
    public constructor. Reaching this diagnostic therefore requires forging a
    second object's node_id after construction, the same technique
    test_crosswalk_diagnostics_are_total_for_bypassed_invalid_object uses.
    """
    base = make_node()
    forged = object.__new__(LegalNode)
    for key, value in base.__dict__.items():
        object.__setattr__(forged, key, value)
    object.__setattr__(forged, "node_id", "node_forged-locator-duplicate")
    assert forged.law_id == base.law_id
    assert forged.locator == base.locator
    assert forged.node_id != base.node_id
    assert "LOCATOR_DUPLICATE" in {
        item.code for item in collect_diagnostics([base, forged])
    }


def test_helper_artifact_roundtrip_and_strict_projection_fields(tmp_path: Path) -> None:
    node = make_node()
    crosswalk = LegacyCrosswalk(
        "old",
        node.node_id,
        node.version_id,
        CrosswalkRelation.EXACT,
        None,
        node.source.sha256,
    )
    document = RetrievalDocument(
        "projection_fixture",
        "1",
        node.node_id,
        node.version_id,
        node.law_id,
        node.locator,
        node.heading,
        node.text,
        node.kind,
        node.temporal,
        node.source,
    )
    crosswalk_path = tmp_path / "crosswalk.jsonl"
    projection_path = tmp_path / "projection.jsonl"
    crosswalk_path.write_bytes(canonical_crosswalk_jsonl([crosswalk]))
    projection_path.write_bytes(canonical_projection_jsonl([document]))
    assert read_crosswalk(crosswalk_path) == [crosswalk]
    assert read_projection(projection_path) == [document]
    base = document.__dict__.copy()
    for field in (
        "projection_id",
        "projection_version",
        "node_id",
        "version_id",
        "law_id",
        "locator",
        "text",
    ):
        for value in ([], {}, 1, None):
            raw = base.copy()
            raw[field] = value
            with pytest.raises(ValueError, match="PROJECTION_FIELDS"):
                RetrievalDocument(**raw)
    for value in ([], {}, 1):
        raw = base.copy()
        raw["heading"] = value
        with pytest.raises(ValueError, match="PROJECTION_FIELDS"):
            RetrievalDocument(**raw)
    with pytest.raises(ValueError, match="SOURCE_SHA256"):
        SourceRef("file:///x", "not-a-sha", "fixture")


@pytest.mark.parametrize(
    "path,value",
    [
        ("depth", True),
        ("ordinal", True),
        ("branch", [True]),
        ("source.page", True),
        ("source.byte_start", True),
    ],
)
def test_jsonl_boolean_numeric_fields_rejected(
    tmp_path: Path, path: str, value: object
) -> None:
    raw = make_node(ordinal=1, branch=(1,)).to_dict()
    target = raw
    for part in path.split(".")[:-1]:
        target = target[part]
    target[path.split(".")[-1]] = value
    if path == "source.byte_start":
        raw["source"]["byte_end"] = 1
    target_path = tmp_path / "bad.jsonl"
    target_path.write_text(json.dumps(raw) + "\n")
    with pytest.raises(Exception):
        read_jsonl(target_path)


@pytest.mark.parametrize("field", ["jurisdiction", "authority", "locator", "text"])
def test_jsonl_string_fields_reject_nonstrings(tmp_path: Path, field: str) -> None:
    raw = make_node().to_dict()
    raw[field] = 1
    target_path = tmp_path / "bad.jsonl"
    target_path.write_text(json.dumps(raw) + "\n")
    with pytest.raises(Exception):
        read_jsonl(target_path)


def test_attributes_duplicate_rejected_and_roundtrip_lossless() -> None:
    with pytest.raises(ValueError, match="DUPLICATE"):
        replace(make_node(), attributes=(("a", "1"), ("a", "2")))
    value = replace(make_node(), attributes=(("a", "1"), ("b", "2")))
    assert type(value).from_dict(value.to_dict()) == value


def test_node_attributes_duplicate_diagnostic_fires_on_construction() -> None:
    """Precise companion to test_attributes_duplicate_rejected_and_roundtrip_lossless
    above (which only asserts the generic substring "DUPLICATE"): this pins the
    exact NODE_ATTRIBUTES_DUPLICATE code that model.py's LegalNode.__post_init__
    raises for a duplicate attribute key.
    """
    with pytest.raises(ValueError, match=r"^NODE_ATTRIBUTES_DUPLICATE$"):
        replace(make_node(), attributes=(("dup", "1"), ("dup", "2")))
