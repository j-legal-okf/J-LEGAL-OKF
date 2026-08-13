"""Deterministic J-LEGAL-OKF v0.1 projection and offline verifier.

The generated legal bundle is deliberately separate from the repository's own
``okf/`` project-knowledge bundle.  It projects a verified ``jori-corpus/v1``
artifact into an official OKF v0.2-shaped bundle without changing canonical
source text or introducing AI-derived legal assertions.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from urllib.parse import quote

import yaml

from .errors import JLegalError
from .model import LegalNode, NodeKind, canonical_json, text_sha256
from .pipeline import JLEGAL_CONVERTER, JLEGAL_PROFILE, _MANIFEST_SCHEMA, _MANIFEST_SCHEMA_RIGHTS, _atomic_bytes, _recorded_rights, read_crosswalk, read_jsonl, verify_manifest
from .validation import validate_corpus


PROFILE = JLEGAL_PROFILE
BUNDLE_SCHEMA = "jlegal-okf-bundle/v1"
# v2 is v1 plus the rights area carried over from a jori-manifest/v6 corpus.
# A bundle exported from a corpus without one stays v1, byte for byte.
BUNDLE_SCHEMA_RIGHTS = "jlegal-okf-bundle/v2"
EXPORTER = "jlegal-okf-exporter/0.1.0-draft"
_MANIFEST = "manifest.json"
_SOURCE_STANDARD_FIELDS = {"type", "title", "description", "resource", "sources", "generated", "verified", "status", "jlegal"}
_SOURCE_JLEGAL_FIELDS = {"profile", "layer", "law_id", "node_id", "version_id", "parent_id", "kind", "locator", "ordinal", "branch", "content_sha256", "source", "temporal", "attributes", "acquisition", "conversion", "converted_at"}


class LegalOKFError(JLegalError):
    """A deterministic J-LEGAL-OKF export or validation error."""


def _require_egov_profile_corpus(manifest: dict[str, Any], nodes: list[LegalNode]) -> None:
    """Keep this public profile scoped to its declared e-Gov XML input only."""
    if manifest.get("adapter") != "egov_xml":
        raise LegalOKFError("JLEGAL_OKF_ADAPTER")
    if not nodes or any(node.source.adapter != "egov_xml" for node in nodes):
        raise LegalOKFError("JLEGAL_OKF_SOURCE_ADAPTER")
    if manifest.get("schema") not in {_MANIFEST_SCHEMA, _MANIFEST_SCHEMA_RIGHTS} or not isinstance(manifest.get("acquisition"), dict) or manifest.get("conversion") != JLEGAL_CONVERTER or not isinstance(manifest.get("converted_at"), str):
        raise LegalOKFError("JLEGAL_OKF_ACQUISITION")


def _yaml(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1_000_000).replace("...\n", "")


def _concept(frontmatter: dict[str, Any], body: str) -> bytes:
    return ("---\n" + _yaml(frontmatter) + "---\n\n" + body).encode("utf-8")


def _parse_concept(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LegalOKFError(f"JLEGAL_OKF_CONCEPT_READ:{path}") from exc
    if not raw.startswith("---\n"):
        raise LegalOKFError(f"JLEGAL_OKF_FRONTMATTER:{path}")
    _, marker, tail = raw.partition("\n---\n")
    if not marker:
        raise LegalOKFError(f"JLEGAL_OKF_FRONTMATTER:{path}")
    yaml_text = raw[4 : len(raw) - len(tail) - len(marker)]
    try:
        value = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise LegalOKFError(f"JLEGAL_OKF_FRONTMATTER:{path}") from exc
    if type(value) is not dict:
        raise LegalOKFError(f"JLEGAL_OKF_FRONTMATTER:{path}")
    # _concept emits one blank line between frontmatter and the markdown body.
    # Keep the body boundary deterministic rather than treating that separator
    # as source content.
    return value, tail[1:] if tail.startswith("\n") else tail


def _json(path: Path, code: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise LegalOKFError(code) from exc
    if type(value) is not dict or raw != canonical_json(value) + b"\n":
        raise LegalOKFError(code)
    return value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _type_for(node: LegalNode) -> str:
    if node.kind is NodeKind.LAW:
        return "Japanese Legal Document"
    if node.kind in {NodeKind.APPENDIX, NodeKind.TABLE, NodeKind.ROW, NodeKind.CELL}:
        return "Japanese Legal Appendix"
    return "Japanese Legal Provision"


def _source_reference(nodes: list[LegalNode], stage: Path, source: str | Path | None, manifest_inputs: list[dict[str, Any]]) -> tuple[str, str]:
    """Embed the immutable source snapshot for a single-source corpus.

    Whether this is a single-source corpus is decided from the verified
    manifest's declared ``role == "source"`` inputs, never from node-level
    fields. A node's ``source`` tuple (including ``source_key``, which is
    outside ``version_id``'s payload) is not bound to anything that would
    stop it from being forged to look like a second, distinct source and
    silently degrade this to the weaker ledger branch below, bypassing the
    fail-closed gate entirely.

    Role uniqueness is already enforced elsewhere, so a validated manifest
    always declares exactly one ``source`` input; this always takes the
    embed branch. ``node.source.uri`` is a content-addressed logical
    identifier (``jlegal:source:sha256:<hex>``), never a resolvable path, so
    it cannot be used to find the file; the caller must supply it
    explicitly. Export fails closed rather than guessing a path or silently
    degrading to the hash ledger below. That ledger is reserved for a
    genuinely multi-source manifest, which no adapter in this profile
    currently produces and which no manifest passing this profile's input
    role validation can declare.
    """
    source_inputs = [item for item in manifest_inputs if item["role"] == "source"]
    references = stage / "references"
    references.mkdir(parents=True, exist_ok=True)
    if len(source_inputs) == 1:
        if source is None:
            raise LegalOKFError("JLEGAL_OKF_SOURCE_REQUIRED")
        source_path = Path(source)
        if not source_path.is_file():
            raise LegalOKFError("JLEGAL_OKF_SOURCE_UNAVAILABLE")
        sha = source_inputs[0]["sha256"]
        raw = source_path.read_bytes()
        if _digest(raw) != sha:
            raise LegalOKFError("JLEGAL_OKF_SOURCE_MISMATCH")
        target = references / "source.xml"
        _atomic_bytes(target, raw)
        return "/references/source.xml", sha
    unique = {(node.source.uri, node.source.sha256, node.source.adapter, node.source.source_key) for node in nodes}
    value = {
        "schema": "jlegal-source-references/v1",
        "sources": [
            {"adapter": adapter, "sha256": sha, "source_key": source_key, "uri": uri}
            for uri, sha, adapter, source_key in sorted(unique)
        ],
    }
    target = references / "source-reference.json"
    _atomic_bytes(target, canonical_json(value) + b"\n")
    return "/references/source-reference.json", _digest(target.read_bytes())


def _source_frontmatter(node: LegalNode, source_resource: str, acquisition: dict[str, Any], conversion: dict[str, str], converted_at: str) -> dict[str, Any]:
    source = node.source.to_dict()
    return {
        "type": _type_for(node),
        "title": node.heading or node.label or f"{node.kind.value}: {node.locator}",
        "description": f"Source-preserving {node.kind.value} from Japanese legal XML.",
        "resource": f"jlegal://law/{quote(node.source.source_key or node.law_id, safe='')}/{node.node_id}",
        "sources": [
            {"id": "canonical-corpus", "resource": "/canonical/corpus.jsonl", "title": "Canonical JORI corpus"},
            {"id": "official-source", "resource": source_resource, "title": "Immutable source XML reference"},
        ],
        "generated": {"by": EXPORTER},
        "verified": [],
        "status": "draft",
        "jlegal": {
            "profile": PROFILE,
            "layer": "source",
            "law_id": node.law_id,
            "node_id": node.node_id,
            "version_id": node.version_id,
            "parent_id": node.parent_id,
            "kind": node.kind.value,
            "locator": node.locator,
            "ordinal": node.ordinal,
            "branch": list(node.branch),
            "content_sha256": text_sha256(node.text),
            "source": source,
            "temporal": node.temporal.to_dict(),
            "attributes": dict(node.attributes),
            "acquisition": acquisition,
            "conversion": conversion,
            "converted_at": converted_at,
        },
    }


def _source_body(node: LegalNode) -> str:
    begin = f"<!-- jlegal-source:{node.version_id}:begin -->"
    end = f"<!-- jlegal-source:{node.version_id}:end -->"
    if begin in node.text or end in node.text:
        raise LegalOKFError("JLEGAL_OKF_SOURCE_MARKER_COLLISION")
    return f"# {node.heading or node.label or node.locator}\n\n## Source text\n\n{begin}{node.text}{end}\n"


def _derived_frontmatter(nodes: list[LegalNode], source_resource: str, acquisition: dict[str, Any], conversion: dict[str, str], converted_at: str) -> dict[str, Any]:
    law_ids = sorted({node.law_id for node in nodes})
    return {
        "type": "AI-derived Legal Knowledge",
        "title": "Derived legal knowledge boundary",
        "description": "No AI-derived legal knowledge is included in this source-preserving export.",
        "resource": f"jlegal://derived/{quote(law_ids[0] if len(law_ids) == 1 else 'multi-law', safe='')}",
        "sources": [
            {"id": "canonical-corpus", "resource": "/canonical/corpus.jsonl", "title": "Canonical JORI corpus"},
            {"id": "official-source", "resource": source_resource, "title": "Immutable source XML reference"},
        ],
        "generated": {"by": EXPORTER},
        "verified": [],
        "status": "draft",
        "jlegal": {"profile": PROFILE, "layer": "derived", "source_version_ids": [], "content_policy": "none-generated", "acquisition": acquisition, "conversion": conversion, "converted_at": converted_at},
    }


def _bundle_manifest(root: Path, corpus_sha: str, input_manifest_sha: str, rights: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = [path for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != _MANIFEST]
    entries = [
        {"path": path.relative_to(root).as_posix(), "sha256": _digest(path.read_bytes())}
        for path in sorted(paths, key=lambda value: value.relative_to(root).as_posix())
    ]
    value = {
        "schema": BUNDLE_SCHEMA_RIGHTS if rights is not None else BUNDLE_SCHEMA,
        "profile": PROFILE,
        "canonical_corpus_sha256": corpus_sha,
        "canonical_manifest_sha256": input_manifest_sha,
        "files": entries,
    }
    # The bundle never states rights of its own: it carries over exactly what
    # the canonical manifest asserts, and validate_okf compares the two.
    if rights is not None:
        value["rights"] = rights
    return value


def _index_content(nodes: list[LegalNode], source_resource: str) -> str:
    links = "\n".join(
        f"- [{node.heading or node.label or node.locator}](source/{node.version_id}.md) — {node.kind.value}"
        for node in sorted(nodes, key=lambda value: (value.node_id, value.version_id))
    )
    return (
        "---\nokf_version: \"0.2\"\n---\n\n# J-LEGAL-OKF legal knowledge bundle\n\n"
        f"Profile: `{PROFILE}`. Canonical source, structure, and derived knowledge are separated.\n\n"
        "# References\n\n"
        f"- [Immutable source reference]({source_resource.lstrip('/')})\n"
        "- [Generated bundle manifest](manifest.json)\n\n"
        f"# Legal concepts\n\n{links}\n\n"
        "# Derived knowledge\n\n"
        "- [Boundary](derived/knowledge.md) — no AI-derived content was generated.\n"
    )


def _copy_canonical(corpus: Path, manifest: Path, stage: Path) -> None:
    source_root = corpus.parent
    canonical = stage / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    for name in ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl"):
        raw = (source_root / name).read_bytes()
        _atomic_bytes(canonical / name, raw)
    _atomic_bytes(canonical / "manifest.json", manifest.read_bytes())


def export_okf(corpus: str | Path, manifest: str | Path, out_dir: str | Path, *, source: str | Path | None = None) -> dict[str, Any]:
    """Export a verified canonical corpus as a deterministic, standalone bundle.

    ``source`` is the local file compiled into this corpus; it is required
    for a single-source corpus and embedded as ``references/source.xml``.
    """
    corpus_path = Path(corpus).resolve()
    manifest_path = Path(manifest).resolve()
    source_root = corpus_path.parent
    crosswalk_path = source_root / "crosswalk.jsonl"
    projection_path = source_root / "projection.jsonl"
    input_manifest = verify_manifest(corpus_path, manifest_path, crosswalk_path, projection_path)
    nodes = read_jsonl(corpus_path)
    validate_corpus(nodes, read_crosswalk(crosswalk_path))
    _require_egov_profile_corpus(input_manifest, nodes)
    acquisition = input_manifest["acquisition"]
    conversion = input_manifest["conversion"]
    converted_at = input_manifest["converted_at"]
    if not nodes:
        raise LegalOKFError("JLEGAL_OKF_CORPUS_EMPTY")
    destination = Path(out_dir).resolve()
    if destination.exists():
        raise LegalOKFError(f"JLEGAL_OKF_OUTPUT_EXISTS_REFUSED: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=destination.name + ".stage.", dir=destination.parent))
    try:
        _copy_canonical(corpus_path, manifest_path, stage)
        source_resource, _ = _source_reference(nodes, stage, source, input_manifest["inputs"])
        source_dir = stage / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        for node in sorted(nodes, key=lambda value: (value.node_id, value.version_id)):
            _atomic_bytes(source_dir / f"{node.version_id}.md", _concept(_source_frontmatter(node, source_resource, acquisition, conversion, converted_at), _source_body(node)))
        derived = stage / "derived"
        derived.mkdir(parents=True, exist_ok=True)
        _atomic_bytes(
            derived / "knowledge.md",
            _concept(_derived_frontmatter(nodes, source_resource, acquisition, conversion, converted_at), "# Boundary\n\nThis bundle contains no model-generated legal interpretation, summary, or advice.\n"),
        )
        _atomic_bytes(stage / "index.md", _index_content(nodes, source_resource).encode("utf-8"))
        bundle_manifest = _bundle_manifest(stage, input_manifest["corpus_sha256"], _digest(manifest_path.read_bytes()), input_manifest.get("rights"))
        _atomic_bytes(stage / _MANIFEST, canonical_json(bundle_manifest) + b"\n")
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {"bundle": str(destination), "corpus_sha256": input_manifest["corpus_sha256"], "nodes": len(nodes), "profile": PROFILE}


def _expected_files(root: Path) -> list[Path]:
    return sorted([path for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != _MANIFEST], key=lambda value: value.relative_to(root).as_posix())


def _validate_bundle_manifest(root: Path) -> dict[str, Any]:
    value = _json(root / _MANIFEST, "JLEGAL_OKF_MANIFEST")
    expected = {"schema", "profile", "canonical_corpus_sha256", "canonical_manifest_sha256", "files"}
    # _json already guarantees a dict written in canonical bytes.
    if value.get("schema") == BUNDLE_SCHEMA_RIGHTS:
        expected |= {"rights"}
    if set(value) != expected or value["schema"] not in {BUNDLE_SCHEMA, BUNDLE_SCHEMA_RIGHTS} or value["profile"] != PROFILE or not all(isinstance(value[key], str) and len(value[key]) == 64 for key in ("canonical_corpus_sha256", "canonical_manifest_sha256")) or type(value["files"]) is not list:
        raise LegalOKFError("JLEGAL_OKF_MANIFEST_SHAPE")
    if "rights" in value:
        try:
            _recorded_rights(value["rights"])
        except JLegalError as exc:
            raise LegalOKFError("JLEGAL_OKF_MANIFEST_SHAPE") from exc
    actual = [
        {"path": path.relative_to(root).as_posix(), "sha256": _digest(path.read_bytes())}
        for path in _expected_files(root)
    ]
    if value["files"] != actual:
        raise LegalOKFError("JLEGAL_OKF_MANIFEST_TAMPERED")
    return value


def _validate_index(root: Path, nodes: list[LegalNode], source_resource: str) -> None:
    raw = (root / "index.md").read_text(encoding="utf-8")
    if raw != _index_content(nodes, source_resource):
        raise LegalOKFError("JLEGAL_OKF_INDEX")


def _validate_source_reference(root: Path, nodes: list[LegalNode]) -> str:
    xml = root / "references" / "source.xml"
    ref = root / "references" / "source-reference.json"
    if xml.is_file() and ref.exists():
        raise LegalOKFError("JLEGAL_OKF_SOURCE_REFERENCE")
    source_hashes = {node.source.sha256 for node in nodes}
    if xml.is_file():
        if len(source_hashes) != 1 or _digest(xml.read_bytes()) != next(iter(source_hashes)):
            raise LegalOKFError("JLEGAL_OKF_SOURCE_TAMPERED")
        return "/references/source.xml"
    if ref.is_file():
        value = _json(ref, "JLEGAL_OKF_SOURCE_REFERENCE")
        if set(value) != {"schema", "sources"} or value["schema"] != "jlegal-source-references/v1" or type(value["sources"]) is not list:
            raise LegalOKFError("JLEGAL_OKF_SOURCE_REFERENCE")
        declared = {(row.get("uri"), row.get("sha256"), row.get("adapter"), row.get("source_key")) for row in value["sources"] if type(row) is dict}
        if declared != {(node.source.uri, node.source.sha256, node.source.adapter, node.source.source_key) for node in nodes}:
            raise LegalOKFError("JLEGAL_OKF_SOURCE_REFERENCE")
        return "/references/source-reference.json"
    raise LegalOKFError("JLEGAL_OKF_SOURCE_REFERENCE")


def _validate_source_concept(path: Path, node: LegalNode, source_resource: str, acquisition: dict[str, Any], conversion: dict[str, str], converted_at: str) -> None:
    frontmatter, body = _parse_concept(path)
    extension = frontmatter.get("jlegal")
    if type(extension) is not dict or set(extension) != _SOURCE_JLEGAL_FIELDS or extension.get("profile") != PROFILE or extension.get("layer") != "source":
        raise LegalOKFError(f"JLEGAL_OKF_SOURCE_EXTENSION:{path.name}")
    if set(frontmatter) != _SOURCE_STANDARD_FIELDS or frontmatter != _source_frontmatter(node, source_resource, acquisition, conversion, converted_at):
        raise LegalOKFError(f"JLEGAL_OKF_SOURCE_FIELDS:{path.name}")
    expected = {
        "law_id": node.law_id,
        "node_id": node.node_id,
        "version_id": node.version_id,
        "parent_id": node.parent_id,
        "kind": node.kind.value,
        "locator": node.locator,
        "ordinal": node.ordinal,
        "branch": list(node.branch),
        "content_sha256": text_sha256(node.text),
        "source": node.source.to_dict(),
        "temporal": node.temporal.to_dict(),
        "attributes": dict(node.attributes),
    }
    if any(extension.get(key) != value for key, value in expected.items()):
        raise LegalOKFError(f"JLEGAL_OKF_SOURCE_IDENTITY:{path.name}")
    begin = f"<!-- jlegal-source:{node.version_id}:begin -->"
    end = f"<!-- jlegal-source:{node.version_id}:end -->"
    start = body.find(begin)
    finish = body.find(end)
    if start < 0 or finish < start or body[start + len(begin) : finish] != node.text or body != _source_body(node):
        raise LegalOKFError(f"JLEGAL_OKF_SOURCE_CONTENT:{path.name}")


def _validate_derived(root: Path, nodes: list[LegalNode], source_resource: str, acquisition: dict[str, Any], conversion: dict[str, str], converted_at: str) -> None:
    frontmatter, body = _parse_concept(root / "derived" / "knowledge.md")
    required = {"type", "title", "description", "resource", "sources", "generated", "verified", "status", "jlegal"}
    extension = frontmatter.get("jlegal")
    if set(frontmatter) != required or frontmatter != _derived_frontmatter(nodes, source_resource, acquisition, conversion, converted_at) or type(extension) is not dict or extension != {"profile": PROFILE, "layer": "derived", "source_version_ids": [], "content_policy": "none-generated", "acquisition": acquisition, "conversion": conversion, "converted_at": converted_at} or body != "# Boundary\n\nThis bundle contains no model-generated legal interpretation, summary, or advice.\n":
        raise LegalOKFError("JLEGAL_OKF_DERIVED")


def _expected_output_paths(nodes: list[LegalNode], source_resource: str) -> set[str]:
    return {
        "index.md",
        "canonical/corpus.jsonl",
        "canonical/crosswalk.jsonl",
        "canonical/projection.jsonl",
        "canonical/manifest.json",
        "derived/knowledge.md",
        source_resource.lstrip("/"),
        *(f"source/{node.version_id}.md" for node in nodes),
    }


def validate_okf(bundle: str | Path, *, verify_source: bool = False) -> dict[str, Any]:
    """Verify deterministic OKF shape, canonical links, source fidelity, and hashes.

    ``verify_source=True`` additionally re-converts the bundle's embedded
    ``references/source.xml`` (via ``verify_manifest(..., verify_inputs=True)``)
    and byte-compares the result against ``canonical/corpus.jsonl``,
    ``crosswalk.jsonl``, and ``projection.jsonl`` -- proving the canonical
    corpus was actually, validly derived from the embedded source, not merely
    that declared hashes agree with each other. Only the single-source
    ``references/source.xml`` embed path supports this; a bundle using the
    multi-source ``source-reference.json`` ledger (which no adapter in this
    profile currently produces) fails closed with
    ``JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED`` rather than silently skipping
    the check.
    """
    root = Path(bundle).resolve()
    if not root.is_dir():
        raise LegalOKFError("JLEGAL_OKF_BUNDLE_DIR")
    bundle_manifest = _validate_bundle_manifest(root)
    canonical = root / "canonical"
    corpus_path = canonical / "corpus.jsonl"
    manifest_path = canonical / "manifest.json"
    crosswalk_path = canonical / "crosswalk.jsonl"
    projection_path = canonical / "projection.jsonl"
    try:
        manifest = verify_manifest(corpus_path, manifest_path, crosswalk_path, projection_path)
    except Exception as exc:
        raise LegalOKFError("JLEGAL_OKF_CANONICAL") from exc
    if manifest["corpus_sha256"] != bundle_manifest["canonical_corpus_sha256"] or _digest(manifest_path.read_bytes()) != bundle_manifest["canonical_manifest_sha256"]:
        raise LegalOKFError("JLEGAL_OKF_CANONICAL_TAMPERED")
    # Both directions: a bundle may neither invent a rights assertion the
    # canonical manifest does not make, nor drop one that it does.
    if bundle_manifest.get("rights") != manifest.get("rights"):
        raise LegalOKFError("JLEGAL_OKF_RIGHTS_MISMATCH")
    nodes = read_jsonl(corpus_path)
    validate_corpus(nodes, read_crosswalk(crosswalk_path))
    _require_egov_profile_corpus(manifest, nodes)
    acquisition = manifest["acquisition"]
    conversion = manifest["conversion"]
    converted_at = manifest["converted_at"]
    source_resource = _validate_source_reference(root, nodes)
    actual_output_paths = {path.relative_to(root).as_posix() for path in _expected_files(root)}
    if actual_output_paths != _expected_output_paths(nodes, source_resource):
        raise LegalOKFError("JLEGAL_OKF_FILE_SET")
    _validate_index(root, nodes, source_resource)
    expected_paths = {f"source/{node.version_id}.md" for node in nodes}
    actual_paths = {path.relative_to(root).as_posix() for path in (root / "source").glob("*.md")} if (root / "source").is_dir() else set()
    if actual_paths != expected_paths:
        raise LegalOKFError("JLEGAL_OKF_SOURCE_CONCEPT_SET")
    known_ids = {node.node_id for node in nodes}
    for node in nodes:
        if node.parent_id is not None and node.parent_id not in known_ids:
            raise LegalOKFError("JLEGAL_OKF_PARENT_LINK")
        _validate_source_concept(root / "source" / f"{node.version_id}.md", node, source_resource, acquisition, conversion, converted_at)
    _validate_derived(root, nodes, source_resource, acquisition, conversion, converted_at)
    if verify_source:
        if source_resource != "/references/source.xml":
            raise LegalOKFError("JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED")
        try:
            verify_manifest(corpus_path, manifest_path, crosswalk_path, projection_path, verify_inputs=True, source=root / "references" / "source.xml")
        except Exception as exc:
            raise LegalOKFError("JLEGAL_OKF_CANONICAL") from exc
    return {"valid": True, "nodes": len(nodes), "profile": PROFILE, "source_resource": source_resource, "source_reverified": verify_source}
