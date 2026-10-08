"""The oracle is checked in; producers only create submitted artifacts."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import unicodedata

import pytest
from jlegal_okf.assurance.conformance import check_okf_format, check_submission
from jlegal_okf.errors import AdapterError, JLegalError, ValidationError
from jlegal_okf.pipeline import compile_corpus, verify_canonical_artifacts, verify_manifest
from jlegal_okf.legal_okf import LegalOKFError, export_okf, validate_okf


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples/conformance/cases.json"


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _reseal(bundle):
    """Rehash mutations so incidental checksum failures cannot mask the oracle."""
    manifest_path = bundle / "canonical/manifest.json"
    manifest = _load(manifest_path)
    manifest["projection_sha256"] = hashlib.sha256((bundle / "canonical/projection.jsonl").read_bytes()).hexdigest()
    _write(manifest_path, manifest)
    outer = _load(bundle / "manifest.json")
    for entry in outer["files"]:
        if entry["path"] != "references/source.xml":
            entry["sha256"] = hashlib.sha256((bundle / entry["path"]).read_bytes()).hexdigest()
    outer["canonical_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write(bundle / "manifest.json", outer)


@pytest.mark.parametrize("mutation,code", [("source-payload", "SOURCE_DISPLAY_CONTRACT"), ("manifest-schema", "MANIFEST_SCHEMA"), ("projection-schema", "PROJECTION_SCHEMA"), ("rights-schema", "MANIFEST_SCHEMA"), ("bundle-schema", "BUNDLE_SCHEMA")])
def test_rehashed_semantic_mutations_do_not_pass(built, tmp_path, mutation, code):
    root = _copy(built, tmp_path)
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "rejection":
            continue
        bundle = root / case["id"] / "bundle"
        if mutation == "source-payload":
            path = sorted((bundle / "source").glob("*.md"))[0]
            raw = path.read_text()
            start = raw.index("-->", raw.index("<!-- jlegal-source:")) + 3
            path.write_text(raw[:start] + "改変。" + raw[start:])
        elif mutation in {"manifest-schema", "rights-schema"}:
            path = bundle / "canonical/manifest.json"
            value = _load(path)
            value["schema"] = "invalid-schema" if mutation == "manifest-schema" else "jori-manifest/v6"
            _write(path, value)
        elif mutation == "projection-schema":
            path = bundle / "canonical/projection.jsonl"
            values = [json.loads(line) for line in path.read_text().splitlines()]
            for value in values:
                value["schema"] = "invalid-schema"
            path.write_text("".join(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for v in values))
        else:
            path = bundle / "manifest.json"
            value = _load(path)
            value["schema"] = "jlegal-okf-bundle/v2"
            _write(path, value)
        _reseal(bundle)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["common_passed"]
    assert all(r["status"] == "pass" for r in result["relations"])
    for row in result["cases"][:-1]:
        assert row["layers"]["profile"]["codes"] == [code]


def _mutate_counts(built, tmp_path, field, value, *, crosswalk=None):
    root = _copy(built, tmp_path)
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "rejection":
            continue
        bundle = root / case["id"] / "bundle"
        path = bundle / "canonical/manifest.json"
        manifest = _load(path)
        manifest[field] = value
        if crosswalk is not None:
            (bundle / "canonical/crosswalk.jsonl").write_bytes(crosswalk)
            manifest["crosswalk_sha256"] = hashlib.sha256(crosswalk).hexdigest()
        _write(path, manifest)
        _reseal(bundle)
    return check_submission(CATALOG, root / "submission.json", tmp_path / "report")


def _assert_count_failure(result, required_codes):
    assert not result["common_passed"]
    assert all(row["status"] == "pass" for row in result["relations"])
    for row in result["cases"]:
        codes = set(row["layers"]["profile"]["codes"])
        if row["id"] == "new-provision":
            assert not codes
        else:
            assert required_codes <= codes
            # A checksum or unrelated failure must not mask this contract.
            assert codes <= {"MANIFEST_COUNTS", "MANIFEST_TYPES", "CROSSWALK_UNEXPECTED"}


@pytest.mark.parametrize("field,value", [
    ("node_count", 999), ("node_count", 0),
    ("law_count", 999), ("law_count", 0),
    ("crosswalk_count", 999), ("crosswalk_count", 1),
    ("projection_count", 999), ("projection_count", 0),
])
def test_manifest_count_mismatch_is_rejected_after_resealing(built, tmp_path, field, value):
    result = _mutate_counts(built, tmp_path, field, value)
    _assert_count_failure(result, {"MANIFEST_COUNTS"})
    assert all(row["layers"]["profile"]["codes"] == ["MANIFEST_COUNTS"]
               for row in result["cases"] if row["id"] != "new-provision")


@pytest.mark.parametrize("field", ["node_count", "law_count", "crosswalk_count", "projection_count"])
@pytest.mark.parametrize("value", [-1, True, False, "0"])
def test_manifest_count_types_are_rejected_after_resealing(built, tmp_path, field, value):
    result = _mutate_counts(built, tmp_path, field, value)
    _assert_count_failure(result, {"MANIFEST_TYPES"})


@pytest.mark.parametrize("crosswalk,count,codes", [
    (b'{}\n', 0, {"CROSSWALK_UNEXPECTED", "MANIFEST_COUNTS"}),
    (b'{}\n', 1, {"CROSSWALK_UNEXPECTED"}),
    (b'\n', 0, {"CROSSWALK_UNEXPECTED"}),
])
def test_crosswalk_record_count_does_not_relax_empty_file_contract(built, tmp_path, crosswalk, count, codes):
    result = _mutate_counts(built, tmp_path, "crosswalk_count", count, crosswalk=crosswalk)
    _assert_count_failure(result, codes)
    assert all(set(row["layers"]["profile"]["codes"]) == codes
               for row in result["cases"] if row["id"] != "new-provision")


def _projection_id(version_id, text):
    # The published full-node-v1 rule, independent of producer helpers.
    payload = (version_id + "|full-node-v1|" + text).encode("utf-8")
    return "projection_" + hashlib.sha256(payload).hexdigest()[:32]


def _write_projections(bundle, values):
    # Retain reference ordering where fields are strings, so comparison with
    # the ordinary verifier fails on derivation rather than serialization.
    values.sort(key=lambda p: tuple(p[k] if type(p.get(k)) is str else ""
                                  for k in ("locator", "version_id", "projection_id")))
    raw = "".join(json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for p in values)
    (bundle / "canonical/projection.jsonl").write_text(raw, encoding="utf-8")
    manifest = _load(bundle / "canonical/manifest.json")
    manifest["projection_count"] = len(values)
    _write(bundle / "canonical/manifest.json", manifest)
    _reseal(bundle)


def _mutate_projection(values, nodes, mutation):
    if mutation == "wrong-id":
        values[0]["projection_id"] = "projection_" + "0" * 32
    elif mutation == "duplicate-id":
        values[1]["projection_id"] = values[0]["projection_id"]
    elif mutation == "duplicate-pair":
        values[1] = dict(values[0])
    elif mutation == "duplicate-pair-distinct-id":
        values[1] = dict(values[0], projection_id="projection_" + "0" * 32)
    elif mutation == "missing":
        values.pop()
    elif mutation == "surplus":
        extra = dict(values[0], node_id="node_surplus", version_id="ver_surplus")
        extra["projection_id"] = _projection_id(extra["version_id"], extra["text"])
        values.append(extra)
    elif mutation == "law-root":
        law = next(n for n in nodes if n["kind"] == "law")
        extra = {k: law[k] for k in ("node_id", "version_id", "law_id", "locator", "heading", "text", "kind", "temporal")}
        extra.update(schema="jori-projection/v1", projection_version="1", evidence=law["source"],
                     projection_id=_projection_id(law["version_id"], law["text"]))
        values.append(extra)
    elif mutation == "wrong-version-pair":
        # A valid digest cannot excuse a node/version pair absent from corpus.
        values[0]["version_id"] = values[1]["version_id"]
        values[0]["projection_id"] = _projection_id(values[0]["version_id"], values[0]["text"])
    elif mutation == "text":
        values[0]["text"] += "改変。"
    elif mutation == "heading":
        values[0]["heading"] = "改変見出し"
    elif mutation == "temporal":
        values[0]["temporal"] = dict(values[0]["temporal"], valid_from="2026-01-01")
    elif mutation == "evidence":
        values[0]["evidence"] = dict(values[0]["evidence"], source_key="WrongLaw")
    else:
        raise AssertionError("unknown projection mutation")


@pytest.mark.parametrize("mutation,codes", [
    ("wrong-id", {"PROJECTION_IDENTITY"}),
    ("duplicate-id", {"PROJECTION_IDENTITY", "PROJECTION_ID_DUPLICATE"}),
    ("duplicate-pair", {"PROJECTION_SET", "PROJECTION_ID_DUPLICATE"}),
    ("duplicate-pair-distinct-id", {"PROJECTION_SET", "PROJECTION_IDENTITY"}),
    ("missing", {"PROJECTION_SET"}),
    ("surplus", {"PROJECTION_SET"}),
    ("law-root", {"PROJECTION_SET"}),
    ("wrong-version-pair", {"PROJECTION_SET"}),
    ("text", {"PROJECTION_IDENTITY", "PROJECTION_CONTENT"}),
    ("heading", {"PROJECTION_CONTENT"}),
    ("temporal", {"PROJECTION_CONTENT"}),
    ("evidence", {"PROJECTION_SOURCE"}),
])
def test_projection_contract_rejects_resealed_mutations(built, tmp_path, mutation, codes):
    root = _copy(built, tmp_path)
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "rejection":
            continue
        bundle = root / case["id"] / "bundle"
        values = [json.loads(line) for line in (bundle / "canonical/projection.jsonl").read_text().splitlines()]
        nodes = [json.loads(line) for line in (bundle / "canonical/corpus.jsonl").read_text().splitlines()]
        _mutate_projection(values, nodes, mutation)
        _write_projections(bundle, values)
        with pytest.raises(JLegalError, match="^PROJECTION_DERIVATION_MISMATCH$"):
            verify_canonical_artifacts(bundle / "canonical/corpus.jsonl")
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["common_passed"]
    assert all(row["status"] == "pass" for row in result["relations"])
    for row in result["cases"]:
        assert set(row["layers"]["profile"]["codes"]) == (set() if row["id"] == "new-provision" else codes)


@pytest.mark.parametrize("version", ["999", "test-1", "01", " 1", "１"])
def test_projection_contract_rejects_unsupported_version(built, tmp_path, version):
    root = _copy(built, tmp_path)
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "rejection":
            continue
        bundle = root / case["id"] / "bundle"
        values = [json.loads(line) for line in (bundle / "canonical/projection.jsonl").read_text().splitlines()]
        values[0]["projection_version"] = version
        _write_projections(bundle, values)
        with pytest.raises(JLegalError, match="^PROJECTION_DERIVATION_MISMATCH$"):
            verify_canonical_artifacts(bundle / "canonical/corpus.jsonl")
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["common_passed"]
    assert all(row["status"] == "pass" for row in result["relations"])
    for row in result["cases"]:
        assert row["layers"]["profile"]["codes"] == ([] if row["id"] == "new-provision" else ["PROJECTION_VERSION"])


@pytest.mark.parametrize("field,value", [
    ("projection_version", 1), ("projection_version", True),
    ("projection_version", 1.0), ("projection_version", None),
    ("projection_version", ""), ("projection_version", []),
    ("projection_id", []), ("projection_id", {}), ("projection_id", None),
    ("projection_id", ""), ("node_id", []), ("version_id", {}),
    ("text", None), ("temporal", []), ("evidence", []),
])
def test_projection_contract_rejects_malformed_fields_without_crashing(built, tmp_path, field, value):
    root = _copy(built, tmp_path)
    bundle = root / "edges/bundle"
    values = [json.loads(line) for line in (bundle / "canonical/projection.jsonl").read_text().splitlines()]
    values[0][field] = value
    _write_projections(bundle, values)
    with pytest.raises(ValidationError, match="^PROJECTION_LINE_"):
        verify_canonical_artifacts(bundle / "canonical/corpus.jsonl")
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["common_passed"]
    codes = next(r["layers"]["profile"]["codes"] for r in result["cases"] if r["id"] == "edges")
    assert "PROJECTION_SCHEMA" in codes
    assert set(codes) <= {"PROJECTION_SCHEMA", "PROJECTION_SET"}


def test_projection_identity_does_not_normalize_unicode_or_whitespace(built, tmp_path):
    root = _copy(built, tmp_path)
    bundle = root / "edges/bundle"
    values = [json.loads(line) for line in (bundle / "canonical/projection.jsonl").read_text().splitlines()]
    selected = [p for p in values if p["text"] != unicodedata.normalize("NFKC", p["text"]).strip()]
    assert selected
    for value in selected:
        value["projection_id"] = _projection_id(value["version_id"], unicodedata.normalize("NFKC", value["text"]).strip())
    _write_projections(bundle, values)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["common_passed"]
    row = next(r for r in result["cases"] if r["id"] == "edges")
    assert row["layers"]["profile"]["codes"] == ["PROJECTION_IDENTITY"]


def test_projection_contract_accepts_another_producer_with_exact_empty_and_whitespace_text(built, tmp_path):
    result = check_submission(CATALOG, built / "submission.json", tmp_path / "report")
    assert result["common_passed"]
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "rejection":
            continue
        corpus = built / case["id"] / "bundle/canonical/corpus.jsonl"
        artifacts = verify_canonical_artifacts(corpus)
        assert len(artifacts.projection) == len(artifacts.nodes) - 1
        assert all(p.projection_version == "1" and p.projection_id == _projection_id(p.version_id, p.text)
                   for p in artifacts.projection)
        # The manifest verifier deliberately accepts only its reference recipe.
        with pytest.raises(ValidationError, match="^MANIFEST_ACQUISITION$"):
            verify_manifest(corpus, corpus.parent / "manifest.json")
        if case["id"] == "edges":
            texts = {p.text for p in artifacts.projection}
            assert {"", " \n  ", "　合成空白\u00a0  を保持する。　"} <= texts


@pytest.mark.parametrize("text", ["", " ", "\n　text\u00a0\n"])
def test_marked_payload_requires_complete_common_display_grammar(text):
    from jlegal_okf.assurance.conformance import _source_payload_matches
    node = {"version_id": "ver_demo", "text": text, "heading": "Title", "label": None, "locator": "/law/root"}
    begin, end = "<!-- jlegal-source:ver_demo:begin -->", "<!-- jlegal-source:ver_demo:end -->"
    body = "# Title\n\n## Source text\n\n" + begin + text + end + "\n"
    assert _source_payload_matches(body, node)
    for body in ("# Other display title\n" + begin + text + end, begin + "extra" + text + end, begin + text, begin + text + end + begin + end, begin.replace("ver_demo", "ver_wrong") + text + end):
        assert not _source_payload_matches(body, node)


@pytest.mark.parametrize("path", ["C:/outside.xml", "C:outside.xml", "c:/outside.xml", "nested/C:outside.xml"])
def test_submission_paths_refuse_windows_drives(tmp_path, path):
    from jlegal_okf.assurance.conformance import _relative
    with pytest.raises(ValueError, match="UNSAFE_PATH"):
        _relative(tmp_path, path)


def _build_submission(root):
    rows = []
    for case in _load(CATALOG)["cases"]:
        case_root = root / case["id"]
        case_root.mkdir()
        source = case_root / "source.xml"
        shutil.copyfile(CATALOG.parent / case["source"], source)
        row = {"id": case["id"], "source": source.relative_to(root).as_posix(), "source_sha256": case["source_sha256"], "official_law_id": case["official_law_id"]}
        if case["method"] == "rejection":
            with pytest.raises(AdapterError, match="EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision"):
                compile_corpus(source, adapter="egov_xml", mapping={"law_id": case["official_law_id"]}, corpus_id=case["corpus_id"], out_dir=case_root / "corpus")
            receipt = case_root / "rejection.json"
            _write(receipt, {"accepted": False, "code": case["diagnostic"], "source_sha256": case["source_sha256"], "official_law_id": case["official_law_id"]})
            row.update(outcome="rejected", rejection=receipt.relative_to(root).as_posix())
        else:
            corpus = case_root / "corpus"
            compile_corpus(source, adapter="egov_xml", mapping={"law_id": case["official_law_id"]}, corpus_id=case["corpus_id"], converted_at=case["converted_at"], out_dir=corpus)
            bundle = case_root / "bundle"
            export_okf(corpus / "corpus.jsonl", corpus / "manifest.json", bundle, source=source)
            if case["method"] == "source_tamper":
                embedded = bundle / "references/source.xml"
                embedded.write_bytes(embedded.read_bytes() + b"\n<!-- synthetic tamper -->\n")
            row.update(outcome="artifacts", bundle=bundle.relative_to(root).as_posix())
        rows.append(row)
    _write(root / "submission.json", {"schema": "jlegal-conformance-submission/v1", "cases": rows, "jori_byte_regression": True})
    return root


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    # Only producer metadata differs. Rendering and the common display grammar
    # use the unmodified implementation; fixed expectations remain independent.
    import jlegal_okf.pipeline
    import jlegal_okf.legal_okf
    with pytest.MonkeyPatch.context() as patch:
        conversion = {"name": "Synthetic independent producer", "version": "test-1", "profile": "J-LEGAL-OKF/0.3.0-draft"}
        patch.setattr(jlegal_okf.pipeline, "JLEGAL_CONVERTER", conversion)
        patch.setattr(jlegal_okf.legal_okf, "JLEGAL_CONVERTER", conversion)
        root = _build_submission(tmp_path_factory.mktemp("conformance-submission"))
    data = _load(root / "submission.json")
    data["jori_byte_regression"] = False
    _write(root / "submission.json", data)
    return root


def _copy(built, tmp_path):
    root = tmp_path / "submission"
    shutil.copytree(built, root)
    return root


def test_fixed_suite_passes_and_never_invokes_producer(built, tmp_path, monkeypatch):
    import jlegal_okf.pipeline
    import jlegal_okf.egov
    import jlegal_okf.legal_okf
    def forbidden(*args, **kwargs):
        raise AssertionError("producer invoked by artifact checker")
    monkeypatch.setattr(jlegal_okf.pipeline, "compile_corpus", forbidden)
    monkeypatch.setattr(jlegal_okf.pipeline, "make_projection", forbidden)
    monkeypatch.setattr(jlegal_okf.pipeline, "verify_canonical_artifacts", forbidden)
    monkeypatch.setattr(jlegal_okf.egov, "egov_xml_adapter", forbidden)
    monkeypatch.setattr(jlegal_okf.legal_okf, "validate_okf", forbidden)
    result = check_submission(CATALOG, built / "submission.json", tmp_path / "report")
    assert result["passed"], result
    assert result["required_case_count"] == 7
    assert all(r["status"] == "pass" for r in result["relations"])
    assert result["cases"][0]["layers"]["jori_byte_regression"]["status"] == "not_checked"
    assert _load(built / "matrix/bundle/canonical/manifest.json")["conversion"]["name"] != "JORI Engine"
    for case in _load(CATALOG)["cases"]:
        if case["method"] != "rejection":
            bundle = built / case["id"] / "bundle"
            assert _load(bundle / "canonical/manifest.json")["crosswalk_count"] == 0
            assert (bundle / "canonical/crosswalk.jsonl").read_bytes() == b""


def test_reference_producer_passes_fixed_oracle_and_new_byte_golden(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    _build_submission(root)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert result["common_passed"] is True
    assert result["passed"] is True
    for row in result["cases"]:
        assert row["layers"]["profile"]["codes"] == []
    for case in _load(CATALOG)["cases"]:
        if case["method"] == "artifact":
            assert validate_okf(root / case["id"] / "bundle", verify_source=True)["source_reverified"]
        elif case["method"] == "source_tamper":
            with pytest.raises(LegalOKFError, match="^JLEGAL_OKF_MANIFEST_TAMPERED$"):
                validate_okf(root / case["id"] / "bundle", verify_source=True)
        else:
            assert not (root / case["id"] / "corpus").exists()
    assert result["cases"][0]["layers"]["jori_byte_regression"]["status"] == "pass"
    assert [row["layers"]["jori_byte_regression"]["status"] for row in result["cases"]] == [
        "pass", "pass", "pass", "pass", "pass", "not_checked", "not_checked",
    ]


def test_jori_bytes_are_separate_from_common_checks(built, tmp_path):
    root = _copy(built, tmp_path)
    data = _load(root / "submission.json")
    data["jori_byte_regression"] = True
    _write(root / "submission.json", data)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert result["common_passed"] is True
    assert result["passed"] is False
    assert result["cases"][0]["layers"]["jori_byte_regression"]["codes"] == ["JORI_BYTES"]


def test_missing_unknown_and_duplicate_cases_are_not_pass(built, tmp_path):
    root = _copy(built, tmp_path)
    data = _load(root / "submission.json")
    data["cases"].pop()
    data["cases"].extend([data["cases"][0], {"id": "unknown"}])
    _write(root / "submission.json", data)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert not result["passed"]
    assert result["errors"] == ["DUPLICATE_CASE", "UNKNOWN_CASE"]
    assert "MISSING_CASE" in result["cases"][-1]["layers"]["profile"]["codes"]


@pytest.mark.parametrize("mutation", ["text", "style-markup", "bool-depth", "parent", "source-id", "source-hash", "date", "appendix-id", "projection", "rejection", "untampered", "tamper-other-file", "traversal", "symlink", "missing-file"])
def test_artifact_failures_are_detected(built, tmp_path, mutation):
    root = _copy(built, tmp_path)
    case = "edges" if mutation == "date" else "matrix"
    corpus = root / case / "bundle/canonical/corpus.jsonl"
    rows = [json.loads(line) for line in corpus.read_text().splitlines()]
    if mutation == "text":
        rows[0]["text"] += "改ざん"
    elif mutation == "style-markup":
        node = next(n for n in rows if n["attributes"].get("egov_tag") == "AppdxStyle")
        node["text"] = "<invented>" + node["text"] + "</invented>"
    elif mutation == "bool-depth":
        next(n for n in rows if n["depth"] == 1)["depth"] = True
    elif mutation == "parent":
        rows[0]["parent_id"] = "node_missing"
    elif mutation == "source-id":
        rows[0]["source"]["source_key"] = "WrongLaw"
    elif mutation == "source-hash":
        rows[0]["source"]["sha256"] = "0" * 64
    elif mutation == "date":
        rows[0]["temporal"]["promulgated"] = "2020-01-02"
    elif mutation == "appendix-id":
        next(n for n in rows if n["kind"] == "appendix")["node_id"] = "node_wrong"
    elif mutation == "projection":
        (root / "matrix/bundle/canonical/projection.jsonl").write_text("")
    elif mutation == "rejection":
        value = _load(root / "new-provision/rejection.json")
        value["accepted"] = True
        _write(root / "new-provision/rejection.json", value)
    elif mutation == "untampered":
        shutil.copyfile(root / "matrix/source.xml", root / "tampered-source/bundle/references/source.xml")
    elif mutation == "tamper-other-file":
        index = root / "tampered-source/bundle/index.md"
        index.write_text(index.read_text() + "\nUnexpected edit.\n")
    elif mutation == "traversal":
        data = _load(root / "submission.json")
        data["cases"][0]["source"] = "../submission/matrix/source.xml"
        _write(root / "submission.json", data)
    elif mutation == "symlink":
        path = root / "matrix/bundle/references/source.xml"
        path.unlink()
        path.symlink_to(root / "matrix/source.xml")
    elif mutation == "missing-file":
        (root / "matrix/bundle/canonical/manifest.json").unlink()
    if mutation in {"text", "style-markup", "bool-depth", "parent", "source-id", "source-hash", "date", "appendix-id"}:
        corpus.write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in rows))
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert result["passed"] is False
    assert str(root) not in json.dumps(result)
    if mutation in {"text", "style-markup"}:
        assert "NODE_TEXT" in result["cases"][0]["layers"]["profile"]["codes"]


def test_format_floor_accepts_optional_and_unknown_fields(tmp_path):
    (tmp_path / "concept.md").write_text("---\ntype: Unknown Synthetic Type\nextra: retained\nverified: {by: 'process:demo', at: '2026-08-09T00:00:00Z'}\n---\n[unwritten](missing.md)\n")
    assert check_okf_format(tmp_path) == []
    (tmp_path / "concept.md").write_text("---\ntype: ''\n---\n")
    assert check_okf_format(tmp_path) == ["OKF_DOCUMENT"]


@pytest.mark.parametrize("name,content", [("nested/index.md", "---\nokf_version: '0.2'\n---\n"), ("log.md", "# History\n## 2026-99-88\n"), ("index.md", "---\ntype: fake\n---\n")])
def test_reserved_okf_files_are_checked(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    assert check_okf_format(tmp_path) == ["OKF_DOCUMENT"]


def test_catalog_tamper_and_existing_output_are_invalid_requests(built, tmp_path):
    catalog_root = tmp_path / "catalog"
    shutil.copytree(CATALOG.parent, catalog_root)
    source = catalog_root / "sources/matrix.xml"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="CATALOG_SOURCE_CHANGED"):
        check_submission(catalog_root / "cases.json", built / "submission.json", tmp_path / "report")
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        check_submission(CATALOG, built / "submission.json", out)


def test_expectations_have_all_sixteen_coverage_and_empty_whitespace_cases():
    catalog = _load(CATALOG)
    golden = _load(ROOT / "examples/fixtures/synthetic_egov_structure_matrix.golden.json")
    assert catalog["cases"][0]["coverage"] == golden["coverage_ids"]
    expected = _load(CATALOG.parent / "expected/edges.json")
    assert expected["temporal"] == dict.fromkeys(("valid_from", "valid_to", "promulgated", "repealed"))
    assert any(n["text"] == "" for n in expected["nodes"])
    assert any(n["text"] == " \n  " for n in expected["nodes"])
    assert any(n["text"] == "　合成空白\u00a0  を保持する。　" for n in expected["nodes"])
