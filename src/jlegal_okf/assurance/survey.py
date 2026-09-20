"""Sequential bounded subprocess measurement of frozen local source units."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from ..egov import admit_egov_xml
from ..errors import JLegalError
from ..legal_okf import export_okf, validate_okf
from ..pipeline import _canonical_utc_timestamp, compile_corpus, read_crosswalk, read_jsonl, verify_manifest
from ..validation import validate_corpus
from .contracts import (AssuranceError, canonical_bytes, digest, file_digest, new_output,
                        implementation_identity, read_json, safe_child, tree_hashes,
                        verify_implementation_lock, write_json)
from .inventory import verify_inventory
from .reporting import STEPS, metrics, write_report


_DIAGNOSTICS = frozenset({
    "EGOV_XML_INPUT_EMPTY", "EGOV_XML_INPUT_TOO_LARGE", "EGOV_XML_DTD_OR_ENTITY_FORBIDDEN",
    "EGOV_XML_PARSE", "EGOV_XML_API_ERROR", "EGOV_XML_ROOT", "EGOV_XML_LAW_FULL_TEXT",
    "EGOV_XML_LAW_MISSING", "EGOV_XML_LAW_INFO", "EGOV_XML_LAW_ID_REQUIRED",
    "EGOV_XML_LAW_ID_MISMATCH", "EGOV_XML_LAW_BODY_MISSING", "EGOV_XML_STRUCTURE_EMPTY",
    "EGOV_XML_UNSUPPORTED_STRUCTURE", "EGOV_XML_PROMULGATION_CONFLICT",
})


def _diagnostic(exc: JLegalError) -> str:
    code = str(exc).split(":", 1)[0]
    if code == "EGOV_XML_UNSUPPORTED_STRUCTURE":
        tag = "NewProvision" if str(exc) == code + ":NewProvision" else "UNKNOWN"
        return code + ":" + tag
    return code if code in _DIAGNOSTICS else "CONTRACT_REJECTED"


def empty_steps() -> dict:
    return {step: {"state": "blocked", "code": "PREREQUISITE"} for step in STEPS}


def _worker_envelope(value: dict) -> bool:
    """Accept only the bounded internal protocol, never arbitrary child output."""
    if not {"steps", "artifacts"} <= value.keys() or set(value) - {"steps", "artifacts", "active_step"}:
        return False
    steps, artifacts = value["steps"], value["artifacts"]
    codes = _DIAGNOSTICS | {"OK", "PREREQUISITE", "CONTRACT_REJECTED", "REPRODUCIBILITY_MISMATCH",
                            "RUNTIME_EXCEPTION", "WORKER_IMPLEMENTATION_MISMATCH",
                            "EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision", "EGOV_XML_UNSUPPORTED_STRUCTURE:UNKNOWN"}
    if type(steps) is not dict or set(steps) != set(STEPS):
        return False
    for item in steps.values():
        if (type(item) is not dict or set(item) != {"state", "code"}
                or type(item["state"]) is not str or item["state"] not in {"pass", "fail", "blocked", "error"}
                or type(item["code"]) is not str or item["code"] not in codes):
            return False
        if (item["state"] == "pass") != (item["code"] == "OK") or (item["state"] == "blocked") != (item["code"] == "PREREQUISITE"):
            return False
    if "active_step" in value and (type(value["active_step"]) is not str or value["active_step"] not in STEPS):
        return False
    if type(artifacts) is not dict:
        return False
    artifact_path = re.compile(r"(?:canonical/(?:corpus|crosswalk|projection)\.jsonl|canonical/manifest\.json|bundle/(?:canonical/(?:corpus|crosswalk|projection)\.jsonl|canonical/manifest\.json|manifest\.json|index\.md|references/source\.xml|derived/knowledge\.md|source/ver_[0-9a-f-]+\.md))\Z")
    return all(type(name) is str and artifact_path.fullmatch(name)
               and type(sha) is str and re.fullmatch(r"[0-9a-f]{64}", sha)
               for name, sha in artifacts.items())


def run_worker(source: Path, law_id: str | None, converted_at: str, corpus_id: str,
               work_dir: Path, result_file: Path, expected_tree_sha256: str | None = None) -> None:
    """Private subprocess protocol. Never persist exception messages or source text."""
    result = {"steps": empty_steps(), "artifacts": {}}
    if expected_tree_sha256 is not None and implementation_identity()["package_tree_sha256"] != expected_tree_sha256:
        result["steps"]["admission"] = {"state": "error", "code": "WORKER_IMPLEMENTATION_MISMATCH"}
        write_json(result_file, result)
        return
    write_json(result_file, result)
    first, second = work_dir / "first", work_dir / "second"
    mapping = {"law_id": law_id} if law_id else None

    def compile_at(root: Path) -> dict:
        return compile_corpus(source, adapter="egov_xml", out_dir=root / "canonical",
                              corpus_id=corpus_id, mapping=mapping, converted_at=converted_at)

    def verify_at(root: Path) -> dict:
        manifest = verify_manifest(root / "canonical/corpus.jsonl", root / "canonical/manifest.json",
                                   verify_inputs=True, source=source)
        validate_corpus(read_jsonl(root / "canonical/corpus.jsonl"),
                        read_crosswalk(root / "canonical/crosswalk.jsonl"))
        return manifest

    def export_at(root: Path) -> dict:
        return export_okf(root / "canonical/corpus.jsonl", root / "canonical/manifest.json",
                          root / "bundle", source=source)

    def repeat() -> None:
        compile_at(second)
        verify_at(second)
        export_at(second)
        validate_okf(second / "bundle", verify_source=True)
        first_hashes, second_hashes = tree_hashes(first), tree_hashes(second)
        result["artifacts"] = first_hashes
        if first_hashes != second_hashes:
            raise JLegalError("REPRODUCIBILITY_MISMATCH")

    actions = (
        lambda: admit_egov_xml(source, law_id=law_id), lambda: compile_at(first),
        lambda: verify_at(first), lambda: export_at(first),
        lambda: validate_okf(first / "bundle", verify_source=True), repeat,
    )
    for step, action in zip(STEPS, actions):
        result["active_step"] = step
        write_json(result_file, result)
        try:
            action()
        except JLegalError as exc:
            code = "REPRODUCIBILITY_MISMATCH" if str(exc) == "REPRODUCIBILITY_MISMATCH" else _diagnostic(exc)
            result["steps"][step] = {"state": "fail", "code": code}
            break
        except Exception:
            result["steps"][step] = {"state": "error", "code": "RUNTIME_EXCEPTION"}
            break
        else:
            result["steps"][step] = {"state": "pass", "code": "OK"}
    result.pop("active_step", None)
    write_json(result_file, result)


def _run_case(source: Path, unit: dict, converted_at: str, timeout_seconds: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="jlegal-measure-") as temp:
        work = Path(temp)
        result_file = work / "result.json"
        argv = [sys.executable, "-m", "jlegal_okf.assurance", "_worker", "--source", str(source),
                "--converted-at", converted_at, "--corpus-id", "survey-" + unit["unit_id"],
                "--work-dir", str(work), "--result-file", str(result_file),
                "--expected-tree-sha256", implementation_identity()["package_tree_sha256"]]
        if unit["law_id"]:
            argv.extend(["--law-id", unit["law_id"]])
        error = None
        try:
            process = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, timeout=timeout_seconds, check=False,
                                     env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            if process.returncode:
                error = "WORKER_EXIT"
        except subprocess.TimeoutExpired:
            error = "TIMEOUT"
        except OSError:
            error = "WORKER_START"
        result = {"steps": empty_steps(), "artifacts": {}}
        if result_file.is_file():
            try:
                result = read_json(result_file)
                if not _worker_envelope(result):
                    raise ValueError
            except (ValueError, KeyError, TypeError, OSError):
                result = {"steps": empty_steps(), "artifacts": {}}
                error = "WORKER_PROTOCOL"
        elif not error:
            error = "WORKER_PROTOCOL"
        if error:
            active = result.get("active_step", next((s for s in STEPS if result["steps"][s]["state"] != "pass"), STEPS[-1]))
            result["steps"][active] = {"state": "error", "code": error}
        result.pop("active_step", None)
        return result


def survey(inventory: Path, input_root: Path, implementation_lock: Path,
           converted_at: str, out_dir: Path, timeout_seconds: float = 120) -> dict:
    if not _canonical_utc_timestamp(converted_at):
        raise AssuranceError("CONVERTED_AT_UTC_REQUIRED")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise AssuranceError("TIMEOUT_POSITIVE_REQUIRED")
    frozen, dataset = verify_inventory(inventory, input_root)
    implementation = verify_implementation_lock(implementation_lock)
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    new_output(out_dir)
    by_unit = {}
    for row in frozen["files"]:
        by_unit.setdefault(row["unit_id"], row)
    cases = []
    for unit in dataset["units"]:
        source = safe_child(input_root, by_unit[unit["unit_id"]]["path"])
        if file_digest(source) != unit["source_sha256"]:
            raise AssuranceError("INPUT_CHANGED")
        if unit["identity_status"] in {"INVALID_ID", "CONFLICTING_ID"}:
            result = {"steps": empty_steps(), "artifacts": {}}
            result["steps"]["admission"] = {"state": "fail", "code": unit["identity_status"]}
        else:
            result = _run_case(source, unit, converted_at, timeout_seconds)
        if file_digest(source) != unit["source_sha256"]:
            raise AssuranceError("INPUT_CHANGED")
        cases.append({**unit, **result})
    # Also catch additions/deletions and changed duplicate inputs during processing.
    current, current_dataset = verify_inventory(inventory, input_root)
    if current != frozen or current_dataset != dataset:
        raise AssuranceError("INVENTORY_CHANGED")
    if verify_implementation_lock(implementation_lock) != implementation:
        raise AssuranceError("IMPLEMENTATION_CHANGED")
    report = {"schema": "jlegal-measurement/v1", "dataset": dataset,
              "dataset_sha256": frozen["dataset_sha256"], "implementation": implementation,
              "recipe": {"adapter": "egov_xml", "converted_at": converted_at,
                         "corpus_id": "survey-<unit_id>", "mapping": {"law_id": "<explicit unit law_id>"},
                         "acquisition": None, "rights": None, "verify_inputs": True,
                         "verify_source": True, "repeat_runs": 2, "timeout_seconds": timeout_seconds},
              "metrics": metrics(cases), "cases": cases,
              "passed": bool(cases) and all(r["state"] == "pass" for c in cases for r in c["steps"].values())}
    write_report(out_dir, report)
    write_json(out_dir / "run.local.json", {"schema": "jlegal-survey-run/v1", "started_at": started,
               "elapsed_seconds": time.monotonic() - start, "temporary_artifacts_cleaned": True,
               "measurement_sha256": digest(canonical_bytes(report))})
    return report
