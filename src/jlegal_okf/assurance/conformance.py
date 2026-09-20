"""Artifact-only, bounded conformance checks independent of the producer.

No adapters, model constructors, pipeline, or reference validator are imported.
The catalog is trusted review material; submissions are untrusted artifacts.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import unicodedata
import uuid

import yaml


PROFILE = "J-LEGAL-OKF/0.2.0-draft"
NAMESPACE = uuid.UUID("9b7b7100-8305-5e41-b8d4-e541ce517491")
LAYERS = ("okf_format", "profile", "jori_byte_regression")
LIMIT = 16 * 1024 * 1024
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _require(value: bool, code: str) -> None:
    if not value:
        raise ValueError(code)


def _plain_path(path: Path) -> Path:
    path = path.absolute()
    _require(not any(part.is_symlink() for part in (path, *path.parents)), "UNSAFE_PATH")
    return path


def _relative(root: Path, value: object, *, directory: bool = False) -> Path:
    _require(isinstance(value, str) and bool(value), "UNSAFE_PATH")
    relative = PurePosixPath(value)
    _require(not relative.is_absolute() and not PureWindowsPath(value).drive and all(p not in {"", ".", ".."} and ":" not in p for p in value.split("/")) and "\\" not in value and "\x00" not in value, "UNSAFE_PATH")
    path = _plain_path(root / relative)
    _require(path.resolve().is_relative_to(root.resolve()), "UNSAFE_PATH")
    _require(path.is_dir() if directory else path.is_file(), "ARTIFACT_MISSING")
    if not directory:
        _require(stat.S_ISREG(path.stat().st_mode), "UNSAFE_PATH")
    return path


def _bytes(path: Path) -> bytes:
    _plain_path(path)
    _require(stat.S_ISREG(path.stat().st_mode) and path.stat().st_size <= LIMIT, "ARTIFACT_SIZE")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    _require(len(raw) <= LIMIT, "ARTIFACT_SIZE")
    return raw


def _pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _parse(raw: bytes | str) -> object:
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: _require(False, "JSON_CONSTANT"))


def _json(path: Path) -> dict:
    value = _parse(_bytes(path))
    _require(type(value) is dict, "JSON_OBJECT")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(prefix: str, payload: dict) -> str:
    return prefix + str(uuid.uuid5(NAMESPACE, _sha(_canonical(payload))))


def _norm(value: str, lower: bool = False) -> str:
    result = re.sub(r"[\t\n\r\f\v ]+", " ", unicodedata.normalize("NFKC", value).strip())
    return result.lower() if lower else result


def _tree(root: Path) -> dict[str, Path]:
    result = {}
    _plain_path(root)
    for path in root.rglob("*"):
        _plain_path(path)
        if path.is_dir():
            continue
        _require(stat.S_ISREG(path.stat().st_mode), "UNSAFE_PATH")
        result[path.relative_to(root).as_posix()] = path
        _require(len(result) <= 1024, "ARTIFACT_COUNT")
    return result


def _frontmatter(raw: bytes) -> tuple[dict, str]:
    text = raw.decode("utf-8").replace("\r\n", "\n")
    lines = text.splitlines(keepends=True)
    _require(bool(lines) and lines[0].strip() == "---", "FRONTMATTER")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    _require(end is not None, "FRONTMATTER")
    value = yaml.safe_load("".join(lines[1:end]))
    _require(type(value) is dict, "FRONTMATTER")
    return value, "".join(lines[end + 1:])


def check_okf_format(bundle: Path) -> list[str]:
    """Check the fixed specification's §11 floor, not optional-family policy.

    No index, optional metadata, known type, or working link is required.
    Reserved-file checks cover frontmatter placement and date headings;
    editorial quality and prose meaning are outside this mechanical check.
    """
    errors = []
    for name, path in sorted(_tree(bundle).items()):
        if not name.endswith(".md"):
            continue
        try:
            raw = _bytes(path)
            text = raw.decode("utf-8")
            if path.name == "index.md":
                if text.startswith("---"):
                    value, _ = _frontmatter(raw)
                    _require(name == "index.md" and set(value) == {"okf_version"}, "OKF_INDEX")
            elif path.name == "log.md":
                _require(not text.startswith("---"), "OKF_LOG")
                for line in text.splitlines():
                    if line.startswith("## "):
                        value = line[3:].strip()
                        _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, "OKF_LOG_DATE")
                        _require(date.fromisoformat(value).isoformat() == value, "OKF_LOG_DATE")
            else:
                value, _ = _frontmatter(raw)
                _require(isinstance(value.get("type"), str) and bool(value["type"].strip()), "OKF_TYPE")
        except (ValueError, UnicodeError, yaml.YAMLError):
            errors.append("OKF_DOCUMENT")
    return sorted(set(errors))


def _records(path: Path) -> list[dict]:
    values = [_parse(line) for line in _bytes(path).splitlines() if line.strip()]
    _require(all(type(value) is dict for value in values), "RECORD_SHAPE")
    return values


def _source_payload_matches(body: str, node: dict) -> bool:
    """Bind an explicitly marked payload without requiring producer headings."""
    if "<!-- jlegal-source:" not in body:
        # Markerless presentation has only bounded presence coverage.
        return node["text"] in body
    begin = f"<!-- jlegal-source:{node['version_id']}:begin -->"
    end = f"<!-- jlegal-source:{node['version_id']}:end -->"
    if body.count("<!-- jlegal-source:") != 2 or body.count(begin) != 1 or body.count(end) != 1:
        return False
    start, finish = body.index(begin) + len(begin), body.index(end)
    return finish >= start and body[start:finish] == node["text"]


def _profile(bundle: Path, expected: dict, case: dict) -> tuple[list[str], dict[str, dict]]:
    errors = []

    def check(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    files = _tree(bundle)
    required = {"canonical/corpus.jsonl", "canonical/manifest.json", "canonical/crosswalk.jsonl", "canonical/projection.jsonl", "references/source.xml", "manifest.json"}
    if not required <= files.keys():
        return ["PROFILE_FILES"], {}
    nodes = _records(files["canonical/corpus.jsonl"])
    by_locator = {n["locator"]: n for n in nodes}
    check(len(by_locator) == len(nodes) == len(expected["nodes"]), "NODE_SET")
    check(set(by_locator) == {e["locator"] for e in expected["nodes"]}, "NODE_SET")
    check(len({n["node_id"] for n in nodes}) == len(nodes), "NODE_ID_DUPLICATE")
    source_hash = case["source_sha256"]
    check(_sha(_bytes(files["references/source.xml"])) == source_hash, "SOURCE_BYTES")
    law_id = _identity("law_", {"jurisdiction": _norm(expected["jurisdiction"], True), "authority": _norm(expected["authority"], True), "key_kind": "source_law", "key": expected["source_law_key"]})
    source = {"uri": "jlegal:source:sha256:" + source_hash, "sha256": source_hash, "source_key": case["official_law_id"], "adapter": "egov_xml", "page": None, "byte_start": None, "byte_end": None}
    for fixed in expected["nodes"]:
        node = by_locator.get(fixed["locator"])
        if node is None:
            continue
        check(node.get("schema") == "jori-corpus/v2", "NODE_SCHEMA")
        check(set(node) == {"schema", "jurisdiction", "authority", "law_number_key", "source_law_key", "law_id", "node_id", "version_id", "parent_id", "kind", "locator", "depth", "ordinal", "branch", "heading", "label", "attributes", "text", "temporal", "source"}, "NODE_KEYS")
        for key in ("jurisdiction", "authority", "law_number_key", "source_law_key", "temporal"):
            check(_canonical(node.get(key)) == _canonical(expected[key]), "NODE_" + key.upper())
        for key in ("kind", "depth", "ordinal", "branch", "heading", "label"):
            check(_canonical(node.get(key)) == _canonical(fixed[key]), "NODE_" + key.upper())
        check(node.get("text") == fixed["text"], "NODE_TEXT")
        attributes = node["attributes"]
        check(type(attributes) is dict and all(attributes.get(k) == v for k, v in fixed["attributes"].items()), "NODE_ATTRIBUTES")
        extras = {k: v for k, v in attributes.items() if k not in fixed["attributes"] and k != "build_provenance_sha256"}
        check(all(fixed.get("allowed_extra_attributes", {}).get(k) == v for k, v in extras.items()), "NODE_ATTRIBUTES")
        check(all(isinstance(k, str) and isinstance(v, str) for k, v in attributes.items()), "NODE_ATTRIBUTES")
        if "build_provenance_sha256" in attributes:
            check(isinstance(attributes["build_provenance_sha256"], str) and SHA.fullmatch(attributes["build_provenance_sha256"]) is not None, "BUILD_DIGEST")
        node_id = _identity("node_", {"law_id": law_id, "locator": fixed["locator"]})
        parent = fixed["parent_locator"]
        parent_id = _identity("node_", {"law_id": law_id, "locator": parent}) if parent else None
        check(node["law_id"] == law_id and node["node_id"] == node_id and node["parent_id"] == parent_id, "NODE_IDENTITY")
        version = _identity("ver_", {"node_id": node_id, "temporal": node["temporal"], "text": node["text"], "heading": node["heading"], "label": node["label"], "attributes": sorted(attributes.items())})
        check(node["version_id"] == version, "VERSION_IDENTITY")
        check(node["source"] == source, "SOURCE_IDENTITY")

    projections = _records(files["canonical/projection.jsonl"])
    projection_keys = {"schema", "projection_id", "projection_version", "node_id", "version_id", "law_id", "locator", "heading", "text", "kind", "temporal", "evidence"}
    check(all(p.get("schema") == "jori-projection/v1" and set(p) == projection_keys
              and all(type(p.get(k)) is str and bool(p[k]) for k in ("projection_id", "projection_version", "node_id", "version_id", "law_id", "locator"))
              and (p.get("heading") is None or type(p["heading"]) is str)
              and all(type(p.get(k)) is str for k in ("text", "kind"))
              and all(type(p.get(k)) is dict for k in ("temporal", "evidence"))
              for p in projections), "PROJECTION_SCHEMA")
    projected = {p["node_id"]: p for p in projections}
    substantive = {n["node_id"]: n for n in nodes if n["kind"] != "law"}
    check(len(projected) == len(projections) and set(projected) == set(substantive), "PROJECTION_SET")
    for key in set(projected) & set(substantive):
        check(all(projected[key].get(k) == substantive[key][k] for k in ("node_id", "version_id", "law_id", "locator", "heading", "text", "kind", "temporal")), "PROJECTION_CONTENT")
        check(projected[key].get("evidence") == source, "PROJECTION_SOURCE")
    check(_bytes(files["canonical/crosswalk.jsonl"]) == b"", "CROSSWALK_UNEXPECTED")

    manifest = _json(files["canonical/manifest.json"])
    # These fixed recipes assert no rights. A rights-bearing case requires a
    # separately reviewed v6/v2 recipe; accepting its name alone is insufficient.
    manifest_keys = {"schema", "corpus_id", "node_count", "law_count", "crosswalk_count", "projection_count", "hierarchy_status", "canonicalization", "adapter", "adapter_version", "inputs", "required_input_roles", "build_recipe", "corpus_sha256", "crosswalk_sha256", "projection_sha256", "build_options_sha256", "acquisition", "conversion", "converted_at"}
    check(manifest.get("schema") == "jori-manifest/v5" and set(manifest) == manifest_keys, "MANIFEST_SCHEMA")
    check(all(type(manifest.get(k)) is int and manifest[k] >= 0 for k in ("node_count", "law_count", "crosswalk_count", "projection_count"))
          and all(type(manifest.get(k)) is str and bool(manifest[k]) for k in ("corpus_id", "hierarchy_status", "canonicalization", "adapter", "adapter_version", "converted_at"))
          and all(type(manifest.get(k)) is list for k in ("inputs", "required_input_roles"))
          and all(type(manifest.get(k)) is dict for k in ("build_recipe", "acquisition", "conversion")), "MANIFEST_TYPES")
    check(manifest.get("adapter") == "egov_xml", "MANIFEST_ADAPTER")
    check(manifest.get("converted_at") == case["converted_at"], "CONVERSION_TIME")
    check(manifest.get("corpus_id") == case["corpus_id"], "CORPUS_ID")
    check(manifest.get("node_count") == len(nodes) and manifest.get("projection_count") == len(projections), "MANIFEST_COUNTS")
    conversion = manifest.get("conversion", {})
    check(type(conversion) is dict and conversion.get("profile") == PROFILE and all(isinstance(conversion.get(k), str) and conversion[k] for k in ("name", "version")), "CONVERTER_METADATA")
    inputs = manifest.get("inputs", [])
    check([v for v in inputs if v.get("role") == "source"] == [{"role": "source", "uri": source["uri"], "sha256": source_hash}], "MANIFEST_SOURCE")
    recipe = manifest.get("build_recipe", {})
    check(recipe == {"adapter": "egov_xml", "mapping": {"law_id": case["official_law_id"]}}, "BUILD_RECIPE")
    options = {k: manifest[k] for k in ("adapter", "adapter_version", "canonicalization", "hierarchy_status", "inputs", "required_input_roles", "build_recipe", "acquisition", "conversion")}
    if "rights" in manifest:
        options["rights"] = manifest["rights"]
    check(manifest.get("build_options_sha256") == _sha(_canonical(options)), "BUILD_OPTIONS_DIGEST")
    fingerprint = _sha(_canonical({"build_recipe": recipe, "inputs": sorted(inputs, key=lambda item: (item["role"], item["uri"], item["sha256"]))}))
    check(all(n["attributes"].get("build_provenance_sha256") == fingerprint for n in nodes), "BUILD_PROVENANCE")
    acquisition = manifest.get("acquisition", {})
    check(acquisition.get("official_law_id") == case["official_law_id"] and acquisition.get("sha256") == source_hash, "ACQUISITION_IDENTITY")
    check(acquisition.get("source_url") is None and acquisition.get("retrieved_at") is None, "ACQUISITION_INVENTED")
    for stem in ("corpus", "crosswalk", "projection"):
        check(manifest.get(stem + "_sha256") == _sha(_bytes(files["canonical/" + stem + ".jsonl"])), "CANONICAL_DIGEST")

    bm = _json(files["manifest.json"])
    check(bm.get("profile") == PROFILE and bm.get("schema") == "jlegal-okf-bundle/v1" and "rights" not in bm, "BUNDLE_SCHEMA")
    entries = bm.get("files", [])
    check(len({v["path"] for v in entries}) == len(entries) and {v["path"] for v in entries} == set(files) - {"manifest.json"}, "BUNDLE_FILE_SET")
    for entry in entries:
        path = _relative(bundle, entry["path"])
        check(entry["sha256"] == _sha(_bytes(path)), "BUNDLE_SOURCE_DIGEST" if entry["path"] == "references/source.xml" else "BUNDLE_DIGEST")
    check(bm.get("canonical_corpus_sha256") == _sha(_bytes(files["canonical/corpus.jsonl"])) and bm.get("canonical_manifest_sha256") == _sha(_bytes(files["canonical/manifest.json"])), "BUNDLE_CANONICAL_DIGEST")
    concepts = {}
    derived = []
    for name, path in files.items():
        if not name.endswith(".md") or path.name in {"index.md", "log.md"}:
            continue
        front, body = _frontmatter(_bytes(path))
        extension = front.get("jlegal", {})
        if extension.get("layer") == "source":
            key = extension["node_id"]
            check(key not in concepts, "CONCEPT_DUPLICATE")
            concepts[key] = (extension, body)
        elif extension.get("layer") == "derived":
            derived.append(extension)
    check(set(concepts) == {n["node_id"] for n in nodes}, "CONCEPT_SET")
    for node in nodes:
        if node["node_id"] not in concepts:
            continue
        ext, body = concepts[node["node_id"]]
        check(all(ext.get(k) == node[k] for k in ("law_id", "node_id", "version_id", "parent_id", "kind", "locator", "ordinal", "branch", "source", "temporal", "attributes")), "CONCEPT_FIELDS")
        check(ext.get("content_sha256") == _sha(node["text"].encode()) and _source_payload_matches(body, node), "CONCEPT_TEXT")
        check(ext.get("conversion") == conversion and ext.get("converted_at") == case["converted_at"] and ext.get("acquisition") == acquisition and ext.get("profile") == PROFILE, "CONCEPT_PROVENANCE")
    check(len(derived) == 1 and derived[0].get("content_policy") == "none-generated" and derived[0].get("source_version_ids") == [], "DERIVED_BOUNDARY")
    return sorted(set(errors)), by_locator


def _catalog(path: Path) -> tuple[dict, dict[str, dict]]:
    catalog = _json(_plain_path(path))
    _require(catalog.get("schema") == "jlegal-conformance-catalog/v1", "CATALOG_SCHEMA")
    cases = catalog.get("cases")
    _require(type(cases) is list and bool(cases), "CATALOG_CASES")
    by_id = {}
    for case in cases:
        _require(type(case) is dict and isinstance(case.get("id"), str) and ID.fullmatch(case["id"]) is not None and case["id"] not in by_id, "CATALOG_CASE_ID")
        _require(case.get("method") in {"artifact", "source_tamper", "rejection"}, "CATALOG_METHOD")
        _require(SHA.fullmatch(case.get("source_sha256", "")) is not None, "CATALOG_SOURCE")
        _require(_sha(_bytes(_relative(path.parent, case["source"]))) == case["source_sha256"], "CATALOG_SOURCE_CHANGED")
        if case["method"] != "rejection":
            oracle = _relative(path.parent, case["expected"])
            _require(_sha(_bytes(oracle)) == case["expected_sha256"], "CATALOG_EXPECTED_CHANGED")
        by_id[case["id"]] = case
    requirements = _json(_relative(path.parent, catalog["requirements"]))
    _require(requirements.get("schema") == "jlegal-conformance-requirements/v1", "REQUIREMENTS_SCHEMA")
    for requirement in requirements["requirements"]:
        _require(requirement["layer"] in LAYERS and set(requirement["cases"]) <= by_id.keys() and bool(requirement["spec_anchor"]), "REQUIREMENT_LINK")
    for relation in catalog.get("relations", []):
        _require(relation["method"] in {"same_node_ids", "same_versions", "identical_bundle"} and relation["left"] in by_id and relation["right"] in by_id, "CATALOG_RELATION")
    return catalog, by_id


def check_submission(catalog: Path, submission: Path, out_dir: Path) -> dict:
    """Read a trusted fixed catalog and a case-to-artifact submission; write reports.

    Invalid configuration raises ValueError. Artifact nonconformance returns
    passed=False. No submitted program is invoked and no source is converted.
    """
    catalog, submission, out_dir = Path(catalog), Path(submission), Path(out_dir)
    spec, cases = _catalog(catalog)
    data = _json(_plain_path(submission))
    _require(data.get("schema") == "jlegal-conformance-submission/v1" and type(data.get("cases")) is list, "SUBMISSION_SCHEMA")
    _require(type(data.get("jori_byte_regression", False)) is bool, "SUBMISSION_REGRESSION")
    _plain_path(out_dir)
    _require(not out_dir.exists(), "OUTPUT_EXISTS")
    submissions = {}
    global_errors = []
    for entry in data["cases"]:
        _require(type(entry) is dict and isinstance(entry.get("id"), str), "SUBMISSION_CASE")
        if entry["id"] not in cases:
            global_errors.append("UNKNOWN_CASE")
        elif entry["id"] in submissions:
            global_errors.append("DUPLICATE_CASE")
        else:
            submissions[entry["id"]] = entry
    rows = []
    artifacts = {}
    for key, case in cases.items():
        errors = []
        okf_errors = []
        byte_errors = []
        okf_checked = False
        byte_checked = False
        entry = submissions.get(key)
        if entry is None:
            errors.append("MISSING_CASE")
        else:
            try:
                source = _relative(submission.parent, entry["source"])
                _require(_sha(_bytes(source)) == case["source_sha256"] and entry.get("source_sha256") == case["source_sha256"] and entry.get("official_law_id") == case["official_law_id"], "SUBMISSION_SOURCE")
                if case["method"] == "rejection":
                    _require(entry.get("outcome") == "rejected", "REJECTION_EXPECTED")
                    receipt = _json(_relative(submission.parent, entry["rejection"]))
                    _require(receipt.get("accepted") is False and receipt.get("code") == case["diagnostic"] and receipt.get("source_sha256") == case["source_sha256"] and receipt.get("official_law_id") == case["official_law_id"], "REJECTION_RECORD")
                else:
                    _require(entry.get("outcome") == "artifacts", "ARTIFACTS_EXPECTED")
                    bundle = _relative(submission.parent, entry["bundle"], directory=True)
                    expected = _json(_relative(catalog.parent, case["expected"]))
                    okf_errors = check_okf_format(bundle)
                    okf_checked = True
                    profile_errors, nodes = _profile(bundle, expected, case)
                    if case["method"] == "source_tamper":
                        _require("SOURCE_BYTES" in profile_errors, "TAMPER_NOT_DEMONSTRATED")
                        errors.extend(e for e in profile_errors if e not in {"SOURCE_BYTES", "BUNDLE_SOURCE_DIGEST"})
                    else:
                        errors.extend(profile_errors)
                        artifacts[key] = (bundle, nodes)
                    if data.get("jori_byte_regression") and "jori_sha256" in case:
                        byte_checked = True
                        for name, digest in case["jori_sha256"].items():
                            if _sha(_bytes(_relative(bundle, name))) != digest:
                                byte_errors.append("JORI_BYTES")
            except (ValueError, UnicodeError, yaml.YAMLError, KeyError, TypeError, AttributeError, OSError):
                errors.append("ARTIFACT_INVALID")
        rows.append({"id": key, "layers": {"okf_format": {"status": "fail" if okf_errors else ("pass" if okf_checked else "not_checked"), "codes": okf_errors}, "profile": {"status": "fail" if errors else "pass", "codes": sorted(set(errors))}, "jori_byte_regression": {"status": "fail" if byte_errors else ("pass" if byte_checked else "not_checked"), "codes": sorted(set(byte_errors))}}})
    relations = []
    for relation in spec.get("relations", []):
        left = artifacts.get(relation["left"])
        right = artifacts.get(relation["right"])
        passed = False
        if left and right:
            if relation["method"] == "identical_bundle":
                a, b = _tree(left[0]), _tree(right[0])
                passed = set(a) == set(b) and all(_bytes(a[k]) == _bytes(b[k]) for k in a)
            else:
                field = "node_id" if relation["method"] == "same_node_ids" else "version_id"
                shared = set(left[1]) & set(right[1])
                passed = bool(shared) and all(left[1][k][field] == right[1][k][field] for k in shared)
        relations.append({"id": relation["id"], "status": "pass" if passed else "fail"})
    common_passed = not global_errors and all(r["layers"][layer]["status"] != "fail" for r in rows for layer in ("okf_format", "profile")) and all(r["status"] == "pass" for r in relations)
    result = {"schema": "jlegal-conformance-result/v1", "catalog_sha256": _sha(_bytes(catalog)), "submission_sha256": _sha(_bytes(submission)), "scope": "fixed-case-artifact-conformance", "common_passed": common_passed, "passed": common_passed and all(r["layers"]["jori_byte_regression"]["status"] != "fail" for r in rows), "cases": rows, "relations": relations, "errors": sorted(set(global_errors)), "required_case_count": len(cases), "submitted_known_case_count": len(submissions)}
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "conformance.json").write_bytes(_canonical(result) + b"\n")
    lines = ["# Fixed-case conformance", "", f"Common checks passed: {str(common_passed).lower()}", "", "| Case | OKF format | Profile | JORI bytes |", "| --- | --- | --- | --- |"]
    lines.extend("| " + r["id"] + " | " + " | ".join(r["layers"][layer]["status"] for layer in LAYERS) + " |" for r in rows)
    lines.extend(["", "Failure codes:"])
    lines.extend("- " + r["id"] + ": " + ", ".join(r["layers"][layer]["codes"]) for r in rows for layer in LAYERS if r["layers"][layer]["codes"])
    lines.extend("- submission: " + code for code in result["errors"])
    lines.extend("- relation: " + r["id"] for r in relations if r["status"] == "fail")
    lines.extend(["", "This checks submitted artifacts for fixed cases; it does not attest producer execution or arbitrary-input conformance.", ""])
    (out_dir / "conformance.md").write_text("\n".join(lines), encoding="utf-8")
    return result
