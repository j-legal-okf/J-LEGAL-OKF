"""Offline regression coverage using only invented, temporary legal data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from jlegal_okf.cli import main
from jlegal_okf.egov import EGOV_ADMISSION_SCHEMA, MAX_EGOV_XML_BYTES, egov_xml_adapter
from jlegal_okf.errors import AdapterError, JLegalError, ValidationError
from jlegal_okf.legal_okf import export_okf, validate_okf
from jlegal_okf.pipeline import compile_corpus, verify_manifest


PUBLIC_FIXTURE = Path(__file__).parents[1] / "examples" / "synthetic_egov_law.xml"


def _json_source(path: Path) -> Path:
    path.write_text(json.dumps({"jurisdiction": "Example", "authority": "Test", "source_law_key": "synthetic-001", "nodes": [{"locator": "root", "kind": "law", "text": "Synthetic statute", "children": [{"locator": "article", "kind": "article", "ordinal": 1, "text": "Synthetic rule"}]}]}, ensure_ascii=False), encoding="utf-8")
    return path


def test_compile_validate_and_manifest_tamper_detection(tmp_path: Path) -> None:
    source = _json_source(tmp_path / "synthetic.json")
    result = compile_corpus(source, adapter="json", out_dir=tmp_path / "corpus", corpus_id="synthetic")
    manifest = verify_manifest(result["corpus"], result["manifest"], verify_inputs=True, source=source)
    assert manifest["node_count"] == 2
    (tmp_path / "corpus" / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(JLegalError, match="MANIFEST_CORPUS_TAMPERED"):
        verify_manifest(result["corpus"], result["manifest"])


def test_manifest_options_tamper_is_detected(tmp_path: Path) -> None:
    result = compile_corpus(_json_source(tmp_path / "synthetic.json"), adapter="json", out_dir=tmp_path / "corpus", corpus_id="synthetic")
    manifest_path = Path(result["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["adapter"] = "html"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((JLegalError, ValidationError), match="MANIFEST"):
        verify_manifest(result["corpus"], manifest_path)


def test_egov_compile_export_and_validate_okf(tmp_path: Path) -> None:
    compiled = compile_corpus(PUBLIC_FIXTURE, adapter="egov_xml", out_dir=tmp_path / "corpus", corpus_id="synthetic-law")
    bundle = export_okf(compiled["corpus"], compiled["manifest"], tmp_path / "bundle", source=PUBLIC_FIXTURE)
    assert bundle["nodes"] == 4
    assert (tmp_path / "bundle" / "references" / "source.xml").read_bytes() == PUBLIC_FIXTURE.read_bytes()
    assert validate_okf(tmp_path / "bundle")["valid"] is True


def test_public_synthetic_fixture_drives_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Keep the documented, repository-owned sample offline and executable."""
    assert "架空" in PUBLIC_FIXTURE.read_text(encoding="utf-8")
    corpus_dir = tmp_path / "corpus"
    assert main(["compile", str(PUBLIC_FIXTURE), "--adapter", "egov_xml", "--corpus-id", "synthetic-egov-law", "--out-dir", str(corpus_dir)]) == 0
    compiled = json.loads(capsys.readouterr().out)
    assert main(["validate", "--corpus", compiled["corpus"], "--manifest", compiled["manifest"], "--verify-inputs", "--source", str(PUBLIC_FIXTURE)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    bundle_dir = tmp_path / "bundle"
    assert main(["export-okf", "--corpus", compiled["corpus"], "--manifest", compiled["manifest"], "--out-dir", str(bundle_dir), "--source", str(PUBLIC_FIXTURE)]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == 4
    assert main(["validate-okf", str(bundle_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_egov_rejects_new_provision(tmp_path: Path) -> None:
    source = tmp_path / "unsupported.xml"
    source.write_text(PUBLIC_FIXTURE.read_text(encoding="utf-8").replace("</MainProvision>", "<NewProvision/></MainProvision>"), encoding="utf-8")
    with pytest.raises(AdapterError, match="EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision"):
        egov_xml_adapter(source)


def test_validate_source_reports_admission_and_compile_cannot_bypass_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first_report = tmp_path / "admission-one.json"
    second_report = tmp_path / "admission-two.json"
    command = ["validate-source", str(PUBLIC_FIXTURE), "--report"]
    assert main([*command, str(first_report)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first == json.loads(first_report.read_text(encoding="utf-8"))
    assert first["schema"] == EGOV_ADMISSION_SCHEMA
    assert first["accepted"] is True
    assert first["source_sha256"] == hashlib.sha256(PUBLIC_FIXTURE.read_bytes()).hexdigest()
    assert main([*command, str(second_report)]) == 0
    assert first_report.read_bytes() == second_report.read_bytes()

    unsafe = tmp_path / "unsafe.xml"
    unsafe.write_text("<!DOCTYPE Law [<!ENTITY x 'no'>]><Law LawId='SyntheticLaw001'><LawBody><MainProvision>&x;</MainProvision></LawBody></Law>", encoding="utf-16")
    rejected_report = tmp_path / "rejected.json"
    assert main(["validate-source", str(unsafe), "--report", str(rejected_report)]) == 2
    assert json.loads(rejected_report.read_text(encoding="utf-8"))["diagnostics"] == ["EGOV_XML_DTD_OR_ENTITY_FORBIDDEN"]
    assert not (tmp_path / "corpus").exists()
    assert main(["compile", str(unsafe), "--adapter", "egov_xml", "--out-dir", str(tmp_path / "corpus")]) == 2
    assert not (tmp_path / "corpus").exists()


def test_validate_source_refuses_a_file_larger_than_64_mib(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    oversized = tmp_path / "oversized.xml"
    with oversized.open("wb") as handle:
        handle.truncate(MAX_EGOV_XML_BYTES + 1)
    report = tmp_path / "oversized-admission.json"
    assert main(["validate-source", str(oversized), "--report", str(report)]) == 2
    capsys.readouterr()
    assert json.loads(report.read_text(encoding="utf-8"))["diagnostics"] == ["EGOV_XML_INPUT_TOO_LARGE"]


def test_validate_source_refuses_to_overwrite_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "admission.json"
    report.write_text("user-owned", encoding="utf-8")
    assert main(["validate-source", str(PUBLIC_FIXTURE), "--report", str(report)]) == 3
    capsys.readouterr()
    assert report.read_text(encoding="utf-8") == "user-owned"


def test_validate_source_checks_optional_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = {
        "schema": "jlegal-egov-acquisition/v1", "source_authority": "e-Gov 法令API Version 2",
        "source_url": None, "retrieved_at": None, "source_format": "e-Gov Law API v2 XML full-text response",
        "official_law_id": "SyntheticLaw001", "law_number": None, "requested_law_id": None,
        "as_of": None, "sha256": hashlib.sha256(PUBLIC_FIXTURE.read_bytes()).hexdigest(), "rights": None,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert main(["validate-source", str(PUBLIC_FIXTURE), "--acquisition", str(receipt_path)]) == 0
    assert json.loads(capsys.readouterr().out)["receipt_verified"] is True
    receipt["sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert main(["validate-source", str(PUBLIC_FIXTURE), "--acquisition", str(receipt_path)]) == 2


@pytest.mark.parametrize("command", ["validate-source", "compile", "validate", "fetch", "export-okf", "validate-okf"])
def test_cli_help_is_available_without_network(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    assert command in capsys.readouterr().out


def test_cli_compile_and_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _json_source(tmp_path / "synthetic.json")
    assert main(["compile", str(source), "--adapter", "json", "--out-dir", str(tmp_path / "corpus")]) == 0
    compile_result = json.loads(capsys.readouterr().out)
    assert main(["validate", "--corpus", compile_result["corpus"], "--manifest", compile_result["manifest"], "--verify-inputs", "--source", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_validate_diagnostics_json_reports_an_empty_list_on_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _json_source(tmp_path / "synthetic.json")
    assert main(["compile", str(source), "--adapter", "json", "--out-dir", str(tmp_path / "corpus")]) == 0
    compile_result = json.loads(capsys.readouterr().out)
    assert main(["validate", "--corpus", compile_result["corpus"], "--manifest", compile_result["manifest"], "--diagnostics-json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_validate_diagnostics_json_reports_layered_failures_without_touching_default_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A tampered-but-manifest-consistent corpus: the default `validate` output stays untouched by this flag."""
    from jlegal_okf.model import canonical_json

    source = _json_source(tmp_path / "synthetic.json")
    assert main(["compile", str(source), "--adapter", "json", "--out-dir", str(tmp_path / "corpus")]) == 0
    compile_result = json.loads(capsys.readouterr().out)
    corpus_path = Path(compile_result["corpus"])
    manifest_path = Path(compile_result["manifest"])

    records = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
    root_index = next(i for i, record in enumerate(records) if record["parent_id"] is None)
    assert records[root_index]["depth"] == 0
    # "depth" feeds no identifier hash and has no projection counterpart
    # (RetrievalDocument has no depth field), so this violates only the
    # ROOT_DEPTH diagnostic without invalidating any stored identifier or
    # the corpus-to-projection derivation check.
    records[root_index]["depth"] = 1
    tampered = b"".join(canonical_json(record) + b"\n" for record in records)
    corpus_path.write_bytes(tampered)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corpus_sha256"] = hashlib.sha256(tampered).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert main(["validate", "--corpus", str(corpus_path), "--manifest", str(manifest_path), "--diagnostics-json"]) == 2
    diagnostics = json.loads(capsys.readouterr().out)
    assert diagnostics
    assert all({"code", "subject", "detail", "layer"} == set(item) for item in diagnostics)
    root_depth = next(item for item in diagnostics if item["code"] == "ROOT_DEPTH")
    assert root_depth["layer"] == "structure"

    # Same tampered corpus, default flag-less output: unchanged shape/exit code.
    assert main(["validate", "--corpus", str(corpus_path), "--manifest", str(manifest_path)]) == 2
    assert capsys.readouterr().out == ""
