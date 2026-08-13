"""Adapted public-core regression contracts using invented temporary data only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import httpx

from jlegal_okf.adapters import default_registry
from jlegal_okf.cli import main
from jlegal_okf.egov import egov_xml_adapter, fetch_egov_xml, write_acquisition_receipt
from jlegal_okf.errors import AdapterError, JLegalError, ValidationError
from jlegal_okf.legal_okf import LegalOKFError, _bundle_manifest, export_okf, validate_okf
from jlegal_okf.model import LegalNode, NodeKind, SourceRef, Temporal, canonical_json, canonical_jsonl, law_identifier, node_identifier, semantic_locator, version_identifier
from jlegal_okf.pipeline import CanonicalArtifacts, canonical_crosswalk_jsonl, canonical_projection_jsonl, compile_adaptation, compile_corpus, make_projection, read_jsonl, verify_canonical_artifacts, verify_manifest
from jlegal_okf.validation import collect_diagnostics


def _json_source(path: Path, *, siblings: bool = False) -> Path:
    children = [{"locator": "article", "kind": "article", "ordinal": 1, "text": "Invented provision"}]
    if siblings:
        children.append({"locator": "article-again", "kind": "article", "ordinal": 1, "text": "Collision"})
    value = {"jurisdiction": "Example", "authority": "Test", "source_law_key": "invented-source", "nodes": [{"locator": "root", "kind": "law", "text": "Invented law", "children": children}]}
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _compiled_json(tmp_path: Path) -> dict:
    return compile_corpus(_json_source(tmp_path / "source.json"), adapter="json", out_dir=tmp_path / "corpus", corpus_id="invented")


def _rehash_options(manifest: dict) -> None:
    options = {key: manifest[key] for key in ("adapter", "adapter_version", "canonicalization", "hierarchy_status", "inputs", "required_input_roles", "build_recipe")}
    manifest["build_options_sha256"] = hashlib.sha256(canonical_json(options)).hexdigest()


def _minimal_law(body: str, *, date_value: str | None = None) -> str:
    envelope = "" if date_value is None else f"<law_info><law_id>InventedLaw001</law_id><promulgation_date>{date_value}</promulgation_date></law_info>"
    return f"<law_data_response>{envelope}<law_full_text><Law LawId=\"InventedLaw001\" LawType=\"Act\" Era=\"Reiwa\" Year=\"2\" PromulgateMonth=\"4\" PromulgateDay=\"1\"><LawBody><LawTitle>架空検証法</LawTitle>{body}</LawBody></Law></law_full_text></law_data_response>"


def test_ids_versions_and_diagnostics_are_stable() -> None:
    source = SourceRef("file:///synthetic.xml", hashlib.sha256(b"synthetic").hexdigest(), "fixture", "invented")
    root = LegalNode("Example", "Act", None, "invented", "/law/root", NodeKind.LAW, 0, "Invented", Temporal(), source)
    changed = replace(root, heading="Heading")
    assert root.law_id.startswith("law_") and root.node_id == changed.node_id and root.version_id != changed.version_id
    assert law_identifier("a|b", "c", "1", None) != law_identifier("a", "b|c", "1", None)
    assert node_identifier("law_a|b", "c") != node_identifier("law_a", "b|c")
    assert version_identifier("node", Temporal(), "a|b", "c") != version_identifier("node", Temporal(), "a", "b|c")
    assert "ROOT_KIND" in {item.code for item in collect_diagnostics([replace(root, kind=NodeKind.ARTICLE)])}


def test_temporal_parent_and_strict_source_contracts() -> None:
    source = SourceRef("file:///synthetic.xml", hashlib.sha256(b"synthetic").hexdigest(), "fixture")
    root = LegalNode("Example", "Act", None, "invented", "/law/root", NodeKind.LAW, 0, "Invented", Temporal("2020-01-01", "2021-01-01"), source)
    child = LegalNode("Example", "Act", None, "invented", "/law/root/article/article-1", NodeKind.ARTICLE, 1, "Later", Temporal("2021-01-01"), source, root.node_id, 1)
    assert "PARENT_TEMPORAL" in {item.code for item in collect_diagnostics([root, child])}
    with pytest.raises(ValueError, match="SOURCE_SHA256"):
        SourceRef("file:///bad", "not-a-hash", "fixture")


def test_json_sibling_semantic_locator_collision_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="ADAPTER_SIBLING_COLLISION"):
        default_registry().adapt(_json_source(tmp_path / "collision.json", siblings=True), name="json")


def test_generic_adapter_mapping_contracts_and_xhtml_requirement(tmp_path: Path) -> None:
    xml = tmp_path / "source.xml"
    xml.write_text("<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
    with pytest.raises(AdapterError, match="MAPPING_REQUIRED"):
        default_registry().adapt(xml, name="xml")
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    assert default_registry().adapt(xml, name="xml", mapping=mapping).nodes[0].kind is NodeKind.LAW
    invalid_html = tmp_path / "invalid.html"; invalid_html.write_text("<p>")
    with pytest.raises(AdapterError, match="XHTML_REQUIRED"):
        default_registry().adapt(invalid_html, name="html", mapping=mapping)


def test_manifest_input_syntax_and_uri_sha256_consistency_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.xml"
    source.write_text("<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    result = compile_corpus(source, adapter="xml", mapping=mapping, out_dir=tmp_path / "corpus", corpus_id="xml")
    manifest_path = Path(result["manifest"])
    original = json.loads(manifest_path.read_text())
    invalid = {**original, "inputs": [{**item, "uri": "https://example.invalid/a"} if item["role"] == "source" else item for item in original["inputs"]]}
    _rehash_options(invalid); manifest_path.write_text(json.dumps(invalid))
    with pytest.raises(JLegalError, match="MANIFEST_INPUT_SYNTAX"):
        verify_manifest(result["corpus"], manifest_path)
    # source.uri is content-addressed (jlegal:source:sha256:<hex>), so its
    # embedded hex and the declared sha256 field must agree; a forged sha256
    # that keeps the real uri is rejected even though the uri itself is
    # well-formed and unique in the manifest.
    mismatched = {**original, "inputs": [{**item, "sha256": "a" * 64} if item["role"] == "source" else item for item in original["inputs"]]}
    _rehash_options(mismatched); manifest_path.write_text(json.dumps(mismatched))
    with pytest.raises(JLegalError, match="MANIFEST_INPUT_SYNTAX"):
        verify_manifest(result["corpus"], manifest_path)


def test_manifest_input_order_is_rejected_and_replay_ignores_external_mapping_bytes(tmp_path: Path) -> None:
    """The mapping content replay verifies is build_recipe["mapping"], not the mapping file's bytes.

    verify_inputs replay never re-reads the external mapping file that the
    (content-addressed) mapping uri names; it only re-verifies the mapping
    already embedded in build_recipe, which build_options_sha256 covers.
    Editing the external file after compile is therefore not a tamper this
    profile can detect from the manifest alone — see CHANGELOG Known
    limitations.
    """
    source = tmp_path / "source.xml"; source.write_text("<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
    mapping_file = tmp_path / "mapping.yaml"; mapping_file.write_text("row: x\nfields:\n  jurisdiction: j\n  authority: a\n  source_law_key: s\n  locator: l\n  kind: k\n  depth: {path: d, type: int}\n  text: t\n")
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    result = compile_corpus(source, adapter="xml", mapping=mapping, mapping_path=mapping_file, out_dir=tmp_path / "corpus", corpus_id="xml")
    manifest_path = Path(result["manifest"]); original = json.loads(manifest_path.read_text())
    ordered = {**original, "inputs": list(reversed(original["inputs"]))}
    _rehash_options(ordered); manifest_path.write_text(json.dumps(ordered))
    with pytest.raises(JLegalError, match="MANIFEST_INPUT_ROLES"):
        verify_manifest(result["corpus"], manifest_path)
    # Mutate the external mapping file itself; replay never reads it back.
    manifest_path.write_text(json.dumps(original)); mapping_file.write_text(mapping_file.read_text() + "# changed\n")
    assert verify_manifest(result["corpus"], manifest_path, verify_inputs=True, source=source)["adapter"] == "xml"


def test_compile_is_deterministic_and_refuses_existing_output(tmp_path: Path) -> None:
    source = _json_source(tmp_path / "source.json")
    first = compile_corpus(source, adapter="json", out_dir=tmp_path / "first", corpus_id="invented")
    second = compile_corpus(source, adapter="json", out_dir=tmp_path / "second", corpus_id="invented")
    assert Path(first["corpus"]).read_bytes() == Path(second["corpus"]).read_bytes()
    with pytest.raises(JLegalError, match="OUTPUT_EXISTS_REFUSED"):
        compile_corpus(source, adapter="json", out_dir=tmp_path / "first", corpus_id="invented")


def test_generic_adaptation_compile_is_reproducible_and_canonical_artifacts_are_typed(tmp_path: Path) -> None:
    source = _json_source(tmp_path / "source.json")
    adaptation = replace(default_registry().adapt(source, name="json"), adapter="synthetic_adapter")
    first = compile_adaptation(adaptation, corpus_id="invented", out_dir=tmp_path / "first")
    second = compile_adaptation(adaptation, corpus_id="invented", out_dir=tmp_path / "second")
    for name in ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl", "manifest.json"):
        assert (Path(first["out_dir"]) / name).read_bytes() == (Path(second["out_dir"]) / name).read_bytes()

    artifacts = verify_canonical_artifacts(first["corpus"])
    assert isinstance(artifacts, CanonicalArtifacts)
    assert tuple(node.node_id for node in artifacts.nodes) == tuple(node.node_id for node in adaptation.nodes)
    assert all("build_provenance_sha256" in dict(node.attributes) for node in artifacts.nodes)
    assert artifacts.corpus_bytes == Path(first["corpus"]).read_bytes()
    assert artifacts.crosswalk_bytes == Path(first["crosswalk"]).read_bytes()
    assert artifacts.projection_bytes == Path(first["projection"]).read_bytes()


def test_canonical_artifact_verification_detects_noncanonical_and_invalid_projection(tmp_path: Path) -> None:
    result = _compiled_json(tmp_path)
    corpus = Path(result["corpus"])
    corpus.write_bytes(corpus.read_bytes() + b"\n")
    with pytest.raises(JLegalError, match="ARTIFACT_NOT_CANONICAL"):
        verify_canonical_artifacts(corpus)

    second_root = tmp_path / "projection"
    second_root.mkdir()
    result = _compiled_json(second_root)
    projection = Path(result["projection"])
    projection.write_bytes(b"")
    with pytest.raises(JLegalError, match="PROJECTION_DERIVATION_MISMATCH"):
        verify_canonical_artifacts(result["corpus"])


def test_projection_duplicate_diagnostic_fires_for_a_directly_authored_bundle(tmp_path: Path) -> None:
    """PROJECTION_DUPLICATE (pipeline.py's verify_canonical_artifacts dedup check
    on (projection_id, projection_version)) guards a canonical bundle written
    directly to disk. compile_adaptation/compile_corpus can never produce this:
    they call validate_corpus, whose DUPLICATE_VERSION check rejects a
    duplicated node before any artifact is written. So this test authors the
    three canonical files by hand -- via the same public LegalNode/
    canonical_jsonl/make_projection helpers the pipeline itself uses, no
    invariant bypassed -- to reach the one caller that can still see a
    duplicate: verify_canonical_artifacts reading a bundle it did not compile.
    """
    source = SourceRef("file:///synthetic-duplicate.xml", hashlib.sha256(b"synthetic-duplicate").hexdigest(), "fixture")
    node = LegalNode("Example", "Act", None, "invented-duplicate", "/law/root/article/article-1", NodeKind.ARTICLE, 0, "Invented duplicate text", Temporal(), source)
    nodes = (node, node)
    corpus_bytes = canonical_jsonl(nodes)
    crosswalk_bytes = canonical_crosswalk_jsonl(())
    projection = make_projection(nodes)
    assert len({(item.projection_id, item.projection_version) for item in projection}) == 1
    assert len(projection) == 2
    projection_bytes = canonical_projection_jsonl(projection)
    (tmp_path / "corpus.jsonl").write_bytes(corpus_bytes)
    (tmp_path / "crosswalk.jsonl").write_bytes(crosswalk_bytes)
    (tmp_path / "projection.jsonl").write_bytes(projection_bytes)
    with pytest.raises(JLegalError, match="PROJECTION_DUPLICATE"):
        verify_canonical_artifacts(tmp_path / "corpus.jsonl")


def test_verify_inputs_replay_detects_tampered_recipe_mapping(tmp_path: Path) -> None:
    """A mapping tampered in build_recipe (not on disk: this uses an inline mapping) breaks replay.

    verify_inputs never reads a mapping file back from disk (see
    test_manifest_input_order_is_rejected_and_replay_ignores_external_mapping_bytes);
    what it can and does catch is a manifest whose build_recipe.mapping no
    longer reproduces the declared corpus when replayed.
    """
    source = tmp_path / "source.xml"
    source.write_text("<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    result = compile_corpus(source, adapter="xml", mapping=mapping, out_dir=tmp_path / "corpus", corpus_id="xml")
    assert verify_manifest(result["corpus"], result["manifest"], verify_inputs=True, source=source)["adapter"] == "xml"
    manifest_path = Path(result["manifest"])
    hostile = json.loads(manifest_path.read_text())
    hostile["build_recipe"]["mapping"]["row"] = "missing"
    mapping_input = next(item for item in hostile["inputs"] if item["role"] == "mapping")
    mapping_input["sha256"] = hashlib.sha256(canonical_json(hostile["build_recipe"]["mapping"])).hexdigest()
    _rehash_options(hostile); manifest_path.write_text(json.dumps(hostile))
    with pytest.raises(JLegalError, match="MANIFEST_REBUILD_CORPUS"):
        verify_manifest(result["corpus"], manifest_path, verify_inputs=True, source=source)


def test_compile_is_path_independent(tmp_path: Path) -> None:
    """Compiling the same bytes from two different directories must reach byte-identical artifacts."""
    xml_text = "<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>"
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"
    first_dir.mkdir(); second_dir.mkdir()
    first_source = first_dir / "source.xml"; first_source.write_text(xml_text)
    second_source = second_dir / "source.xml"; second_source.write_text(xml_text)
    first = compile_corpus(first_source, adapter="xml", mapping=mapping, out_dir=first_dir / "corpus", corpus_id="xml")
    second = compile_corpus(second_source, adapter="xml", mapping=mapping, out_dir=second_dir / "corpus", corpus_id="xml")
    # Byte-identical manifest.json already implies matching corpus_sha256,
    # projection_sha256, and build_options_sha256; byte-identical corpus.jsonl
    # already implies matching version_id order and attributes.build_provenance_sha256.
    for name in ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl", "manifest.json"):
        assert (Path(first["out_dir"]) / name).read_bytes() == (Path(second["out_dir"]) / name).read_bytes()


def test_compiled_artifacts_never_leak_local_paths(tmp_path: Path) -> None:
    # pytest's tmp_path already lives outside /home in most environments, so
    # a bare "/home/" substring check alone would silently test nothing here;
    # str(tmp_path) itself is checked so the assertion is meaningful
    # regardless of where the test happens to run.
    xml_source = tmp_path / "source.xml"
    xml_source.write_text("<r><x><j>Example</j><a>Act</a><s>source</s><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
    mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "source_law_key": "s", "locator": "l", "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    xml_result = compile_corpus(xml_source, adapter="xml", mapping=mapping, out_dir=tmp_path / "xml_corpus", corpus_id="xml")
    # egov_xml is what this profile actually ships (compile --adapter egov_xml).
    egov_source = tmp_path / "law.xml"
    egov_source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    egov_result = compile_corpus(egov_source, adapter="egov_xml", out_dir=tmp_path / "egov_corpus", corpus_id="egov")
    forbidden = ("file://", "/home/", str(tmp_path), str(xml_source.resolve()), str(egov_source.resolve()))
    for result in (xml_result, egov_result):
        for name in ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl", "manifest.json"):
            text = (Path(result["out_dir"]) / name).read_text(encoding="utf-8")
            assert not any(needle in text for needle in forbidden)


def test_source_uri_is_content_addressed(tmp_path: Path) -> None:
    source = _json_source(tmp_path / "source.json")
    result = compile_corpus(source, adapter="json", out_dir=tmp_path / "corpus", corpus_id="invented")
    nodes = [json.loads(line) for line in Path(result["corpus"]).read_text(encoding="utf-8").splitlines()]
    assert nodes
    for node in nodes:
        assert node["source"]["uri"] == f"jlegal:source:sha256:{node['source']['sha256']}"


def test_replay_requires_and_verifies_explicit_source(tmp_path: Path) -> None:
    source = _json_source(tmp_path / "source.json")
    result = compile_corpus(source, adapter="json", out_dir=tmp_path / "corpus", corpus_id="invented")
    with pytest.raises(JLegalError, match="MANIFEST_REPLAY_SOURCE_REQUIRED"):
        verify_manifest(result["corpus"], result["manifest"], verify_inputs=True)
    other = _json_source(tmp_path / "other.json", siblings=True)
    with pytest.raises(JLegalError, match="MANIFEST_REPLAY_SOURCE_MISMATCH"):
        verify_manifest(result["corpus"], result["manifest"], verify_inputs=True, source=other)
    assert verify_manifest(result["corpus"], result["manifest"], verify_inputs=True, source=source)["adapter"] == "json"


def test_egov_hierarchy_temporal_and_fail_closed_contracts(tmp_path: Path) -> None:
    body = "<MainProvision><Article Num=\"3-2\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision><SupplProvision><Chapter Num=\"1\"><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>附則</ParagraphSentence></Paragraph></Article></Chapter></SupplProvision>"
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body, date_value="2020-04-01"), encoding="utf-8")
    nodes = egov_xml_adapter(path).nodes
    article = next(node for node in nodes if node.kind is NodeKind.ARTICLE and node.ordinal == 3)
    assert article.branch == (2,) and {node.temporal.promulgated for node in nodes} == {"2020-04-01"}
    conflict = tmp_path / "conflict.xml"; conflict.write_text(_minimal_law(body, date_value="2020-04-02"), encoding="utf-8")
    with pytest.raises(AdapterError, match="PROMULGATION_CONFLICT"):
        egov_xml_adapter(conflict)
    unsupported = tmp_path / "unsupported.xml"; unsupported.write_text(_minimal_law("<MainProvision><NewProvision/></MainProvision>"), encoding="utf-8")
    with pytest.raises(AdapterError, match="UNSUPPORTED_STRUCTURE:NewProvision"):
        egov_xml_adapter(unsupported)


def test_egov_kanji_numeral_ordinal_and_branch_fallback(tmp_path: Path) -> None:
    """rule JLEGAL-NORM-2/3 (docs/normalization-rules.md): kanji-numeral title fallback when Num is absent."""
    body = "<MainProvision><Article><ArticleTitle>第十二条の二</ArticleTitle><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    nodes = egov_xml_adapter(path).nodes
    article = next(node for node in nodes if node.kind is NodeKind.ARTICLE)
    assert (article.ordinal, article.branch) == (12, (2,))


def _appdx_table_xml(num: str = "1") -> str:
    return (
        f'<AppdxTable Num="{num}"><AppdxTableTitle>別表</AppdxTableTitle>'
        "<TableStruct><Table><TableRow><TableColumn><Sentence>架空</Sentence>"
        "</TableColumn></TableRow></Table></TableStruct></AppdxTable>"
    )


def _appdx_style_xml(num: str = "1") -> str:
    return (
        f'<AppdxStyle Num="{num}"><AppdxStyleTitle>様式</AppdxStyleTitle>'
        "<StyleStruct><Style>様式の本文。</Style></StyleStruct></AppdxStyle>"
    )


def test_semantic_locator_source_tag_produces_exact_appendix_locator() -> None:
    """rule JLEGAL-NORM-5 (docs/normalization-rules.md): source_tag produces the exact tag-qualified appendix locator."""
    assert semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="AppdxTable") == "/law/root/appendix/appendix-appdxtable-1"
    assert semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="AppdxStyle") == "/law/root/appendix/appendix-appdxstyle-1"


def test_semantic_locator_without_source_tag_keeps_legacy_ordinal_form() -> None:
    """rule JLEGAL-NORM-5: source_tag=None (the default, and every non-appendix call site) keeps the {kind.value}-{ordinal} form."""
    assert semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "ignored", ordinal=3, branch=(2,)) == "/law/root/article/article-3-2"
    assert semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1) == "/law/root/appendix/appendix-1"


@pytest.mark.parametrize("source_tag", ["", "   ", "　"])
def test_semantic_locator_source_tag_fail_closed_on_empty_or_blank(source_tag: str) -> None:
    """rule JLEGAL-NORM-5: a source_tag that normalizes to empty (including all-whitespace) fails closed, never silently falls back."""
    with pytest.raises(ValueError, match="LOCATOR_SOURCE_TAG_REQUIRED"):
        semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag=source_tag)


def test_semantic_locator_source_tag_is_nfkc_lowercased_and_sanitized() -> None:
    """rule JLEGAL-NORM-5: source_tag reuses JLEGAL-NORM-1 (NFKC + lowercase + whitespace-collapse) then JLEGAL-NORM-4's sanitize."""
    assert semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="Ａｐｐｄｘ Ｔａｂｌｅ") == "/law/root/appendix/appendix-appdx-table-1"


def test_source_tag_does_not_affect_non_appendix_compiled_locators(tmp_path: Path) -> None:
    """rule JLEGAL-NORM-5: the source_tag branch is reached only for NodeKind.APPENDIX; Article/Paragraph locators are unchanged."""
    body = "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"
    path = tmp_path / "law.xml"
    path.write_text(_minimal_law(body), encoding="utf-8")
    nodes = egov_xml_adapter(path).nodes
    article = next(node for node in nodes if node.kind is NodeKind.ARTICLE)
    paragraph = next(node for node in nodes if node.kind is NodeKind.PARAGRAPH)
    assert article.locator.endswith("/article/article-1")
    assert paragraph.locator.endswith("/article/article-1/paragraph/paragraph-1")
    assert "appendix" not in article.locator and "appendix" not in paragraph.locator


def test_appendix_sibling_order_does_not_change_locators_or_node_ids(tmp_path: Path) -> None:
    """rule JLEGAL-NORM-5: reordering AppdxTable/AppdxStyle siblings must not change either appendix's locator or node_id."""
    body = "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"
    table_first = tmp_path / "table_first.xml"
    table_first.write_text(_minimal_law(body + _appdx_table_xml() + _appdx_style_xml()), encoding="utf-8")
    style_first = tmp_path / "style_first.xml"
    style_first.write_text(_minimal_law(body + _appdx_style_xml() + _appdx_table_xml()), encoding="utf-8")
    table_first_appendices = {(node.locator, node.node_id) for node in egov_xml_adapter(table_first).nodes if node.kind is NodeKind.APPENDIX}
    style_first_appendices = {(node.locator, node.node_id) for node in egov_xml_adapter(style_first).nodes if node.kind is NodeKind.APPENDIX}
    assert len(table_first_appendices) == 2
    assert table_first_appendices == style_first_appendices


####################################################################
# Preservation levels (item 8): byte preservation of the source XML and
# character-level preservation of extracted body text are two separate,
# separately-verified contracts (see the profile's "Preservation levels").
####################################################################


def test_byte_preservation_embeds_exact_source_bytes(tmp_path: Path) -> None:
    """Byte preservation (source layer): references/source.xml is exactly the input bytes."""
    body = "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>　全角空白で挟まれた本文　</ParagraphSentence></Paragraph></Article></MainProvision>"
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law(body), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="byte-preservation")
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=source)["bundle"])
    embedded = bundle / "references" / "source.xml"
    assert embedded.read_bytes() == source.read_bytes()


def test_character_level_preservation_keeps_ideographic_and_ascii_whitespace(tmp_path: Path) -> None:
    """A <Sentence> value bounded by U+3000 on both sides, with an interior ASCII space, survives verbatim."""
    exact = "　full width bounded and ascii space　"
    body = f"<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence><Sentence Num=\"1\">{exact}</Sentence></ParagraphSentence></Paragraph></Article></MainProvision>"
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    nodes = egov_xml_adapter(path).nodes
    ancestor_kinds = {NodeKind.LAW, NodeKind.MAIN_PROVISION, NodeKind.ARTICLE, NodeKind.PARAGRAPH}
    assert ancestor_kinds <= {node.kind for node in nodes}
    for node in nodes:
        if node.kind in ancestor_kinds:
            assert exact in node.text
    paragraph = next(node for node in nodes if node.kind is NodeKind.PARAGRAPH)
    assert paragraph.text == exact


def test_formatting_independence_between_pretty_and_compact_xml(tmp_path: Path) -> None:
    """Same content, reformatted: text/heading/label/version_id must not depend on layout.

    The Article carries both an ArticleCaption (-> heading) and an
    ArticleTitle (-> label) so the label comparison below is not vacuous
    (label is None on every node of a fixture with no *Title element).
    """
    compact = (
        "<law_data_response><law_full_text>"
        "<Law LawId=\"InventedLaw001\" LawType=\"Act\" Era=\"Reiwa\" Year=\"2\" PromulgateMonth=\"4\" PromulgateDay=\"1\">"
        "<LawBody><LawTitle>架空検証法</LawTitle>"
        "<MainProvision><Article Num=\"1\"><ArticleCaption>（目的）</ArticleCaption><ArticleTitle>第一条</ArticleTitle>"
        "<Paragraph Num=\"1\"><ParagraphSentence>本文です。</ParagraphSentence></Paragraph>"
        "</Article></MainProvision></LawBody></Law>"
        "</law_full_text></law_data_response>"
    )
    pretty = (
        "<law_data_response>\n  <law_full_text>\n"
        "    <Law LawId=\"InventedLaw001\" LawType=\"Act\" Era=\"Reiwa\" Year=\"2\" PromulgateMonth=\"4\" PromulgateDay=\"1\">\n"
        "      <LawBody>\n        <LawTitle>架空検証法</LawTitle>\n"
        "        <MainProvision>\n          <Article Num=\"1\">\n            <ArticleCaption>（目的）</ArticleCaption>\n"
        "            <ArticleTitle>第一条</ArticleTitle>\n"
        "            <Paragraph Num=\"1\">\n              <ParagraphSentence>本文です。</ParagraphSentence>\n            </Paragraph>\n"
        "          </Article>\n        </MainProvision>\n      </LawBody>\n    </Law>\n"
        "  </law_full_text>\n</law_data_response>\n"
    )
    compact_path = tmp_path / "compact.xml"; compact_path.write_text(compact, encoding="utf-8")
    pretty_path = tmp_path / "pretty.xml"; pretty_path.write_text(pretty, encoding="utf-8")
    compact_nodes = egov_xml_adapter(compact_path).nodes
    pretty_nodes = egov_xml_adapter(pretty_path).nodes
    assert len(compact_nodes) == len(pretty_nodes) == 4
    article = next(n for n in compact_nodes if n.kind is NodeKind.ARTICLE)
    assert article.label == "第一条"
    for a, b in zip(compact_nodes, pretty_nodes):
        assert a.text == b.text
        assert a.heading == b.heading
        assert a.label == b.label
        assert a.version_id == b.version_id


def test_display_fields_are_trimmed_but_text_is_preserved(tmp_path: Path) -> None:
    """The same padding is trimmed in heading/label (display fields) but kept verbatim in text."""
    padded = "　　padded　　"
    body = (
        f"<MainProvision><Article Num=\"1\"><ArticleCaption>{padded}</ArticleCaption>"
        f"<ArticleTitle>{padded}</ArticleTitle>"
        f"<Paragraph Num=\"1\"><ParagraphSentence>{padded}</ParagraphSentence></Paragraph></Article></MainProvision>"
    )
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    nodes = egov_xml_adapter(path).nodes
    article = next(node for node in nodes if node.kind is NodeKind.ARTICLE)
    paragraph = next(node for node in nodes if node.kind is NodeKind.PARAGRAPH)
    assert article.heading == "padded"
    assert article.label == "padded"
    assert article.text == padded * 3
    assert paragraph.text == padded


def test_xml_whitespace_elision_never_destroys_unicode_whitespace_between_children(tmp_path: Path) -> None:
    """A U+3000 between two <Sentence> children of a <ParagraphSentence> is source text, not XML formatting.

    The structural formatting-whitespace elision in _render_text must only
    drop XML 1.0 S-production whitespace (space/tab/CR/LF). It must never use
    Python's Unicode-aware str.strip(), which would also treat U+3000
    IDEOGRAPHIC SPACE as formatting and destroy it, even though
    ParagraphSentence is a structural tag here (it has two child elements).
    """
    body = (
        "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\">"
        "<ParagraphSentence><Sentence Num=\"1\">A</Sentence>　<Sentence Num=\"2\">B</Sentence></ParagraphSentence>"
        "</Paragraph></Article></MainProvision>"
    )
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    paragraph = next(n for n in egov_xml_adapter(path).nodes if n.kind is NodeKind.PARAGRAPH)
    assert paragraph.text == "A　B"


def test_subitem_sentence_numbered_and_unnumbered_spellings_produce_identical_text(tmp_path: Path) -> None:
    """SubitemSentence and Subitem1Sentence are the same element-only wrapper shape; spelling must not change text.

    The wrapper carries a child element on purpose: a childless wrapper is a
    leaf, so formatting elision never runs and both spellings would agree
    whatever the structural set says. Each wrapper sits inside the subitem
    element it belongs to, so the shape stays close to the e-Gov content
    model rather than putting a subitem wrapper directly under an item.
    """
    def item_body(subitem_tag: str) -> str:
        return (
            "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence>"
            "<Item Num=\"1\">\n"
            "  <ItemTitle>一</ItemTitle>\n"
            "  <ItemSentence><Sentence>号の本文</Sentence></ItemSentence>\n"
            f"  <{subitem_tag} Num=\"1\">\n"
            f"    <{subitem_tag}Title>イ</{subitem_tag}Title>\n"
            f"    <{subitem_tag}Sentence>\n"
            "      <Sentence>子号の本文</Sentence>\n"
            f"    </{subitem_tag}Sentence>\n"
            f"  </{subitem_tag}>\n"
            "</Item></Paragraph></Article></MainProvision>"
        )
    unnumbered_path = tmp_path / "unnumbered.xml"
    unnumbered_path.write_text(_minimal_law(item_body("Subitem")), encoding="utf-8")
    numbered_path = tmp_path / "numbered.xml"
    numbered_path.write_text(_minimal_law(item_body("Subitem1")), encoding="utf-8")
    unnumbered = next(n for n in egov_xml_adapter(unnumbered_path).nodes if n.kind is NodeKind.SUBITEM)
    numbered = next(n for n in egov_xml_adapter(numbered_path).nodes if n.kind is NodeKind.SUBITEM)
    assert unnumbered.text == numbered.text == "イ子号の本文"


def test_empty_table_cell_falls_back_to_element_markup_without_crashing(tmp_path: Path) -> None:
    """A structural node with no character data of its own (an empty appendix-table cell) must not crash.

    This is the retained conflation documented in the profile's "Known
    limitation" note under "Preservation levels": the empty-text fallback
    embeds the element's own XML serialization as text rather than failing
    the model's NODE_TEXT_EMPTY invariant.
    """
    body = (
        "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence>"
        "<TableStruct><Table><TableRow><TableColumn>a</TableColumn><TableColumn/></TableRow></Table></TableStruct>"
        "</Paragraph></Article></MainProvision>"
    )
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    cells = [n.text for n in egov_xml_adapter(path).nodes if n.kind is NodeKind.CELL]
    assert cells == ["a", "<TableColumn></TableColumn>"]


def test_table_header_column_preserves_mixed_content_whitespace(tmp_path: Path) -> None:
    """TableHeaderColumn is mixed content in the e-Gov schema, so it must stay out of _STRUCTURAL_TAGS.

    Unlike TableColumn, TableHeaderColumn may carry text directly alongside
    inline markup, so eliding its own whitespace-only text/tail -- as every
    other canonical node tag does -- would lose meaningful source formatting.
    """
    body = (
        "<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence>"
        "<TableStruct><Table><TableHeaderRow><TableHeaderColumn>　<Ruby>漢<Rt>かん</Rt></Ruby>　</TableHeaderColumn>"
        "</TableHeaderRow></Table></TableStruct></Paragraph></Article></MainProvision>"
    )
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    header_cell = next(n for n in egov_xml_adapter(path).nodes if n.kind is NodeKind.CELL)
    assert header_cell.text.startswith("　") and header_cell.text.endswith("　")


def test_plain_text_display_fields_never_contain_inline_xml_markup(tmp_path: Path) -> None:
    """heading/label are character data only; an inline element like Ruby must not leak its XML markup into them.

    LegalNode.text does keep inline markup verbatim (JLEGAL-TEXT-PRESERVE-1);
    JLEGAL-DISPLAY-TRIM-1's _plain_text must not, matching the character-data-
    only behaviour of the element.itertext() call it replaced.
    """
    body = (
        "<MainProvision><Article Num=\"1\">"
        "<ArticleCaption>（<Ruby>目的<Rt>もくてき</Rt></Ruby>）</ArticleCaption>"
        "<Paragraph Num=\"1\"><ParagraphSentence>本文です。</ParagraphSentence></Paragraph>"
        "</Article></MainProvision>"
    )
    path = tmp_path / "law.xml"; path.write_text(_minimal_law(body), encoding="utf-8")
    article = next(n for n in egov_xml_adapter(path).nodes if n.kind is NodeKind.ARTICLE)
    assert article.heading == "（目的もくてき）"
    assert "<Ruby>" not in article.heading
    assert "<Ruby>" in article.text


def test_bare_egov_law_never_guesses_identity(tmp_path: Path) -> None:
    bare = tmp_path / "bare.xml"
    bare.write_text("<Law LawType=\"Act\"><LawBody><LawTitle>架空</LawTitle><MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision></LawBody></Law>")
    with pytest.raises(AdapterError, match="LAW_ID_REQUIRED"):
        egov_xml_adapter(bare)
    assert egov_xml_adapter(bare, {"law_id": "InventedLaw002"}).nodes[0].source.source_key == "InventedLaw002"


def test_fetch_helper_uses_v2_parameters_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>").encode()
    calls: list[tuple[str, dict]] = []
    response = httpx.Response(200, content=content, request=httpx.Request("GET", "https://laws.e-gov.go.jp/api/2/law_data/InventedLaw001?law_full_text_format=xml&response_format=xml&asof=2024-04-01"))
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: calls.append((url, kwargs)) or response)
    output = tmp_path / "fetched.xml"
    result = fetch_egov_xml("InventedLaw001", output, as_of="2024-04-01")
    assert output.read_bytes() == content and result.sha256 == hashlib.sha256(content).hexdigest()
    assert calls[0][1]["params"] == {"response_format": "xml", "law_full_text_format": "xml", "asof": "2024-04-01"}


def test_fetch_receipt_is_verified_and_propagated_to_okf_frontmatter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>").encode()
    response = httpx.Response(200, content=content, request=httpx.Request("GET", "https://laws.e-gov.go.jp/api/2/law_data/InventedLaw001?law_full_text_format=xml&response_format=xml&asof=2024-04-01"))
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: response)
    xml = tmp_path / "fetched.xml"
    receipt = tmp_path / "receipt.json"
    result = fetch_egov_xml("InventedLaw001", xml, as_of="2024-04-01")
    write_acquisition_receipt(result, receipt)
    acquisition = json.loads(receipt.read_text(encoding="utf-8"))
    compiled = compile_corpus(xml, adapter="egov_xml", acquisition=acquisition, out_dir=tmp_path / "corpus", corpus_id="invented")
    manifest = verify_manifest(compiled["corpus"], compiled["manifest"], verify_inputs=True, source=xml)
    assert manifest["schema"] == "jori-manifest/v5"
    assert manifest["acquisition"] == acquisition
    assert manifest["acquisition"]["source_url"].startswith("https://laws.e-gov.go.jp/api/2/law_data/")
    assert manifest["acquisition"]["retrieved_at"].endswith("Z")
    assert manifest["converted_at"].endswith("Z")
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=xml)["bundle"])
    assert (bundle / "references" / "source.xml").read_bytes() == xml.read_bytes()
    frontmatter = next((bundle / "source").glob("*.md")).read_text(encoding="utf-8").split("---\n", 2)[1]
    assert "source_authority: e-Gov 法令API Version 2" in frontmatter
    assert "rights: null" in frontmatter
    assert validate_okf(bundle)["valid"] is True
    forged = {**acquisition, "sha256": "0" * 64}
    with pytest.raises(ValidationError, match="ACQUISITION_CONFLICT"):
        compile_corpus(xml, adapter="egov_xml", acquisition=forged, out_dir=tmp_path / "forged", corpus_id="invented")


@pytest.mark.parametrize("field, value", [
    ("source_url", "https://laws.e-gov.go.jp/api/2/law_data/OtherLaw?law_full_text_format=xml&response_format=xml&asof=2024-04-01"),
    ("source_url", "https://laws.e-gov.go.jp/api/2/law_data/InventedLaw001?law_full_text_format=xml&response_format=json&asof=2024-04-01"),
    ("retrieved_at", "2024-04-01T00:00:00+00:00"),
    ("as_of", "2024-04-02"),
    ("requested_law_id", "OtherLaw"),
])
def test_acquisition_rejects_forged_retrieval_facts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
    content = _minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>").encode()
    response = httpx.Response(200, content=content, request=httpx.Request("GET", "https://laws.e-gov.go.jp/api/2/law_data/InventedLaw001?law_full_text_format=xml&response_format=xml&asof=2024-04-01"))
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: response)
    xml = tmp_path / "fetched.xml"
    receipt = tmp_path / "receipt.json"
    write_acquisition_receipt(fetch_egov_xml("InventedLaw001", xml, as_of="2024-04-01"), receipt)
    forged = json.loads(receipt.read_text(encoding="utf-8"))
    forged[field] = value
    with pytest.raises(ValidationError, match="ACQUISITION"):
        compile_corpus(xml, adapter="egov_xml", acquisition=forged, out_dir=tmp_path / "forged", corpus_id="invented")


def test_export_okf_requires_and_verifies_explicit_source(tmp_path: Path) -> None:
    source = tmp_path / "law.xml"; source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    with pytest.raises(JLegalError, match="JLEGAL_OKF_SOURCE_REQUIRED"):
        export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle")
    other = tmp_path / "other.xml"
    other.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>別の本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    with pytest.raises(JLegalError, match="JLEGAL_OKF_SOURCE_MISMATCH"):
        export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=other)
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=source)["bundle"])
    assert (bundle / "references" / "source.xml").read_bytes() == source.read_bytes()
    assert not (bundle / "references" / "source-reference.json").exists()
    assert validate_okf(bundle)["valid"] is True


def test_export_okf_source_gate_survives_a_forged_second_node_source(tmp_path: Path) -> None:
    """A corpus.jsonl forged to make one node claim a distinct source must not bypass --source.

    source_key is not part of version_id's payload and MANIFEST_NODE_PROVENANCE
    only binds (uri, sha256), so changing only a node's source_key produces a
    self-consistent, verify_manifest-passing corpus with two distinct
    (uri, sha256, adapter, source_key) node-source tuples. Whether export_okf
    treats this as a single-source corpus must come from the verified
    manifest's declared "source"-role inputs (always exactly one for
    egov_xml), never from that forgeable node-level set, or this reaches the
    hash-ledger branch and skips the --source requirement entirely.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    corpus_path = Path(compiled["corpus"])
    nodes = read_jsonl(corpus_path)
    # The root (kind == law) is never projected by make_projection, so this
    # needs no matching change to projection.jsonl.
    root = next(n for n in nodes if n.parent_id is None)
    forged_root = replace(root, source=replace(root.source, source_key=root.source.source_key + "-x"))
    corpus_path.write_bytes(canonical_jsonl(forged_root if n is root else n for n in nodes))
    manifest_path = Path(compiled["manifest"])
    manifest = json.loads(manifest_path.read_text())
    manifest["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    # The forged manifest is internally self-consistent, so a non-replaying
    # verify_manifest (what export_okf itself calls) still accepts it.
    assert verify_manifest(compiled["corpus"], compiled["manifest"])["adapter"] == "egov_xml"
    with pytest.raises(JLegalError, match="JLEGAL_OKF_SOURCE_REQUIRED"):
        export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle")


def test_manifest_node_provenance_rejects_mapping_uri_impersonation(tmp_path: Path) -> None:
    """A node must not be able to claim the mapping input's (uri, sha256) as its own provenance.

    This is the second bypass route noted alongside JLEGAL_OKF_SOURCE_REQUIRED:
    before restricting declared_sources to role == "source", a node forged to
    carry the mapping entry's (uri, sha256) still passed MANIFEST_NODE_PROVENANCE
    and would have inflated _source_reference's node-derived source count.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented", mapping={"law_id": "InventedLaw001"})
    manifest_path = Path(compiled["manifest"])
    manifest = json.loads(manifest_path.read_text())
    mapping_input = next(item for item in manifest["inputs"] if item["role"] == "mapping")
    corpus_path = Path(compiled["corpus"])
    nodes = read_jsonl(corpus_path)
    root = next(n for n in nodes if n.parent_id is None)
    forged_root = replace(root, source=replace(root.source, uri=mapping_input["uri"], sha256=mapping_input["sha256"]))
    corpus_path.write_bytes(canonical_jsonl(forged_root if n is root else n for n in nodes))
    manifest["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(JLegalError, match="MANIFEST_NODE_PROVENANCE"):
        verify_manifest(compiled["corpus"], compiled["manifest"])


def test_okf_tamper_and_profile_provenance_are_detected(tmp_path: Path) -> None:
    source = tmp_path / "law.xml"; source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=source)["bundle"])
    concept = next((bundle / "source").glob("*.md")); concept.write_text(concept.read_text().replace("  layer: source", "  layer: source\n  forged: true"), encoding="utf-8")
    manifest = _bundle_manifest(bundle, json.loads((bundle / "canonical" / "manifest.json").read_text())["corpus_sha256"], hashlib.sha256((bundle / "canonical" / "manifest.json").read_bytes()).hexdigest())
    (bundle / "manifest.json").write_bytes(canonical_json(manifest) + b"\n")
    with pytest.raises(JLegalError, match="SOURCE_EXTENSION"):
        validate_okf(bundle)


def test_okf_export_refuses_non_egov_corpus(tmp_path: Path) -> None:
    compiled = _compiled_json(tmp_path)
    with pytest.raises(JLegalError, match="JLEGAL_OKF_ADAPTER"):
        export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle")


def test_cli_exit_codes_are_stable(tmp_path: Path) -> None:
    assert main(["compile", "--adapter", "json", "--out-dir", str(tmp_path / "out")]) == 2
    assert main(["validate", "--corpus", str(tmp_path / "missing"), "--manifest", str(tmp_path / "manifest")]) == 3


@pytest.mark.parametrize("converted_at", ["NOT-A-TIMESTAMP", "2024-01-01T00:00:00+00:00", 12345, ""])
def test_compile_rejects_a_malformed_converted_at_before_writing_a_manifest(tmp_path: Path, converted_at) -> None:
    """converted_at must be validated at compile time, like acquisition already is.

    Before this fix, compile_adaptation accepted any value for converted_at
    and wrote it straight into manifest.json; the defect only surfaced
    later, when verify_manifest rejected the manifest that had already been
    staged to disk. This asserts the earlier, fail-closed rejection instead,
    and that no output directory is left behind by the refused compile.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    out_dir = tmp_path / "corpus"
    with pytest.raises(ValidationError, match="ACQUISITION_CONVERTED_AT"):
        compile_corpus(source, adapter="egov_xml", out_dir=out_dir, corpus_id="invented", converted_at=converted_at)
    assert not out_dir.exists()


def test_compile_still_defaults_converted_at_when_left_unset(tmp_path: Path) -> None:
    """converted_at=None (the default) requests auto-generation; it is not a rejected value.

    The malformed-value rejection above must not also reject the sentinel
    that requests auto-generation -- None is a legitimate, intentional input,
    never a value that "sneaks through" unvalidated.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    result = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented", converted_at=None)
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["converted_at"].endswith("Z")


def test_manifest_for_trusts_its_caller_for_converted_at_format(tmp_path: Path) -> None:
    """manifest_for documents (but does not itself re-check) that converted_at is pre-validated.

    compile_adaptation is manifest_for's sole caller and now validates
    converted_at before calling in (see the rejection test above), so this
    state is unreachable through the public compile path. A manifest that
    somehow still carries an invalid converted_at fails closed downstream,
    at verify_manifest, rather than silently passing.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    manifest_path = Path(compiled["manifest"])
    manifest = json.loads(manifest_path.read_text())
    manifest["converted_at"] = None
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValidationError, match="MANIFEST_ACQUISITION"):
        verify_manifest(compiled["corpus"], compiled["manifest"])


def test_converted_at_is_excluded_from_deterministic_hashes(tmp_path: Path) -> None:
    """converted_at is conversion history, not a canonical identifier input.

    Compiling the same egov_xml source twice with two different explicit
    converted_at values must still produce byte-identical corpus.jsonl,
    crosswalk.jsonl, and projection.jsonl, and identical corpus_sha256,
    crosswalk_sha256, projection_sha256, and build_options_sha256. The two
    manifest.json files may legitimately differ in exactly one key:
    converted_at.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    first = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "first", corpus_id="invented", converted_at="2024-01-01T00:00:00Z")
    second = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "second", corpus_id="invented", converted_at="2025-06-15T12:30:00Z")
    for name in ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl"):
        assert (Path(first["out_dir"]) / name).read_bytes() == (Path(second["out_dir"]) / name).read_bytes()
    first_manifest = json.loads(Path(first["manifest"]).read_text())
    second_manifest = json.loads(Path(second["manifest"]).read_text())
    assert first_manifest["converted_at"] == "2024-01-01T00:00:00Z"
    assert second_manifest["converted_at"] == "2025-06-15T12:30:00Z"
    for key in ("corpus_sha256", "crosswalk_sha256", "projection_sha256", "build_options_sha256"):
        assert first_manifest[key] == second_manifest[key]
    without_converted_at = {key: value for key, value in first_manifest.items() if key != "converted_at"}
    other_without_converted_at = {key: value for key, value in second_manifest.items() if key != "converted_at"}
    assert without_converted_at == other_without_converted_at


def test_validate_okf_verify_source_accepts_a_genuine_bundle(tmp_path: Path) -> None:
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=source)["bundle"])
    assert validate_okf(bundle)["source_reverified"] is False
    result = validate_okf(bundle, verify_source=True)
    assert result["valid"] is True and result["source_reverified"] is True


def test_validate_okf_verify_source_catches_a_corpus_not_derived_from_source(tmp_path: Path) -> None:
    """A corpus.jsonl edited after compile can be made internally self-consistent.

    Hand-editing one node's text and recomputing every hash that depends on
    corpus.jsonl bytes (corpus_sha256, projection_sha256) produces a bundle
    that passes plain validate_okf(bundle): every declared hash agrees with
    itself. Only re-deriving canonical/corpus.jsonl from the bundle's own
    embedded references/source.xml (validate_okf(bundle, verify_source=True))
    proves the corpus was never actually produced by converting that XML.
    """
    source = tmp_path / "law.xml"
    source.write_text(_minimal_law("<MainProvision><Article Num=\"1\"><Paragraph Num=\"1\"><ParagraphSentence>本文</ParagraphSentence></Paragraph></Article></MainProvision>"), encoding="utf-8")
    compiled = compile_corpus(source, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="invented")
    corpus_path = Path(compiled["corpus"])
    nodes = read_jsonl(corpus_path)
    target = next(n for n in nodes if n.kind is NodeKind.ARTICLE)
    # version_id is dataclass field(init=False): LegalNode.__post_init__
    # recomputes it from text (and the node's other identity fields)
    # automatically, so replace(text=...) alone yields a self-consistent,
    # non-tampered-looking node -- exactly the property this test needs.
    tampered = replace(target, text=target.text + "改ざん")
    tampered_nodes = [tampered if n is target else n for n in nodes]
    corpus_path.write_bytes(canonical_jsonl(tampered_nodes))
    manifest_path = Path(compiled["manifest"])
    manifest = json.loads(manifest_path.read_text())
    manifest["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    projection_path = Path(compiled["projection"])
    projection_bytes = canonical_projection_jsonl(make_projection(tampered_nodes))
    projection_path.write_bytes(projection_bytes)
    manifest["projection_sha256"] = hashlib.sha256(projection_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    # The forged compile output is internally self-consistent: plain
    # verify_manifest (no verify_inputs) accepts it.
    assert verify_manifest(compiled["corpus"], compiled["manifest"])["adapter"] == "egov_xml"
    bundle = Path(export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=source)["bundle"])
    result = validate_okf(bundle)
    assert result["valid"] is True and result["source_reverified"] is False
    with pytest.raises(LegalOKFError, match="JLEGAL_OKF_CANONICAL"):
        validate_okf(bundle, verify_source=True)
