"""The oracle is checked in; producers only create submitted artifacts."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil

import pytest
from jlegal_okf.assurance.conformance import check_okf_format, check_submission
from jlegal_okf.errors import AdapterError
from jlegal_okf.pipeline import compile_corpus
from jlegal_okf.legal_okf import export_okf


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


@pytest.mark.parametrize("mutation,code", [("source-payload", "CONCEPT_TEXT"), ("manifest-schema", "MANIFEST_SCHEMA"), ("projection-schema", "PROJECTION_SCHEMA"), ("rights-schema", "MANIFEST_SCHEMA"), ("bundle-schema", "BUNDLE_SCHEMA")])
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


@pytest.mark.parametrize("text", ["", " ", "\n　text\u00a0\n"])
def test_marked_payload_is_exact_without_requiring_reference_headings(text):
    from jlegal_okf.assurance.conformance import _source_payload_matches
    node = {"version_id": "ver_demo", "text": text}
    begin, end = "<!-- jlegal-source:ver_demo:begin -->", "<!-- jlegal-source:ver_demo:end -->"
    assert _source_payload_matches("# Other display title\n" + begin + text + end, node)
    for body in (begin + "extra" + text + end, begin + text, begin + text + end + begin + end, begin.replace("ver_demo", "ver_wrong") + text + end):
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
    # A fixture-only producer stand-in supplies character-only Style rendering.
    # Expectations remain immutable source-authored files. This is deliberately
    # separate from the measured unmodified reference implementation below.
    import jlegal_okf.egov
    import jlegal_okf.pipeline
    import jlegal_okf.legal_okf
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(jlegal_okf.egov, "_render_text", jlegal_okf.egov._character_data)
        conversion = {"name": "Synthetic independent producer", "version": "test-1", "profile": "J-LEGAL-OKF/0.2.0-draft"}
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
    monkeypatch.setattr(jlegal_okf.egov, "egov_xml_adapter", forbidden)
    monkeypatch.setattr(jlegal_okf.legal_okf, "validate_okf", forbidden)
    result = check_submission(CATALOG, built / "submission.json", tmp_path / "report")
    assert result["passed"], result
    assert result["required_case_count"] == 7
    assert all(r["status"] == "pass" for r in result["relations"])
    assert result["cases"][0]["layers"]["jori_byte_regression"]["status"] == "not_checked"
    assert _load(built / "matrix/bundle/canonical/manifest.json")["conversion"]["name"] != "JORI Engine"


def test_reference_style_discrepancy_is_reported_without_changing_golden(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    _build_submission(root)
    result = check_submission(CATALOG, root / "submission.json", tmp_path / "report")
    assert result["common_passed"] is False
    for row in result["cases"]:
        expected_codes = [] if row["id"] in {"appendix-alone", "new-provision"} else ["NODE_TEXT"]
        assert row["layers"]["profile"]["codes"] == expected_codes
    assert result["cases"][0]["layers"]["jori_byte_regression"]["status"] == "pass"


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
