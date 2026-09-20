"""Opt-in pinned third-party judgment, separate from profile compliance."""

from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import subprocess

from .contracts import (AssuranceError, canonical_bytes, digest, file_digest, new_output,
                        read_json, reject_symlinks, safe_child, tree_hashes, write_json)

TOOL_REPOSITORY = "https://github.com/Sudhakaran88/okf-conformance"
TOOL_REVISION = "3e958ae965bf9673fc291859a44feb05a60a9748"
SPEC_REVISION = "ad30107c31c06aec8a7d5636e0d1058118604e6f"
TOOL_FILES = {
    "validator/okf-validate.mjs": "d4b3a0ee9c2f486cdb5b853304bd0af8b36cf3c6af41de60589f117f2413eb99",
    "validator/okf-graph.mjs": "e58b90c9139fa3a3943161d57a048f233562ff95ce7f5874e83e2fb0a33b8373",
}


def verify_tool(tool_root: Path, lock_file: Path) -> dict:
    lock = read_json(lock_file)
    if (lock.get("schema") != "jlegal-external-tools-lock/v1"
            or lock.get("repository") != TOOL_REPOSITORY or lock.get("revision") != TOOL_REVISION
            or lock.get("files") != TOOL_FILES or lock.get("entrypoint") != "validator/okf-validate.mjs"
            or lock.get("official_spec_revision") != SPEC_REVISION):
        raise AssuranceError("EXTERNAL_LOCK_MISMATCH")
    reject_symlinks(tool_root)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    revision = subprocess.run(["git", "-C", str(tool_root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False, timeout=10, env=env)
    if revision.returncode or revision.stdout.strip() != TOOL_REVISION:
        raise AssuranceError("EXTERNAL_REVISION_MISMATCH")
    for name, sha in TOOL_FILES.items():
        if file_digest(safe_child(tool_root, name)) != sha:
            raise AssuranceError("EXTERNAL_CODE_MISMATCH")
    return {"repository": TOOL_REPOSITORY, "revision": TOOL_REVISION, "files": TOOL_FILES,
            "lock_sha256": file_digest(lock_file), "official_spec_revision": SPEC_REVISION}


def _judgment(raw: bytes, returncode: int) -> dict:
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("large report")
    value = json.loads(raw)
    if (type(value) is not dict or type(value.get("conformant")) is not bool
            or type(value.get("pass")) is not bool or value.get("strict") is not False
            or value.get("okfVersion") != "0.2"):
        raise ValueError("shape")
    rules = {}
    for name, prefix in (("errors", "M"), ("warnings", "S")):
        items = value.get(name)
        if not isinstance(items, list) or any(type(row) is not dict or not re.fullmatch(prefix + "[1-6]", str(row.get("rule"))) for row in items):
            raise ValueError("rules")
        rules[name] = dict(sorted(Counter(row["rule"] for row in items).items()))
    conforms = len(value["errors"]) == 0
    if value["conformant"] != conforms or value["pass"] != conforms or returncode != (0 if conforms else 1):
        raise ValueError("inconsistent status")
    summary = value.get("summary")
    if not isinstance(summary, dict) or any(type(summary.get(key)) is not int or summary[key] < 0 for key in ("concepts", "reserved", "links", "errors", "warnings")):
        raise ValueError("summary")
    if summary["errors"] != len(value["errors"]) or summary["warnings"] != len(value["warnings"]):
        raise ValueError("counts")
    return {"conformant": conforms, "summary": {k: summary[k] for k in ("concepts", "reserved", "links", "errors", "warnings")}, "rule_counts": rules}


def external(tool_root: Path, tool_lock: Path, bundle: Path, out_dir: Path,
             timeout_seconds: float = 120) -> dict:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise AssuranceError("TIMEOUT_POSITIVE_REQUIRED")
    identity = verify_tool(tool_root, tool_lock)
    before = tree_hashes(bundle)
    # Outputs inside the observed bundle would invalidate read-only evidence.
    if out_dir.absolute().is_relative_to(bundle.absolute()):
        raise AssuranceError("OUTPUT_WITHIN_BUNDLE")
    new_output(out_dir)
    env = {k: v for k, v in os.environ.items() if k not in {"NODE_OPTIONS", "NODE_PATH"}}
    report = {"schema": "jlegal-external-result/v1", "tool": identity,
              "official_compliance": "not-established", "state": "error", "code": "TOOL_RUNTIME",
              "judgment": None, "bundle_before_sha256": digest(canonical_bytes(before)),
              "bundle_unchanged": False, "passed": False, "node_version": None}
    try:
        runtime = subprocess.run(["node", "--version"], capture_output=True, timeout=10, check=False, env=env)
        version = runtime.stdout.decode("ascii").strip()
        if runtime.returncode or not re.fullmatch(r"v\d+\.\d+\.\d+", version):
            raise ValueError("node runtime")
        report["node_version"] = version
        process = subprocess.run(["node", str(safe_child(tool_root.absolute(), "validator/okf-validate.mjs")),
                                  str(bundle.absolute()), "--json"], stdin=subprocess.DEVNULL,
                                 capture_output=True, timeout=timeout_seconds, check=False, env=env)
        report["judgment"] = _judgment(process.stdout, process.returncode)
        report["state"] = "pass" if report["judgment"]["conformant"] else "fail"
        report["code"] = "OK" if report["state"] == "pass" else "TOOL_REJECTED"
    except subprocess.TimeoutExpired:
        report["code"] = "TIMEOUT"
    except (ValueError, UnicodeError):
        report["code"] = "TOOL_JSON_INVALID"
    except OSError:
        report["code"] = "TOOL_START_FAILED"
    try:
        after = tree_hashes(bundle)
        report["bundle_unchanged"] = before == after
        report["bundle_after_sha256"] = digest(canonical_bytes(after))
    except (OSError, AssuranceError):
        report["bundle_after_sha256"] = None
    if not report["bundle_unchanged"]:
        report["state"], report["code"] = "error", "BUNDLE_MUTATED"
    report["passed"] = report["state"] == "pass"
    write_json(out_dir / "external.json", report)
    return report
