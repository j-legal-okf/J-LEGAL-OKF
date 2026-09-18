"""Pins the behaviors `docs/known-limitations.md` documents as known limitations.

Each test below fixes exactly one bullet point that document makes. If a
test here fails, the limitation it names has changed (most likely: it has
been resolved), and `docs/known-limitations.md` must be updated to match
before the failure is treated as a regression. This file is deliberately
self-contained -- it does not import fixtures or helpers from any other
test module -- so each test can be read on its own next to the document
bullet it fixes. The same behaviors may also be covered, less directly, by
other test modules; that overlap is intentional and this file is not meant
to replace those tests.
"""

from __future__ import annotations

import xml.etree.ElementTree as _StdElementTree

import pytest

from jlegal_okf import adapters
from jlegal_okf.egov import egov_xml_adapter
from jlegal_okf.errors import AdapterError, ValidationError
from jlegal_okf.legal_okf import LegalOKFError, export_okf
from jlegal_okf.model import LegalNode, NodeKind, SourceRef, Temporal
from jlegal_okf.pipeline import compile_corpus
from jlegal_okf.validation import collect_diagnostics


def _minimal_law(body: str) -> str:
    """An e-Gov API v2 XML envelope `egov_xml_adapter()` accepts, wrapping `body`.

    Not claimed to be the smallest accepted form: a bare `<Law>` document
    without the `law_data_response`/`law_full_text` envelope is also
    accepted by `egov_xml_adapter()` and is smaller (verified separately).
    This helper uses the envelope shape only because it is the shape this
    test file's assertions were written and verified against.
    """
    return (
        "<law_data_response><law_full_text>"
        "<Law LawId=\"InventedLaw001\" LawType=\"Act\" Era=\"Reiwa\" Year=\"2\" "
        "PromulgateMonth=\"4\" PromulgateDay=\"1\">"
        "<LawBody><LawTitle>架空検証法</LawTitle>" + body + "</LawBody></Law>"
        "</law_full_text></law_data_response>"
    )


def _synthetic_source() -> SourceRef:
    import hashlib

    return SourceRef(
        uri="file:///synthetic.txt",
        sha256=hashlib.sha256(b"synthetic").hexdigest(),
        adapter="synthetic",
        source_key="fixture",
    )


def _synthetic_node(
    locator: str,
    *,
    kind: NodeKind = NodeKind.LAW,
    depth: int = 0,
    parent_id: str | None = None,
    text: str = "synthetic text",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> LegalNode:
    """A minimal, self-contained `LegalNode`, independent of any other test module's fixtures."""
    return LegalNode(
        jurisdiction="Synthetic",
        authority="LAW",
        law_number_key=None,
        source_law_key="generic001",
        locator=locator,
        kind=kind,
        depth=depth,
        text=text,
        temporal=Temporal(valid_from=valid_from, valid_to=valid_to),
        source=_synthetic_source(),
        parent_id=parent_id,
    )


def test_new_provision_is_rejected_fail_closed(tmp_path) -> None:
    """`docs/known-limitations.md` §1 claims `NewProvision` fails closed, not flattened.

    If this stops raising, the reviewed nested-hierarchy contract this
    document says is still missing has been added, and the limitation
    should be removed or rewritten.
    """
    body = (
        "<SupplProvision><AmendProvision><AmendProvisionSentence><NewProvision>"
        "<Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>x</ParagraphSentence></Paragraph></Article>"
        "</NewProvision></AmendProvisionSentence></AmendProvision></SupplProvision>"
    )
    path = tmp_path / "law.xml"
    path.write_text(_minimal_law(body), encoding="utf-8")
    with pytest.raises(AdapterError, match="^EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision$"):
        egov_xml_adapter(path)


def test_empty_structural_node_keeps_empty_text(tmp_path) -> None:
    """`docs/known-limitations.md` §1 claims an empty structural node keeps `text == ""`.

    If this fails because `LegalNode` rejects an empty `text` again, or
    because the adapter backfills it with serialized XML, the "Empty
    structural nodes" bullet is stale.
    """
    body = (
        "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\">"
        "<ParagraphSentence>本文</ParagraphSentence>"
        "<TableStruct><Table><TableRow><TableColumn>a</TableColumn><TableColumn/></TableRow></Table></TableStruct>"
        "</Paragraph></Article></MainProvision>"
    )
    path = tmp_path / "law.xml"
    path.write_text(_minimal_law(body), encoding="utf-8")
    cells = [node.text for node in egov_xml_adapter(path).nodes if node.kind is NodeKind.CELL]
    assert cells == ["a", ""]


def test_generic_xml_and_html_adapters_do_not_use_defusedxml() -> None:
    """`docs/known-limitations.md` §2 claims the generic `xml`/`html` adapters are not hardened.

    Checked by module identity, not by grepping source text for the string
    "defusedxml": if `src/jlegal_okf/adapters.py` were changed to parse with
    `defusedxml.ElementTree` instead of the standard library, `adapters.ET`
    would no longer be the same module object as `xml.etree.ElementTree`,
    and this test would fail -- which is the point, since that would mean
    the limitation had been fixed and the document is stale.
    """
    assert adapters.ET is _StdElementTree
    assert "defusedxml" not in adapters.ET.__name__


def test_acquisition_receipt_rights_is_always_null_and_non_null_is_rejected(tmp_path) -> None:
    """`docs/known-limitations.md` §3 claims a receipt's `rights` is always null and a non-null value is rejected.

    This is enforced by `src/jlegal_okf/pipeline.py` `_egov_acquisition()`,
    which rejects with `ACQUISITION_CONFLICT` *any* caller-supplied
    acquisition field that disagrees with the adapter-derived facts -- not
    a check specific to `rights`. A control below (changing an unrelated
    field, `law_number`, while leaving `rights` at its adapter-derived
    `None`) triggers the identical code, confirming that. What makes the
    document's `rights`-specific claim true anyway is that the
    adapter-derived `rights` is hard-coded to `None`
    (`src/jlegal_okf/egov.py` `_base_source_metadata()`): there is no
    adapter-derived value a caller could match to assert a non-null
    `rights` and pass this check, so in practice a non-null `rights` is
    *always* rejected by this general mismatch guard. This test pins both
    halves: the general mechanism (isolation control) and the specific,
    always-rejected outcome for `rights` (target case), plus a positive
    control showing the unmodified, adapter-derived acquisition compiles.
    """
    law_path = tmp_path / "law.xml"
    law_path.write_text(
        _minimal_law(
            "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\">"
            "<ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"
        ),
        encoding="utf-8",
    )
    adaptation = egov_xml_adapter(law_path)
    base_acquisition = adaptation.source_metadata
    assert base_acquisition is not None
    assert base_acquisition["rights"] is None

    # Positive control: the adapter-derived acquisition, passed through
    # unmodified, compiles without error.
    compile_corpus(
        law_path,
        adapter="egov_xml",
        out_dir=tmp_path / "corpus_control",
        corpus_id="control",
        acquisition=dict(base_acquisition),
    )

    # Target: only `rights` is changed to a non-null value.
    rights_changed = dict(base_acquisition)
    rights_changed["rights"] = {
        "source_license": "CC0",
        "bundle_license": "CC0",
        "redistribution_allowed": True,
        "commercial_use_allowed": True,
    }
    with pytest.raises(ValidationError, match="^ACQUISITION_CONFLICT$"):
        compile_corpus(
            law_path,
            adapter="egov_xml",
            out_dir=tmp_path / "corpus_rights",
            corpus_id="rights-changed",
            acquisition=rights_changed,
        )

    # Isolation control: `rights` is untouched (still the adapter-derived
    # `None`); only an unrelated field, `law_number`, is changed. This
    # raises the *same* code, showing the check above is not itself
    # `rights`-specific.
    law_number_changed = dict(base_acquisition)
    law_number_changed["law_number"] = "令和二年法律第一号"
    with pytest.raises(ValidationError, match="^ACQUISITION_CONFLICT$"):
        compile_corpus(
            law_path,
            adapter="egov_xml",
            out_dir=tmp_path / "corpus_law_number",
            corpus_id="law-number-changed",
            acquisition=law_number_changed,
        )


def test_egov_xml_nodes_only_populate_promulgated_and_export_okf_rejects_generic_adapter_corpus(tmp_path) -> None:
    """`docs/known-limitations.md` §4 claims `egov_xml` populates only `Temporal.promulgated`.

    Also fixes the related §3/§4 claim that `export-okf` rejects a corpus
    built by a generic adapter, so a caller-supplied Temporal claim never
    reaches a public bundle -- the two are tested together because the
    second claim is what makes the first one matter for the exported
    profile, not just for the adapter's own output.
    """
    law_path = tmp_path / "law.xml"
    law_path.write_text(
        _minimal_law(
            "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\">"
            "<ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"
        ),
        encoding="utf-8",
    )
    nodes = egov_xml_adapter(law_path).nodes
    assert nodes
    for node in nodes:
        assert node.temporal.valid_from is None
        assert node.temporal.valid_to is None
        assert node.temporal.repealed is None
    assert nodes[0].temporal.promulgated is not None

    generic_path = tmp_path / "law.json"
    generic_path.write_text(
        (
            '{"jurisdiction": "Synthetic", "authority": "LAW", "source_law_key": "generic001", '
            '"nodes": [{"locator": "root", "kind": "law", "text": "root text", '
            '"temporal": {"valid_from": "2020-01-01", "valid_to": "2030-01-01"}}]}'
        ),
        encoding="utf-8",
    )
    corpus_dir = tmp_path / "generic_corpus"
    compile_corpus(generic_path, adapter="json", out_dir=corpus_dir, corpus_id="generic")
    with pytest.raises(LegalOKFError, match="^JLEGAL_OKF_ADAPTER$"):
        export_okf(
            corpus_dir / "corpus.jsonl",
            corpus_dir / "manifest.json",
            tmp_path / "bundle",
            source=generic_path,
        )


def test_temporal_overlap_and_semantic_identity_drift_are_vacuous_and_parent_temporal_is_active() -> None:
    """`docs/known-limitations.md` §4 claims `TEMPORAL_OVERLAP`/`SEMANTIC_IDENTITY_DRIFT` are dormant on a
    single-snapshot corpus while `PARENT_TEMPORAL` is fully active.

    Builds one synthetic single-version parent/child pair with a validity
    window mismatch (active check) and confirms the two dormant checks
    never fire on it, then builds a second, explicitly multi-version
    corpus sharing one `node_id` to confirm `TEMPORAL_OVERLAP` is not
    permanently broken -- only vacuous when there is exactly one version of
    each node, which is what every current adapter run produces.
    """
    root = _synthetic_node("/law/root", valid_from="2020-01-01", valid_to="2021-01-01")
    child = _synthetic_node(
        "/law/root/a1",
        kind=NodeKind.ARTICLE,
        depth=1,
        parent_id=root.node_id,
        valid_from="2021-01-01",
    )
    single_snapshot_codes = {diagnostic.code for diagnostic in collect_diagnostics([root, child])}
    assert single_snapshot_codes == {"PARENT_TEMPORAL"}

    v1 = _synthetic_node(
        "/law/root/a1", kind=NodeKind.ARTICLE, depth=1, parent_id=root.node_id,
        text="v1", valid_from="2020-01-01", valid_to="2021-06-01",
    )
    v2 = _synthetic_node(
        "/law/root/a1", kind=NodeKind.ARTICLE, depth=1, parent_id=root.node_id,
        text="v2", valid_from="2021-01-01", valid_to="2022-01-01",
    )
    assert v1.node_id == v2.node_id
    multi_version_codes = {diagnostic.code for diagnostic in collect_diagnostics([root, v1, v2])}
    assert "TEMPORAL_OVERLAP" in multi_version_codes
