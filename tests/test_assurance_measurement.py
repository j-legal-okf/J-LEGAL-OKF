"""Synthetic/offline assurance behavior, including failure denominators."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from jlegal_okf.assurance.contracts import (AssuranceError, canonical_bytes, implementation_identity,
                                          verify_implementation_lock, write_json)
from jlegal_okf.assurance.inventory import build_inventory, inventory, verify_inventory
from jlegal_okf.assurance.reporting import metrics
from jlegal_okf.assurance.survey import _run_case, run_worker, survey

FIXTURE = Path(__file__).resolve().parents[1] / "examples/synthetic_egov_law.xml"
FIXED_TIME = "2026-08-09T00:00:00Z"


def make_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "inputs"
    root.mkdir()
    shutil.copyfile(FIXTURE, root / "arbitrary-filename.xml")
    return root


def make_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "implementation.json"
    write_json(lock, {"schema": "jlegal-implementation-lock/v1", "artifact_kind": "candidate-source",
                      "source_revision": None, **implementation_identity()})
    return lock


def test_inventory_counts_invalid_missing_and_duplicate_without_paths(tmp_path):
    root = make_inputs(tmp_path)
    shutil.copyfile(FIXTURE, root / "duplicate.XML")
    (root / "invalid.xml").write_text("<not xml")
    (root / "missing.xml").write_text(FIXTURE.read_text().replace(' LawId="SyntheticLaw001"', ""))
    result = inventory(root, tmp_path / "inventory")
    assert (result["files"], result["unique_units"], result["duplicates"]) == (4, 3, 1)
    assert {r["identity_status"] for r in result["units"]} == {"IDENTIFIED", "INVALID_XML", "MISSING_ID"}
    public = canonical_bytes(result).decode()
    assert str(root) not in public and "filename" not in public and "架空" not in public
    local = json.loads((tmp_path / "inventory/inventory.local.json").read_text())
    assert all("path" in row for row in local["files"])


@pytest.mark.parametrize("change", ["bytes", "add", "delete"])
def test_inventory_detects_all_xml_changes(tmp_path, change):
    root = make_inputs(tmp_path)
    inventory(root, tmp_path / "inventory")
    target = root / "arbitrary-filename.xml"
    if change == "bytes":
        target.write_bytes(target.read_bytes() + b"\n")
    elif change == "add":
        (root / "another.xml").write_text("<Law/>")
    else:
        target.unlink()
    with pytest.raises(AssuranceError, match="INVENTORY_CHANGED"):
        verify_inventory(tmp_path / "inventory/inventory.local.json", root)


def test_explicit_map_is_not_filename_inference(tmp_path):
    root = make_inputs(tmp_path)
    target = root / "arbitrary-filename.xml"
    target.write_text(FIXTURE.read_text().replace(' LawId="SyntheticLaw001"', ""))
    local, data = build_inventory(root, {target.name: "Explicit001"})
    assert data["units"][0]["law_id"] == "Explicit001"
    assert local["law_id_map"] == {target.name: "Explicit001"}
    with pytest.raises(AssuranceError, match="PATH_TRAVERSAL"):
        build_inventory(root, {"../outside.xml": "Explicit001"})


@pytest.mark.parametrize("directory", [False, True])
def test_inventory_refuses_symlinks_before_traversal(tmp_path, directory):
    root = make_inputs(tmp_path)
    (root / "linked").symlink_to(tmp_path if directory else FIXTURE, target_is_directory=directory)
    with pytest.raises(AssuranceError, match="SYMLINK_REFUSED"):
        build_inventory(root)


def test_public_identity_never_echoes_path_or_text(tmp_path):
    root = make_inputs(tmp_path)
    target = root / "arbitrary-filename.xml"
    target.write_text(FIXTURE.read_text().replace("SyntheticLaw001", "/secret/private/path"))
    _, data = build_inventory(root)
    assert data["units"][0]["identity_status"] == "INVALID_ID"
    assert data["units"][0]["law_id"] is None
    assert "secret" not in canonical_bytes(data).decode()


def test_forged_implementation_and_runtime_locks_refused(tmp_path):
    path = make_lock(tmp_path)
    lock = json.loads(path.read_text())
    lock["package_tree_sha256"] = "0" * 64
    write_json(path, lock)
    with pytest.raises(AssuranceError, match="IMPLEMENTATION_LOCK_MISMATCH"):
        verify_implementation_lock(path)
    path = make_lock(tmp_path)
    lock = json.loads(path.read_text())
    lock["dependencies"]["PyYAML"] = "fictional"
    write_json(path, lock)
    with pytest.raises(AssuranceError, match="IMPLEMENTATION_RUNTIME_MISMATCH"):
        verify_implementation_lock(path)


def test_full_survey_preserves_failed_denominators_and_is_repeatable(tmp_path):
    root = make_inputs(tmp_path)
    (root / "bad.xml").write_text("<broken")
    (root / "missing.xml").write_text(FIXTURE.read_text().replace(' LawId="SyntheticLaw001"', ""))
    inventory(root, tmp_path / "inventory")
    lock = make_lock(tmp_path)
    first = survey(tmp_path / "inventory/inventory.local.json", root, lock, FIXED_TIME, tmp_path / "first")
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    second = survey(tmp_path / "inventory/inventory.local.json", moved, lock, FIXED_TIME, tmp_path / "second")
    assert first == second
    assert not first["passed"]
    assert first["metrics"]["admission"] == {"pass": 1, "fail": 2, "blocked": 0, "error": 0,
                                              "all_units": 3, "reached_units": 3,
                                              "reason_counts": {"pass": {"OK": 1}, "fail": {"EGOV_XML_LAW_ID_REQUIRED": 1, "EGOV_XML_PARSE": 1}, "blocked": {}, "error": {}},
                                              "pass_rate_all": 1 / 3, "pass_rate_reached": 1 / 3}
    assert first["metrics"]["compile"]["blocked"] == 2
    assert first["metrics"]["compile"]["pass_rate_reached"] == 1
    passing = next(row for row in first["cases"] if row["steps"]["compile"]["state"] == "pass")
    assert "canonical/manifest.json" in passing["artifacts"]
    assert "bundle/references/source.xml" in passing["artifacts"]
    assert all(row["state"] == "pass" for row in passing["steps"].values())
    assert set(p.name for p in (tmp_path / "first").iterdir()) == {"measurement.json", "measurement.md", "run.local.json"}
    assert "EGOV_XML_PARSE" in (tmp_path / "first/measurement.md").read_text()
    assert str(tmp_path) not in (tmp_path / "first/measurement.json").read_text()
    with pytest.raises(AssuranceError, match="OUTPUT_EXISTS"):
        survey(tmp_path / "inventory/inventory.local.json", root, lock, FIXED_TIME, tmp_path / "first")


def test_zero_denominators_are_null():
    assert all(row["pass_rate_all"] is None and row["pass_rate_reached"] is None for row in metrics([]).values())
    assert all(row["reason_counts"] == {s: {} for s in ("pass", "fail", "blocked", "error")} for row in metrics([]).values())


@pytest.mark.parametrize("path", ["C:/outside.xml", "C:outside.xml", "c:/outside.xml", "nested/C:outside.xml"])
def test_inventory_mapping_refuses_windows_drive_paths(tmp_path, path):
    with pytest.raises(AssuranceError, match="PATH_TRAVERSAL"):
        build_inventory(make_inputs(tmp_path), {path: "SyntheticLaw001"})


@pytest.mark.parametrize("malformation", ["null-step", "active", "code", "artifacts", "envelope"])
def test_malformed_worker_protocol_keeps_survey_denominators_and_cleans(tmp_path, monkeypatch, malformation):
    from jlegal_okf.assurance import survey as module
    root = make_inputs(tmp_path)
    (root / "bad.xml").write_text("<broken")
    inventory(root, tmp_path / "inventory")
    lock = make_lock(tmp_path)
    temporary = []
    def broken(argv, **kwargs):
        result_file = Path(argv[argv.index("--result-file") + 1])
        temporary.append(result_file.parent)
        value = {"steps": module.empty_steps(), "artifacts": {}}
        if malformation == "null-step":
            value["steps"]["compile"] = None
        elif malformation == "active":
            value["active_step"] = "not-a-stage"
        elif malformation == "code":
            value["steps"]["admission"]["code"] = "/sensitive/path"
        elif malformation == "artifacts":
            value["artifacts"] = {"/sensitive/path": "0" * 64}
        else:
            value["private_text"] = "must not escape"
        write_json(result_file, value)
        return subprocess.CompletedProcess(argv, 1)
    monkeypatch.setattr(module.subprocess, "run", broken)
    report = survey(tmp_path / "inventory/inventory.local.json", root, lock, FIXED_TIME, tmp_path / "report")
    assert report["metrics"]["admission"]["all_units"] == 2
    assert report["metrics"]["admission"]["error"] == 2
    assert report["metrics"]["admission"]["reason_counts"]["error"] == {"WORKER_PROTOCOL": 2}
    assert report["metrics"]["compile"]["blocked"] == 2
    assert all(set(case["steps"]) == set(module.STEPS) for case in report["cases"])
    assert all(not path.exists() for path in temporary)
    assert "sensitive" not in canonical_bytes(report).decode()


def test_reason_counts_group_mixed_states_without_counting_duplicate_occurrences(tmp_path):
    from jlegal_okf.assurance.reporting import STEPS, write_report
    cases = []
    for state, code in (("fail", "EGOV_XML_PARSE"), ("fail", "EGOV_XML_PARSE"), ("fail", "EGOV_XML_LAW_ID_REQUIRED"), ("error", "TIMEOUT")):
        steps = {step: {"state": "blocked", "code": "PREREQUISITE"} for step in STEPS}
        steps["admission"] = {"state": state, "code": code}
        cases.append({"unit_id": str(len(cases)), "occurrences": 3, "steps": steps})
    summary = metrics(cases)
    assert summary["admission"]["all_units"] == 4
    assert summary["admission"]["reason_counts"]["fail"] == {"EGOV_XML_LAW_ID_REQUIRED": 1, "EGOV_XML_PARSE": 2}
    assert summary["admission"]["reason_counts"]["error"] == {"TIMEOUT": 1}
    assert summary["compile"]["reason_counts"]["blocked"] == {"PREREQUISITE": 4}
    write_report(tmp_path, {"metrics": summary, "cases": cases})
    assert "| admission | fail | EGOV_XML_PARSE | 2 |" in (tmp_path / "measurement.md").read_text()


def test_worker_exception_is_error_and_details_stay_private(tmp_path, monkeypatch):
    from jlegal_okf.assurance import survey as module
    def crash(*args, **kwargs):
        raise RuntimeError("sensitive-law-text /private/path")
    monkeypatch.setattr(module, "admit_egov_xml", crash)
    run_worker(FIXTURE, "SyntheticLaw001", FIXED_TIME, "test", tmp_path, tmp_path / "result.json")
    report = json.loads((tmp_path / "result.json").read_text())
    assert report["steps"]["admission"] == {"state": "error", "code": "RUNTIME_EXCEPTION"}
    assert "sensitive" not in canonical_bytes(report).decode()


def test_timeout_cleans_artifacts_and_does_not_misclassify(tmp_path, monkeypatch):
    from jlegal_okf.assurance import survey as module
    seen = []
    def timeout(argv, **kwargs):
        root = Path(argv[argv.index("--work-dir") + 1])
        seen.append(root)
        (root / "partial.xml").write_text("private transient source")
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
    monkeypatch.setattr(module.subprocess, "run", timeout)
    result = _run_case(FIXTURE, {"unit_id": "0" * 64, "law_id": "SyntheticLaw001"}, FIXED_TIME, .01)
    assert result["steps"]["admission"] == {"state": "error", "code": "TIMEOUT"}
    assert result["steps"]["compile"]["state"] == "blocked"
    assert seen and all(not path.exists() for path in seen)


def test_unknown_tag_diagnostic_does_not_echo_input(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text(FIXTURE.read_text().replace("<MainProvision>", "<MainProvision><SecretInternalTag><Article/></SecretInternalTag>"))
    run_worker(source, "SyntheticLaw001", FIXED_TIME, "test", tmp_path, tmp_path / "result.json")
    report = json.loads((tmp_path / "result.json").read_text())
    assert report["steps"]["admission"]["state"] == "fail"
    assert "SecretInternalTag" not in canonical_bytes(report).decode()
    assert report["steps"]["admission"]["code"] == "EGOV_XML_UNSUPPORTED_STRUCTURE:UNKNOWN"


def test_worker_checks_actual_import_identity_before_measuring(tmp_path):
    run_worker(FIXTURE, "SyntheticLaw001", FIXED_TIME, "test", tmp_path,
               tmp_path / "result.json", expected_tree_sha256="0" * 64)
    report = json.loads((tmp_path / "result.json").read_text())
    assert report["steps"]["admission"] == {"state": "error", "code": "WORKER_IMPLEMENTATION_MISMATCH"}
    assert not (tmp_path / "first").exists()


def test_cli_measured_failure_and_runtime_exit_codes(tmp_path):
    root = make_inputs(tmp_path)
    (root / "bad.xml").write_text("<broken")
    inventory(root, tmp_path / "inventory")
    lock = make_lock(tmp_path)
    result = subprocess.run([sys.executable, "-m", "jlegal_okf.assurance", "survey",
                             "--inventory", str(tmp_path / "inventory/inventory.local.json"),
                             "--input-root", str(root), "--implementation-lock", str(lock),
                             "--converted-at", FIXED_TIME, "--out-dir", str(tmp_path / "out")],
                            capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["passed"] is False
    result = subprocess.run([sys.executable, "-m", "jlegal_okf.assurance", "inventory",
                             "--input-dir", str(root), "--out-dir", str(tmp_path / "inventory")], capture_output=True, text=True)
    assert result.returncode == 2
    assert "OUTPUT_EXISTS" in result.stderr and str(tmp_path) not in result.stderr


def test_compile_cli_fixed_time_covers_manifest_and_bundle(tmp_path):
    from jlegal_okf.cli import main
    from jlegal_okf.assurance.contracts import tree_hashes
    for name in ("a", "b"):
        root = tmp_path / name
        assert main(["compile", str(FIXTURE), "--adapter", "egov_xml", "--corpus-id", "fixed",
                     "--converted-at", FIXED_TIME, "--out-dir", str(root / "canonical")]) == 0
        assert main(["export-okf", "--corpus", str(root / "canonical/corpus.jsonl"),
                     "--manifest", str(root / "canonical/manifest.json"), "--source", str(FIXTURE),
                     "--out-dir", str(root / "bundle")]) == 0
    assert tree_hashes(tmp_path / "a") == tree_hashes(tmp_path / "b")


def test_inventory_keeps_size_depth_elements_and_empty_in_denominator(tmp_path, monkeypatch):
    from jlegal_okf import egov, input_limits

    root = tmp_path / "inputs"
    root.mkdir()
    fragments = {
        "plain.xml": b'<Law LawId="Invented001"/>',
        "empty.xml": b"",
        "syntax.xml": b"<broken",
        "dtd.xml": b"<!DOCTYPE Law><Law/>",
        "size.xml": b" " * 257,
        "depth.xml": b"<a><b><c><d/></c></b></a>",
        "elements.xml": b"<a><b/><b/><b/><b/></a>",
    }
    for name, raw in fragments.items():
        (root / name).write_bytes(raw)
    monkeypatch.setattr(egov, "MAX_EGOV_XML_BYTES", 256)
    monkeypatch.setattr(input_limits, "MAX_XML_DEPTH", 3)
    monkeypatch.setattr(input_limits, "MAX_XML_ELEMENTS", 4)
    local, dataset = build_inventory(root)
    assert dataset["files"] == dataset["unique_units"] == 7
    assert {row["path"]: row["identity_status"] for row in local["files"]} == {
        "plain.xml": "IDENTIFIED", "empty.xml": "INVALID_XML", "syntax.xml": "INVALID_XML",
        "dtd.xml": "INVALID_XML", "size.xml": "INPUT_TOO_LARGE",
        "depth.xml": "INPUT_XML_DEPTH_LIMIT", "elements.xml": "INPUT_XML_ELEMENT_LIMIT",
    }


@pytest.mark.parametrize("constant,code", [
    ("MAX_XML_DEPTH", "INPUT_XML_DEPTH_LIMIT"),
    ("MAX_XML_ELEMENTS", "INPUT_XML_ELEMENT_LIMIT"),
])
def test_survey_preserves_safe_limit_diagnostics_only(tmp_path, monkeypatch, constant, code):
    from jlegal_okf import input_limits
    from jlegal_okf.assurance import survey as module
    from jlegal_okf.errors import AdapterError

    monkeypatch.setattr(input_limits, constant, 1)
    run_worker(FIXTURE, "SyntheticLaw001", FIXED_TIME, "test", tmp_path, tmp_path / "result.json")
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["steps"]["admission"] == {"state": "fail", "code": code}
    assert module._worker_envelope(result)
    assert all(row == {"state": "blocked", "code": "PREREQUISITE"}
               for name, row in result["steps"].items() if name != "admission")
    assert metrics([result])["admission"]["all_units"] == 1
    assert module._diagnostic(AdapterError(code + ":must-not-escape")) == code
    assert module._diagnostic(AdapterError("UNKNOWN:must-not-escape")) == "CONTRACT_REJECTED"
    result["steps"]["admission"]["code"] = code + ":must-not-escape"
    assert not module._worker_envelope(result)
