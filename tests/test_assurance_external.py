"""Exercise external integration with process stubs, never external code."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from jlegal_okf.assurance import external as module
from jlegal_okf.assurance.contracts import AssuranceError, write_json

LOCK = Path(__file__).resolve().parents[1] / "examples/conformance/external-tools.lock.json"


def judgment(pass_result=True):
    errors = [] if pass_result else [{"rule": "M2", "file": "/sensitive/path", "message": "private source text"}]
    return {"okfVersion": "0.2", "strict": False, "conformant": pass_result, "pass": pass_result,
            "summary": {"concepts": 1, "reserved": 0, "links": 0, "errors": len(errors), "warnings": 0},
            "errors": errors, "warnings": []}


@pytest.mark.parametrize("mode", ["pass", "fail", "timeout", "invalid", "mutation", "contradiction"])
def test_external_reports_judgment_failure_and_tree_mutation(tmp_path, monkeypatch, mode):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "index.md").write_text("fixture")
    monkeypatch.setattr(module, "verify_tool", lambda *args: {"revision": module.TOOL_REVISION})
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv == ["node", "--version"]:
            return subprocess.CompletedProcess(argv, 0, b"v22.0.0\n", b"")
        assert argv[-1] == "--json" and isinstance(argv, list)
        if mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        if mode == "mutation":
            (bundle / "index.md").write_text("changed")
        payload = judgment(mode != "fail")
        code = 1 if mode == "fail" else 0
        if mode == "contradiction":
            code = 1
        stdout = b"not json /sensitive/path" if mode == "invalid" else json.dumps(payload).encode()
        return subprocess.CompletedProcess(argv, code, stdout, b"private stderr")
    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.external(tmp_path / "tools", LOCK, bundle, tmp_path / "report", 1)
    assert result["passed"] is (mode == "pass")
    assert result["official_compliance"] == "not-established"
    assert result["bundle_unchanged"] is (mode != "mutation")
    assert len(calls) == 2
    content = (tmp_path / "report/external.json").read_text()
    assert "sensitive" not in content and "private" not in content
    if mode == "fail":
        assert result["state"] == "fail"
        assert result["judgment"]["rule_counts"]["errors"] == {"M2": 1}
    elif mode != "pass":
        assert result["state"] == "error"


def test_forged_external_lock_fails_before_execution(tmp_path, monkeypatch):
    value = json.loads(LOCK.read_text())
    value["files"]["validator/okf-validate.mjs"] = "0" * 64
    lock = tmp_path / "forged.json"
    write_json(lock, value)
    def forbidden(*args, **kwargs):
        pytest.fail("no process may execute for a forged lock")
    monkeypatch.setattr(module.subprocess, "run", forbidden)
    with pytest.raises(AssuranceError, match="EXTERNAL_LOCK_MISMATCH"):
        module.verify_tool(tmp_path, lock)


def test_external_actual_code_hash_must_match_even_when_revision_matches(tmp_path, monkeypatch):
    (tmp_path / "validator").mkdir()
    (tmp_path / "validator/okf-validate.mjs").write_text("modified")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, module.TOOL_REVISION + "\n", ""))
    with pytest.raises(AssuranceError, match="EXTERNAL_CODE_MISMATCH"):
        module.verify_tool(tmp_path, LOCK)


def test_external_rejects_report_inside_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "verify_tool", lambda *a: {})
    with pytest.raises(AssuranceError, match="OUTPUT_WITHIN_BUNDLE"):
        module.external(tmp_path, LOCK, tmp_path, tmp_path / "report")
