"""Connect fixed source-authored expectations to the real producer and checker.

The display examples are grammar-boundary records, not complete law artifacts
with a self-referential version ID. The CR law variant is the existing synthetic
matrix with one numeric character reference, checked against the official XSD.
"""

import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest
import yaml

from jlegal_okf.assurance.conformance import _frontmatter, _profile, _source_payload_matches
from jlegal_okf.egov import _ensure_supported_tree, _render_text, admit_egov_xml
from jlegal_okf.errors import AdapterError, JLegalError
from jlegal_okf.legal_okf import (
    EXPORTER, LegalOKFError, _concept, _parse_concept, _source_body,
    _source_frontmatter, _validate_source_concept, export_okf, validate_okf,
)
from jlegal_okf.model import LegalNode, NodeKind, SourceRef, Temporal
from jlegal_okf.pipeline import compile_corpus, read_jsonl, verify_manifest


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "examples/conformance/cases.json").read_bytes())
MATRIX = CATALOG["cases"][0]
SOURCE = ROOT / "examples/conformance" / MATRIX["source"]
ORACLE = json.loads((ROOT / "examples/conformance/text-display-oracle.json").read_bytes())
CONVERSION = {"name": "JORI Engine", "version": "0.2.0-draft", "profile": "J-LEGAL-OKF/0.3.0-draft"}


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _reseal(bundle):
    manifest_path = bundle / "canonical/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    options = {k: manifest[k] for k in ("adapter", "adapter_version", "canonicalization", "hierarchy_status", "inputs", "required_input_roles", "build_recipe", "acquisition", "conversion")}
    manifest["build_options_sha256"] = hashlib.sha256(_json_bytes(options)[:-1]).hexdigest()
    manifest_path.write_bytes(_json_bytes(manifest))
    outer = json.loads((bundle / "manifest.json").read_bytes())
    outer["canonical_corpus_sha256"] = hashlib.sha256((bundle / "canonical/corpus.jsonl").read_bytes()).hexdigest()
    outer["canonical_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for entry in outer["files"]:
        entry["sha256"] = hashlib.sha256((bundle / entry["path"]).read_bytes()).hexdigest()
    (bundle / "manifest.json").write_bytes(_json_bytes(outer))


@pytest.mark.parametrize("case", ORACLE["text_cases"], ids=lambda c: c["id"])
def test_producer_character_data_matches_independent_oracle(case):
    element = ET.fromstring(case["xml"])
    before = ET.tostring(element)
    assert _render_text(element) == case["expected_text"]
    assert ET.tostring(element) == before


@pytest.mark.parametrize("xml,tag", [
    ("<NewProvision/>", "NewProvision"),
    ("<Unreviewed><Sentence>x</Sentence></Unreviewed>", "Unreviewed"),
    ("<Style><Unreviewed>x</Unreviewed></Style>", "Style"),
])
def test_character_data_fix_does_not_admit_unreviewed_structure(xml, tag):
    with pytest.raises(AdapterError, match="^EGOV_XML_UNSUPPORTED_STRUCTURE:" + tag + "$"):
        _ensure_supported_tree(ET.fromstring(xml))


def _grammar_node(case):
    base = LegalNode("Japan", "Law", None, "SyntheticGrammar", case["locator"],
                     NodeKind.LAW, 0, case["text"], Temporal(),
                     SourceRef("jlegal:source:sha256:" + "0" * 64, "0" * 64, "egov_xml", "SyntheticGrammar"))
    # A fixed example version binds markers only; it is not a valid full-law ID.
    return SimpleNamespace(**(base.__dict__ | {key: case[key] for key in ("version_id", "heading", "label")}))


def _document(node, body, newline="\n", separator="\n"):
    front = _source_frontmatter(node, "/references/source.xml", {}, CONVERSION, MATRIX["converted_at"])
    header = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).replace("\n", newline)
    return ("---" + newline + header + "---" + newline + separator + body).encode("utf-8")


@pytest.mark.parametrize("case", ORACLE["display_cases"], ids=lambda c: c["id"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf-header", "crlf-header"])
@pytest.mark.parametrize("separator", ["", "\n", "\r\n"], ids=["no-separator", "lf-separator", "crlf-separator"])
def test_display_oracle_survives_builder_storage_and_both_parsers(tmp_path, case, newline, separator):
    node = _grammar_node(case)
    assert _source_body(node) == case["expected_body"]
    raw = _document(node, case["expected_body"], newline, separator)
    path = tmp_path / "concept.md"
    path.write_bytes(raw)
    front, body = _parse_concept(path)
    independent_front, independent_body = _frontmatter(path.read_bytes())
    assert front == independent_front
    assert body == independent_body == case["expected_body"]
    assert _source_payload_matches(independent_body, case)
    _validate_source_concept(path, node, "/references/source.xml", {}, CONVERSION, MATRIX["converted_at"])
    # The reference producer's separator remains one LF blank line.
    assert _concept(front, body).endswith(("---\n\n" + case["expected_body"]).encode())


def _mutations(case):
    body = case["expected_body"]
    begin = "<!-- jlegal-source:" + case["version_id"] + ":begin -->"
    end = "<!-- jlegal-source:" + case["version_id"] + ":end -->"
    title = case["heading"] or case["label"] or case["locator"]
    prefix = "# " + title + "\n\n## Source text\n\n"
    return [
        "Commentary.\n" + body, body + "Commentary.\n",
        prefix + case["text"] + end + "\n",
        prefix + begin + case["text"] + "\n",
        prefix + case["text"] + "\n",
        prefix + begin + case["text"] + "!" + end + "\n",
        "# Wrong title\n\n## Source text\n\n" + begin + case["text"] + end + "\n",
        prefix + begin.replace(case["version_id"], "ver_wrong") + case["text"] + end + "\n",
        prefix + begin + case["text"] + end.replace(case["version_id"], "ver_wrong") + "\n",
        body[:-1], "\n" + body, "\r\n" + body,
    ]


@pytest.mark.parametrize("case", ORACLE["display_cases"], ids=lambda c: c["id"])
def test_complete_display_rejects_each_mutation_in_both_validators(tmp_path, case):
    node = _grammar_node(case)
    path = tmp_path / "concept.md"
    mutations = _mutations(case)
    if case["id"] == "preserved-newlines":
        mutations.append(case["expected_body"].replace("\r\n", "\n").replace("\r", "\n"))
    for body in mutations:
        path.write_bytes(_document(node, body))
        _, parsed = _frontmatter(path.read_bytes())
        assert not _source_payload_matches(parsed, case)
        with pytest.raises(LegalOKFError, match="^JLEGAL_OKF_SOURCE_CONTENT:"):
            _validate_source_concept(path, node, "/references/source.xml", {}, CONVERSION, MATRIX["converted_at"])


@pytest.fixture(scope="module")
def matrix_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("text-display-matrix")
    corpus = root / "corpus"
    compile_corpus(SOURCE, adapter="egov_xml", mapping={"law_id": MATRIX["official_law_id"]},
                   out_dir=corpus, corpus_id=MATRIX["corpus_id"], converted_at=MATRIX["converted_at"])
    bundle = root / "bundle"
    export_okf(corpus / "corpus.jsonl", corpus / "manifest.json", bundle, source=SOURCE)
    return bundle


def test_coordinated_tuple_source_structure_and_fixed_expected(matrix_bundle):
    bundle = matrix_bundle
    expected = json.loads((ROOT / "examples/conformance" / MATRIX["expected"]).read_bytes())
    codes, by_locator = _profile(bundle, expected, MATRIX)
    assert codes == []
    manifest = json.loads((bundle / "canonical/manifest.json").read_bytes())
    assert manifest["conversion"] == CONVERSION
    assert manifest["adapter_version"] == "2"
    assert {n["schema"] for n in by_locator.values()} == {"jori-corpus/v3"}
    assert admit_egov_xml(SOURCE, law_id=MATRIX["official_law_id"]).report(accepted=True, receipt_verified=False)["profile"] == CONVERSION["profile"]
    assert EXPORTER == "jlegal-okf-exporter/0.2.0-draft"
    assert (bundle / "references/source.xml").read_bytes() == SOURCE.read_bytes()
    assert validate_okf(bundle, verify_source=True)["source_reverified"]
    # Exact independently authored hierarchy/locators/attributes, not just text.
    for fixed in expected["nodes"]:
        node = by_locator[fixed["locator"]]
        assert node["text"] == fixed["text"]
        for field in ("kind", "depth", "ordinal", "branch", "heading", "label"):
            assert node[field] == fixed[field]
        assert node["parent_id"] == (by_locator[fixed["parent_locator"]]["node_id"] if fixed["parent_locator"] else None)
        assert {k: v for k, v in node["attributes"].items() if k != "build_provenance_sha256"} == (fixed["attributes"] | fixed.get("allowed_extra_attributes", {}))
    assert any(n["attributes"].get("Delete") == "true" for n in by_locator.values())


def test_numeric_cr_reference_survives_compile_export_and_source_replay(tmp_path):
    source = tmp_path / "source.xml"
    raw = SOURCE.read_bytes().replace(b"</Sentence>", b"&#xD;</Sentence>", 1)
    source.write_bytes(raw)
    corpus = tmp_path / "corpus"
    compile_corpus(source, adapter="egov_xml", mapping={"law_id": MATRIX["official_law_id"]},
                   out_dir=corpus, corpus_id="synthetic-cr-probe", converted_at=MATRIX["converted_at"])
    nodes = read_jsonl(corpus / "corpus.jsonl")
    assert any("\r" in n.text for n in nodes)
    bundle = tmp_path / "bundle"
    export_okf(corpus / "corpus.jsonl", corpus / "manifest.json", bundle, source=source)
    assert (bundle / "references/source.xml").read_bytes() == raw
    assert validate_okf(bundle, verify_source=True)["source_reverified"]
    for node in nodes:
        _, body = _frontmatter((bundle / "source" / (node.version_id + ".md")).read_bytes())
        assert _source_payload_matches(body, node.to_dict())


@pytest.mark.parametrize("entity,characters", [(b"&#xD;", "\r"), (b"&#xD;&#xA;", "\r\n")], ids=["cr", "crlf"])
def test_law_title_newlines_survive_index_and_resealed_changes_fail(tmp_path, entity, characters):
    source = tmp_path / "source.xml"
    raw = SOURCE.read_bytes().replace(b"<LawTitle>", b"<LawTitle>A" + entity + b"B", 1)
    source.write_bytes(raw)
    corpus = tmp_path / "corpus"
    compile_corpus(source, adapter="egov_xml", mapping={"law_id": MATRIX["official_law_id"]},
                   out_dir=corpus, corpus_id="synthetic-cr-title-probe", converted_at=MATRIX["converted_at"])
    nodes = read_jsonl(corpus / "corpus.jsonl")
    law = next(node for node in nodes if node.locator == "/law/root")
    assert law.heading.startswith("A" + characters + "B")
    bundle = tmp_path / "bundle"
    export_okf(corpus / "corpus.jsonl", corpus / "manifest.json", bundle, source=source)
    assert (bundle / "references/source.xml").read_bytes() == raw
    index = (bundle / "index.md").read_bytes()
    assert ("A" + characters + "B").encode("utf-8") in index
    concept = bundle / "source" / (law.version_id + ".md")
    assert _parse_concept(concept)[1] == _source_body(law)
    assert _source_payload_matches(_frontmatter(concept.read_bytes())[1], law.to_dict())
    assert validate_okf(bundle, verify_source=True)["source_reverified"]

    changed = tmp_path / "changed-bundle"
    shutil.copytree(bundle, changed)
    normalized = index.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    assert normalized != index
    (changed / "index.md").write_bytes(normalized)
    _reseal(changed)
    with pytest.raises(LegalOKFError, match="^JLEGAL_OKF_INDEX$"):
        validate_okf(changed, verify_source=True)


@pytest.mark.parametrize("mutation,code", [
    ("corpus-v2", "CORPUS_SCHEMA_UNSUPPORTED"),
    ("adapter-v1", "MANIFEST_OPTIONS"),
    ("old-profile", "MANIFEST_ACQUISITION"),
    ("old-converter", "MANIFEST_ACQUISITION"),
    ("missing-conversion", "MANIFEST_ACQUISITION"),
    ("old-tuple", "MANIFEST_OPTIONS"),
])
def test_old_or_mixed_tuple_is_rejected_before_replay(matrix_bundle, tmp_path, monkeypatch, mutation, code):
    import jlegal_okf.pipeline as pipeline
    bundle = tmp_path / "bundle"
    shutil.copytree(matrix_bundle, bundle)
    path = bundle / "canonical/manifest.json"
    manifest = json.loads(path.read_bytes())
    corpus = bundle / "canonical/corpus.jsonl"
    if mutation in {"corpus-v2", "old-tuple"}:
        corpus.write_bytes(corpus.read_bytes().replace(b'"schema":"jori-corpus/v3"', b'"schema":"jori-corpus/v2"'))
        manifest["corpus_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
    if mutation in {"adapter-v1", "old-tuple"}:
        manifest["adapter_version"] = "1"
    if mutation in {"old-profile", "old-tuple"}:
        manifest["conversion"]["profile"] = "J-LEGAL-OKF/0.2.0-draft"
    if mutation in {"old-converter", "old-tuple"}:
        manifest["conversion"]["version"] = "0.1.0-draft"
    if mutation == "missing-conversion":
        manifest["schema"] = "jori-manifest/v3"
        for key in ("conversion", "acquisition", "converted_at"):
            manifest.pop(key)
    path.write_bytes(_json_bytes(manifest))
    calls = []
    monkeypatch.setattr(pipeline, "_rebuild_from_manifest", lambda *args: calls.append(True))
    with pytest.raises(JLegalError, match=code):
        verify_manifest(corpus, path, verify_inputs=True, source=SOURCE)
    assert calls == []


@pytest.mark.parametrize("version", ["1", "999", 2, True, None, [], {}])
def test_checker_rejects_wrong_adapter_version(matrix_bundle, tmp_path, version):
    bundle = tmp_path / "bundle"
    shutil.copytree(matrix_bundle, bundle)
    path = bundle / "canonical/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["adapter_version"] = version
    path.write_bytes(_json_bytes(manifest))
    _reseal(bundle)
    expected = json.loads((ROOT / "examples/conformance" / MATRIX["expected"]).read_bytes())
    codes, _ = _profile(bundle, expected, MATRIX)
    assert set(codes) == ({"ADAPTER_METADATA"} if type(version) is str else {"ADAPTER_METADATA", "MANIFEST_TYPES"})


@pytest.mark.parametrize("mutation", ["prefix", "suffix", "markerless", "title", "payload", "second-blank", "hash"])
def test_resealed_display_failures_are_distinct_from_content_hash(matrix_bundle, tmp_path, mutation):
    bundle = tmp_path / "bundle"
    shutil.copytree(matrix_bundle, bundle)
    path = sorted((bundle / "source").glob("*.md"))[0]
    front, body = _frontmatter(path.read_bytes())
    if mutation == "hash":
        front["jlegal"]["content_sha256"] = "0" * 64
    elif mutation == "prefix":
        body = "Commentary.\n" + body
    elif mutation == "suffix":
        body += "Commentary.\n"
    elif mutation == "markerless":
        version = front["jlegal"]["version_id"]
        body = body.replace("<!-- jlegal-source:" + version + ":begin -->", "").replace("<!-- jlegal-source:" + version + ":end -->", "")
    elif mutation == "title":
        body = "# Wrong title" + body[body.index("\n"):]
    elif mutation == "payload":
        start = body.index("-->", body.index("<!-- jlegal-source:")) + 3
        body = body[:start] + "!" + body[start:]
    elif mutation == "second-blank":
        body = "\n" + body
    path.write_bytes(_concept(front, body))
    _reseal(bundle)
    expected = json.loads((ROOT / "examples/conformance" / MATRIX["expected"]).read_bytes())
    codes, _ = _profile(bundle, expected, MATRIX)
    assert codes == (["CONCEPT_TEXT"] if mutation == "hash" else ["SOURCE_DISPLAY_CONTRACT"])
    with pytest.raises(LegalOKFError, match="^JLEGAL_OKF_SOURCE_FIELDS:" if mutation == "hash" else "^JLEGAL_OKF_SOURCE_CONTENT:"):
        validate_okf(bundle, verify_source=True)


@pytest.mark.parametrize("schema", ["jori-corpus/v2", "jori-corpus/unknown"])
def test_checker_rejects_old_corpus_schema_after_resealing(matrix_bundle, tmp_path, schema):
    bundle = tmp_path / "bundle"
    shutil.copytree(matrix_bundle, bundle)
    corpus = bundle / "canonical/corpus.jsonl"
    rows = [json.loads(line) for line in corpus.read_bytes().splitlines()]
    for row in rows:
        row["schema"] = schema
    corpus.write_bytes(b"".join(_json_bytes(row) for row in rows))
    path = bundle / "canonical/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["corpus_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
    path.write_bytes(_json_bytes(manifest))
    _reseal(bundle)
    expected = json.loads((ROOT / "examples/conformance" / MATRIX["expected"]).read_bytes())
    codes, _ = _profile(bundle, expected, MATRIX)
    assert codes == ["NODE_SCHEMA"]


@pytest.mark.parametrize("adapter", ["json", "xml", "html"])
def test_generic_adapters_keep_version_one_with_shared_corpus_v3(tmp_path, adapter):
    source = tmp_path / ("source." + adapter)
    if adapter == "json":
        source.write_bytes(_json_bytes({"jurisdiction": "Example", "authority": "Act", "law_number_key": "1",
                                      "nodes": [{"kind": "law", "locator": "root", "text": "Invented"}]}))
        mapping = None
    else:
        source.write_bytes(b"<r><x><j>Example</j><a>Act</a><n>1</n><l>root</l><k>law</k><d>0</d><t>Invented</t></x></r>")
        mapping = {"row": "x", "fields": {"jurisdiction": "j", "authority": "a", "law_number_key": "n", "locator": "l",
                                            "kind": "k", "depth": {"path": "d", "type": "int"}, "text": "t"}}
    corpus = tmp_path / "corpus"
    compile_corpus(source, adapter=adapter, mapping=mapping, corpus_id="synthetic-generic", out_dir=corpus)
    manifest = verify_manifest(corpus / "corpus.jsonl", corpus / "manifest.json", verify_inputs=True, source=source)
    assert manifest["adapter_version"] == "1" and manifest["schema"] == "jori-manifest/v3"
    assert {n.to_dict()["schema"] for n in read_jsonl(corpus / "corpus.jsonl")} == {"jori-corpus/v3"}
