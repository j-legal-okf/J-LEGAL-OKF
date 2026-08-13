"""Transactional compilation, canonical artifact IO, and manifest verification."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from dataclasses import dataclass, replace
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, quote, urlparse

from .adapters import Adaptation, BuildInput, default_registry
from .errors import JLegalError, ValidationError
from .model import LegalNode, LegacyCrosswalk, NodeKind, RetrievalDocument, SCHEMA, canonical_json, canonical_jsonl, content_addressed_uri, content_uri_sha256, text_sha256
from .validation import validate_corpus

_MANIFEST_CANONICALIZATION = "json-sort-keys-utf8-compact-jsonl-final-lf"
_MANIFEST_SCHEMA = "jori-manifest/v5"
# v6 is v5 plus an asserted rights area. A corpus compiled without one keeps
# emitting v5 byte for byte, so recorded v5 digests stay valid.
_MANIFEST_SCHEMA_RIGHTS = "jori-manifest/v6"
_LEGACY_MANIFEST_SCHEMA = "jori-manifest/v3"
_MANIFEST_ADAPTERS = frozenset({"json", "xml", "html", "egov_xml"})
_MANIFEST_ADAPTER_VERSION = "1"
_MANIFEST_DIGESTS = ("corpus_sha256", "crosswalk_sha256", "projection_sha256", "build_options_sha256")
_REQUIRED_INPUT_ROLES = {
    "json": frozenset({"source"}),
    "xml": frozenset({"source", "mapping"}),
    "html": frozenset({"source", "mapping"}),
    "egov_xml": frozenset({"source"}),
}
_OPTIONAL_INPUT_ROLES = {"egov_xml": frozenset({"mapping"})}
_INLINE_MAPPING_URI = "inline:canonical-json-v1"
JLEGAL_PROFILE = "J-LEGAL-OKF/0.1.0-draft"
JLEGAL_CONVERTER = {"name": "JORI Engine", "version": "0.1.0-draft", "profile": JLEGAL_PROFILE}
_ACQUISITION_KEYS = {"schema", "source_authority", "source_url", "retrieved_at", "source_format", "official_law_id", "law_number", "requested_law_id", "as_of", "sha256", "rights"}
_RIGHTS_KEYS = {"source_license", "bundle_license", "redistribution_allowed", "commercial_use_allowed"}


@dataclass(frozen=True)
class CanonicalArtifacts:
    """Typed canonical products and their exact on-disk bytes."""

    nodes: tuple[LegalNode, ...]
    crosswalk: tuple[LegacyCrosswalk, ...]
    projection: tuple[RetrievalDocument, ...]
    corpus_bytes: bytes
    crosswalk_bytes: bytes
    projection_bytes: bytes


def _lower_hex_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and value == value.lower() and all(char in "0123456789abcdef" for char in value)


def _canonical_mapping(mapping: Any) -> dict[str, Any] | None:
    if mapping is None: return None
    if not isinstance(mapping, dict): raise ValidationError("BUILD_RECIPE_MAPPING")
    return json.loads(canonical_json(mapping))


def _build_recipe(adapter: str, mapping: Any) -> dict[str, Any]:
    return {"adapter":adapter,"mapping":_canonical_mapping(mapping)}


def _mapping_input(mapping: Any, mapping_path: str | Path | None) -> BuildInput:
    if mapping_path is not None:
        raw=Path(mapping_path).read_bytes(); sha256=hashlib.sha256(raw).hexdigest()
        return BuildInput("mapping",content_addressed_uri(sha256),sha256)
    return BuildInput("mapping",_INLINE_MAPPING_URI,hashlib.sha256(canonical_json(mapping)).hexdigest())


def _manifest_options(adapter: str, adapter_version: str, canonicalization: str, hierarchy_status: str, inputs: list[dict[str, str]], required_input_roles: list[str], build_recipe: dict[str, Any], acquisition: dict[str, Any] | None = None, conversion: dict[str, str] | None = None, rights: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"adapter":adapter,"adapter_version":adapter_version,"canonicalization":canonicalization,"hierarchy_status":hierarchy_status,"inputs":inputs,"required_input_roles":required_input_roles,"build_recipe":build_recipe}
    if acquisition is not None:
        value["acquisition"] = acquisition
        value["conversion"] = conversion
    # Only an asserted rights area enters these options, so build_options_sha256
    # binds the assertion when there is one and is unchanged when there is not.
    if rights is not None:
        value["rights"] = rights
    return value


def _valid_optional_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _canonical_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc and parsed.isoformat().replace("+00:00", "Z") == value


def _now_canonical_utc() -> str:
    """A conversion timestamp in the same canonical UTC 'Z' form as ``retrieved_at``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_acquisition_url(value: Any, requested_law_id: str, as_of: str | None) -> None:
    if not isinstance(value, str):
        raise ValidationError("ACQUISITION_URL")
    parsed = urlparse(value)
    expected_path = "/api/2/law_data/" + quote(requested_law_id, safe="")
    if parsed.scheme != "https" or parsed.netloc != "laws.e-gov.go.jp" or parsed.path != expected_path or parsed.params or parsed.fragment:
        raise ValidationError("ACQUISITION_URL")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValidationError("ACQUISITION_URL") from exc
    if len(pairs) != len({key for key, _ in pairs}):
        raise ValidationError("ACQUISITION_URL")
    query = dict(pairs)
    expected = {"response_format": "xml", "law_full_text_format": "xml"}
    if as_of is not None:
        expected["asof"] = as_of
    if query != expected:
        raise ValidationError("ACQUISITION_URL")


def _egov_acquisition(adaptation: Adaptation, supplied: dict[str, Any] | None) -> dict[str, Any] | None:
    """Accept retrieval facts only from the e-Gov fetch receipt, never mtime."""
    if adaptation.adapter != "egov_xml":
        if supplied is not None:
            raise ValidationError("ACQUISITION_EGOV_ONLY")
        return None
    base = adaptation.source_metadata
    if type(base) is not dict or set(base) != _ACQUISITION_KEYS:
        raise ValidationError("ACQUISITION_ADAPTER_METADATA")
    source = next((item for item in adaptation.inputs if item.role == "source"), None)
    if source is None or base["sha256"] != source.sha256:
        raise ValidationError("ACQUISITION_SOURCE_HASH")
    value = base if supplied is None else supplied
    if type(value) is not dict or set(value) != _ACQUISITION_KEYS:
        raise ValidationError("ACQUISITION_SHAPE")
    fixed = ("schema", "source_authority", "source_format", "official_law_id", "law_number", "sha256", "rights")
    if any(value[key] != base[key] for key in fixed):
        raise ValidationError("ACQUISITION_CONFLICT")
    if value["schema"] != "jlegal-egov-acquisition/v1" or value["source_authority"] != "e-Gov 法令API Version 2" or value["source_format"] != "e-Gov Law API v2 XML full-text response" or value["rights"] is not None:
        raise ValidationError("ACQUISITION_VALUES")
    if not isinstance(value["official_law_id"], str) or not value["official_law_id"] or not _valid_optional_string(value["law_number"]) or not _valid_optional_string(value["requested_law_id"]) or not _valid_optional_string(value["as_of"]):
        raise ValidationError("ACQUISITION_VALUES")
    if value["sha256"] != source.sha256:
        raise ValidationError("ACQUISITION_SOURCE_HASH")
    if (value["source_url"] is None) != (value["retrieved_at"] is None):
        raise ValidationError("ACQUISITION_RETRIEVAL_PAIR")
    if value["source_url"] is not None:
        if not isinstance(value["requested_law_id"], str) or not value["requested_law_id"] or not _canonical_utc_timestamp(value["retrieved_at"]):
            raise ValidationError("ACQUISITION_RETRIEVAL")
        if value["as_of"] is not None:
            try:
                if date.fromisoformat(value["as_of"]).isoformat() != value["as_of"]:
                    raise ValueError
            except ValueError as exc:
                raise ValidationError("ACQUISITION_AS_OF") from exc
        _validate_acquisition_url(value["source_url"], value["requested_law_id"], value["as_of"])
    return json.loads(canonical_json(value))


def _rights(value: Any) -> dict[str, Any] | None:
    """Normalize an explicitly asserted rights area, or None when none is asserted.

    Rights are never inferred. Nothing in the source bytes, the API delivery,
    or the adapter can produce this value: it is recorded only because a
    caller stated it, and the four fields are opaque labels this profile
    stores and hashes without interpreting them (a licence identifier is not
    resolved, and the two booleans are not derived from it).

    An assertion in which every field is null says nothing that absence does
    not already say, so it is refused; a manifest without the key stays the
    single representation of "no rights recorded".
    """
    if value is None:
        return None
    if type(value) is not dict or set(value) != _RIGHTS_KEYS:
        raise ValidationError("RIGHTS_SHAPE")
    for key in ("source_license", "bundle_license"):
        item = value[key]
        if item is not None and (not isinstance(item, str) or not item or "\0" in item):
            raise ValidationError("RIGHTS_VALUES")
    for key in ("redistribution_allowed", "commercial_use_allowed"):
        # type(...) is bool, because bool is an int subclass and 0/1 would
        # otherwise be silently accepted as a permission decision.
        if value[key] is not None and type(value[key]) is not bool:
            raise ValidationError("RIGHTS_VALUES")
    if all(value[key] is None for key in _RIGHTS_KEYS):
        raise ValidationError("RIGHTS_EMPTY")
    return json.loads(canonical_json(value))


def _recorded_rights(value: Any) -> dict[str, Any]:
    """Re-validate a rights area already recorded in an artifact.

    Unlike _rights, None is not a sentinel here: a schema that declares a
    rights area must carry one, so a null is a malformed area, not silence.
    """
    if value is None:
        raise ValidationError("RIGHTS_SHAPE")
    return _rights(value)


def _provenance_sha256(recipe: dict[str, Any], inputs: Sequence[BuildInput]) -> str:
    entries=sorted(({"role":item.role,"uri":item.uri,"sha256":item.sha256} for item in inputs),key=lambda item:(item["role"],item["uri"],item["sha256"]))
    return hashlib.sha256(canonical_json({"build_recipe":recipe,"inputs":entries})).hexdigest()


def _bind_build_provenance(adaptation: Adaptation, recipe: dict[str, Any], inputs: Sequence[BuildInput]) -> Adaptation:
    """Make used build dependencies part of every canonical node version."""
    fingerprint=_provenance_sha256(recipe,inputs); versions: dict[str,str]={}; nodes=[]
    for node in adaptation.nodes:
        attributes=tuple((key,value) for key,value in node.attributes if key != "build_provenance_sha256") + (("build_provenance_sha256",fingerprint),)
        bound=replace(node,attributes=tuple(sorted(attributes))); nodes.append(bound); versions[node.version_id]=bound.version_id
    crosswalk=tuple(replace(row,target_version_id=versions[row.target_version_id]) for row in adaptation.crosswalk)
    return replace(adaptation,nodes=tuple(nodes),crosswalk=crosswalk,inputs=tuple(inputs))


def _safe(path: str | Path) -> Path:
    return Path(path).resolve()


def _canonical_artifact_paths(
    corpus_path: str | Path,
    crosswalk_path: str | Path | None,
    projection_path: str | Path | None,
) -> tuple[Path, Path, Path]:
    corpus_file = Path(corpus_path)
    if crosswalk_path is None:
        legacy_crosswalk = corpus_file.parent / "crosswalk.json"
        crosswalk_path = legacy_crosswalk if legacy_crosswalk.exists() else corpus_file.parent / "crosswalk.jsonl"
    if projection_path is None:
        projection_path = corpus_file.parent / "projection.jsonl"
    return corpus_file, Path(crosswalk_path), Path(projection_path)


def read_jsonl(path: str | Path) -> list[LegalNode]:
    items: list[LegalNode] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line:
            try: items.append(LegalNode.from_dict(json.loads(line)))
            except Exception as exc: raise ValidationError(f"JSONL_LINE_{number}: {exc}") from exc
    return items


def read_crosswalk(path: str | Path | None) -> list[LegacyCrosswalk]:
    if path is None or not Path(path).exists(): return []
    result=[]
    for number,line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),1):
        if not line: raise ValidationError("CROSSWALK_BLANK_LINE")
        try: result.append(LegacyCrosswalk.from_dict(json.loads(line)))
        except Exception as exc: raise ValidationError(f"CROSSWALK_LINE_{number}: {exc}") from exc
    return result


def read_projection(path: str | Path) -> list[RetrievalDocument]:
    result=[]
    for number,line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),1):
        if not line: raise ValidationError("PROJECTION_BLANK_LINE")
        try: result.append(RetrievalDocument.from_dict(json.loads(line)))
        except Exception as exc: raise ValidationError(f"PROJECTION_LINE_{number}: {exc}") from exc
    return result


def canonical_crosswalk_jsonl(crosswalk: Sequence[LegacyCrosswalk]) -> bytes:
    ordered=sorted(crosswalk,key=lambda x:(x.legacy_id,x.target_version_id))
    return b"".join(canonical_json(x.to_dict())+b"\n" for x in ordered)


def make_projection(nodes: Sequence[LegalNode]) -> list[RetrievalDocument]:
    """Project every substantive AST node, retaining parent chapeau but not child aggregates."""
    selected={NodeKind.PREAMBLE,NodeKind.MAIN_PROVISION,NodeKind.PART,NodeKind.CHAPTER,NodeKind.SECTION,NodeKind.SUBSECTION,NodeKind.DIVISION,NodeKind.ARTICLE,NodeKind.PARAGRAPH,NodeKind.ITEM,NodeKind.SUBITEM,NodeKind.APPENDIX,NodeKind.SUPPLEMENTARY_PROVISION,NodeKind.AMENDMENT_PROVISION,NodeKind.TABLE,NodeKind.ROW,NodeKind.CELL}
    result=[]
    for n in sorted(nodes,key=lambda x:(x.locator,x.version_id)):
        if n.kind not in selected: continue
        # Without explicit own/aggregate source fields, subtraction is lossy. Keep every substantive text.
        policy="full-node-v1"; pid="projection_"+text_sha256(n.version_id+"|"+policy+"|"+n.text)[:32]
        result.append(RetrievalDocument(pid,"1",n.node_id,n.version_id,n.law_id,n.locator,n.heading,n.text,n.kind,n.temporal,n.source))
    return result


def canonical_projection_jsonl(documents: Sequence[RetrievalDocument]) -> bytes:
    return b"".join(canonical_json(x.to_dict())+b"\n" for x in sorted(documents,key=lambda x:(x.locator,x.version_id,x.projection_id)))

def artifact_bundle_bytes(corpus_path: str | Path) -> bytes:
    root=Path(corpus_path).resolve().parent
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    # Artifact locations are intentionally not part of a manifest; canonical bytes remain portable.
    return (root/"corpus.jsonl").read_bytes()+(root/"crosswalk.jsonl").read_bytes()+(root/"projection.jsonl").read_bytes()+canonical_json(manifest)+b"\n"


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle: handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
    except Exception:
        Path(name).unlink(missing_ok=True); raise


def manifest_for(corpus_id: str, nodes: Sequence[LegalNode], crosswalk: Sequence[LegacyCrosswalk], projection: Sequence[RetrievalDocument], adaptation: Adaptation, corpus: bytes, build_recipe: dict[str, Any], acquisition: dict[str, Any] | None = None, converted_at: str | None = None, rights: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the manifest dict from already-validated parts.

    Like ``acquisition`` (validated by ``_egov_acquisition`` before this is
    called), a non-None ``converted_at`` must already be a canonical UTC
    timestamp accepted by ``_canonical_utc_timestamp`` -- this function does
    not re-check it, and neither does it re-check an already-normalized
    ``rights`` area. ``compile_adaptation`` is the sole caller and enforces
    both before calling in; a manifest assembled here with an invalid
    ``converted_at`` or ``rights`` still fails closed downstream at
    ``verify_manifest``.
    """
    sources = sorted(({"role": x.role, "uri": x.uri, "sha256": x.sha256} for x in adaptation.inputs), key=lambda x: (x["role"], x["uri"], x["sha256"]))
    crosswalk_bytes = canonical_crosswalk_jsonl(crosswalk); projection_bytes=canonical_projection_jsonl(projection)
    required_input_roles=[item["role"] for item in sources]; hierarchy_status="partial" if adaptation.partial_hierarchy else "full"; options = _manifest_options(adaptation.adapter,adaptation.version,_MANIFEST_CANONICALIZATION,hierarchy_status,sources,required_input_roles,build_recipe,acquisition,JLEGAL_CONVERTER if acquisition is not None else None,rights)
    egov_schema = _MANIFEST_SCHEMA_RIGHTS if rights is not None else _MANIFEST_SCHEMA
    value = {"schema": egov_schema if acquisition is not None else _LEGACY_MANIFEST_SCHEMA, "corpus_id": corpus_id, "node_count": len(nodes), "law_count": len({n.law_id for n in nodes}), "crosswalk_count": len(crosswalk), "projection_count":len(projection), "hierarchy_status":hierarchy_status, "canonicalization": options["canonicalization"], "adapter": adaptation.adapter, "adapter_version": adaptation.version, "inputs": sources, "required_input_roles":required_input_roles, "build_recipe":build_recipe, "corpus_sha256": hashlib.sha256(corpus).hexdigest(), "crosswalk_sha256": hashlib.sha256(crosswalk_bytes).hexdigest(), "projection_sha256":hashlib.sha256(projection_bytes).hexdigest(), "build_options_sha256": hashlib.sha256(canonical_json(options)).hexdigest()}
    if acquisition is not None:
        value["acquisition"] = acquisition
        value["conversion"] = JLEGAL_CONVERTER
        # converted_at is deliberately excluded from _manifest_options above,
        # so it never enters build_options_sha256 or any other deterministic
        # hash; two compiles of the same bytes at different wall-clock times
        # differ only in this field.
        value["converted_at"] = converted_at
        if rights is not None:
            value["rights"] = rights
    return value


def _rebuild_from_manifest(manifest: dict[str, Any], corpus: bytes, crosswalk: bytes, projection: bytes, source: Path) -> None:
    """Re-execute the declared local recipe against a caller-verified source and compare its canonical products."""
    recipe=manifest["build_recipe"]; mapping=recipe["mapping"]
    if manifest["adapter"] == "json":
        if mapping is not None: raise JLegalError("MANIFEST_RECIPE_MAPPING")
        replay_mapping=None
    elif manifest["adapter"] in {"xml","html"}:
        if not isinstance(mapping,dict): raise JLegalError("MANIFEST_RECIPE_MAPPING")
        replay_mapping=mapping
    elif manifest["adapter"] == "egov_xml":
        if mapping is not None and not isinstance(mapping, dict): raise JLegalError("MANIFEST_RECIPE_MAPPING")
        replay_mapping=mapping
    else:
        raise JLegalError("MANIFEST_RECIPE_ADAPTER")
    try: adaptation=default_registry().adapt(source,name=manifest["adapter"],mapping=replay_mapping)
    except Exception as exc: raise JLegalError("MANIFEST_REBUILD_FAILED") from exc
    inputs=tuple(BuildInput(item["role"],item["uri"],item["sha256"]) for item in manifest["inputs"])
    rebuilt=_bind_build_provenance(adaptation,recipe,inputs); rebuilt_corpus=canonical_jsonl(rebuilt.nodes); rebuilt_crosswalk=canonical_crosswalk_jsonl(rebuilt.crosswalk); rebuilt_projection=canonical_projection_jsonl(make_projection(rebuilt.nodes))
    if rebuilt_corpus != corpus: raise JLegalError("MANIFEST_REBUILD_CORPUS")
    if rebuilt_crosswalk != crosswalk: raise JLegalError("MANIFEST_REBUILD_CROSSWALK")
    if rebuilt_projection != projection: raise JLegalError("MANIFEST_REBUILD_PROJECTION")
    if ("partial" if rebuilt.partial_hierarchy else "full") != manifest["hierarchy_status"]: raise JLegalError("MANIFEST_REBUILD_OPTIONS")


def verify_canonical_artifacts(
    corpus_path: str | Path,
    crosswalk_path: str | Path | None = None,
    projection_path: str | Path | None = None,
) -> CanonicalArtifacts:
    """Verify portable canonical artifacts without interpreting a manifest."""
    corpus_file, crosswalk_file, projection_file = _canonical_artifact_paths(corpus_path, crosswalk_path, projection_path)
    corpus = corpus_file.read_bytes()
    crosswalk_bytes = crosswalk_file.read_bytes()
    projection_bytes = projection_file.read_bytes()
    nodes = read_jsonl(corpus_file)
    crosswalk = read_crosswalk(crosswalk_file)
    projection = read_projection(projection_file)
    canonical_crosswalk = canonical_crosswalk_jsonl(crosswalk)
    canonical_projection = canonical_projection_jsonl(projection)
    if corpus != canonical_jsonl(nodes) or crosswalk_bytes != canonical_crosswalk or projection_bytes != canonical_projection:
        raise JLegalError("ARTIFACT_NOT_CANONICAL")
    if canonical_projection != canonical_projection_jsonl(make_projection(nodes)):
        raise JLegalError("PROJECTION_DERIVATION_MISMATCH")
    if len({(item.projection_id, item.projection_version) for item in projection}) != len(projection):
        raise JLegalError("PROJECTION_DUPLICATE")
    return CanonicalArtifacts(
        nodes=tuple(nodes),
        crosswalk=tuple(crosswalk),
        projection=tuple(projection),
        corpus_bytes=corpus,
        crosswalk_bytes=crosswalk_bytes,
        projection_bytes=projection_bytes,
    )


def verify_manifest(corpus_path: str | Path, manifest_path: str | Path, crosswalk_path: str | Path | None = None, projection_path: str | Path | None = None, *, verify_inputs: bool = False, source: str | Path | None = None) -> dict[str, Any]:
    try: manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: raise ValidationError("MANIFEST_JSON") from exc
    expected = {"schema", "corpus_id", "node_count", "law_count", "crosswalk_count","projection_count","hierarchy_status", "canonicalization", "adapter", "adapter_version", "inputs", "required_input_roles", "build_recipe", "corpus_sha256", "crosswalk_sha256","projection_sha256", "build_options_sha256"}
    schema = manifest.get("schema") if type(manifest) is dict else None
    if schema in {_MANIFEST_SCHEMA, _MANIFEST_SCHEMA_RIGHTS}:
        expected |= {"acquisition", "conversion", "converted_at"}
    # The key set is exact per schema, so a v5 manifest cannot smuggle in a
    # rights area and a v6 manifest cannot drop one.
    if schema == _MANIFEST_SCHEMA_RIGHTS:
        expected |= {"rights"}
    if type(manifest) is not dict or set(manifest) != expected or schema not in {_MANIFEST_SCHEMA, _MANIFEST_SCHEMA_RIGHTS, _LEGACY_MANIFEST_SCHEMA}: raise ValidationError("MANIFEST_KEYS")
    counts = ("node_count", "law_count", "crosswalk_count", "projection_count")
    options = ("corpus_id", "adapter", "adapter_version", "canonicalization", "hierarchy_status")
    recipe=manifest["build_recipe"]
    if any(type(manifest[key]) is not int or manifest[key] < 0 for key in counts) or any(not isinstance(manifest[key], str) or not manifest[key] for key in options) or not isinstance(manifest["inputs"], list) or not isinstance(manifest["required_input_roles"],list) or any(not isinstance(role,str) or not role for role in manifest["required_input_roles"]) or type(recipe) is not dict or set(recipe)!={"adapter","mapping"} or not isinstance(recipe.get("adapter"),str) or (recipe.get("mapping") is not None and not isinstance(recipe.get("mapping"),dict)) or any(not _lower_hex_digest(manifest[key]) for key in _MANIFEST_DIGESTS): raise ValidationError("MANIFEST_TYPES")
    if manifest["adapter"] not in _MANIFEST_ADAPTERS or manifest["adapter_version"] != _MANIFEST_ADAPTER_VERSION or manifest["canonicalization"] != _MANIFEST_CANONICALIZATION or manifest["hierarchy_status"] not in {"full", "partial"}: raise ValidationError("MANIFEST_OPTIONS")
    if recipe["adapter"] != manifest["adapter"]: raise ValidationError("MANIFEST_RECIPE")
    corpus_file, crosswalk_file, projection_file = _canonical_artifact_paths(corpus_path, crosswalk_path, projection_path)
    corpus = corpus_file.read_bytes()
    crosswalk = read_crosswalk(crosswalk_file)
    if hashlib.sha256(corpus).hexdigest() != manifest["corpus_sha256"]: raise JLegalError("MANIFEST_CORPUS_TAMPERED")
    value = canonical_crosswalk_jsonl(crosswalk)
    if hashlib.sha256(value).hexdigest() != manifest["crosswalk_sha256"]: raise JLegalError("MANIFEST_CROSSWALK_TAMPERED")
    projection = read_projection(projection_file); projection_value=canonical_projection_jsonl(projection)
    if hashlib.sha256(projection_value).hexdigest() != manifest["projection_sha256"]: raise JLegalError("MANIFEST_PROJECTION_TAMPERED")
    artifacts = verify_canonical_artifacts(corpus_file, crosswalk_file, projection_file)
    nodes, crosswalk, projection = artifacts.nodes, artifacts.crosswalk, artifacts.projection
    if len(nodes) != manifest["node_count"] or len({n.law_id for n in nodes}) != manifest["law_count"] or len(crosswalk) != manifest["crosswalk_count"] or len(projection)!=manifest["projection_count"]: raise JLegalError("MANIFEST_COUNT_TAMPERED")
    previous: tuple[str,str] | None = None
    seen_uri_sha: dict[str,str] = {}
    for item in manifest["inputs"]:
        if type(item) is not dict or set(item)!={"role","uri","sha256"} or not isinstance(item["role"],str) or not item["role"] or not isinstance(item["uri"],str) or not item["uri"] or not _lower_hex_digest(item["sha256"]): raise ValidationError("MANIFEST_INPUTS")
    if not manifest["inputs"]: raise JLegalError("MANIFEST_INPUTS_REQUIRED")
    if schema in {_MANIFEST_SCHEMA, _MANIFEST_SCHEMA_RIGHTS}:
        if manifest["adapter"] != "egov_xml" or manifest["conversion"] != JLEGAL_CONVERTER or not _canonical_utc_timestamp(manifest["converted_at"]):
            raise ValidationError("MANIFEST_ACQUISITION")
        _egov_acquisition(Adaptation((), adapter="egov_xml", inputs=tuple(BuildInput(item["role"], item["uri"], item["sha256"]) for item in manifest["inputs"]), source_metadata=manifest["acquisition"]), manifest["acquisition"])
    if schema == _MANIFEST_SCHEMA_RIGHTS:
        # A manifest this profile did not write can still declare v6, so the
        # rights area is re-validated here rather than trusted. Key order is
        # not re-checked: build_options_sha256 is computed from parsed values,
        # exactly as it is for acquisition. A recorded null is malformed, not
        # silence, so this uses the non-sentinel variant of the check.
        _recorded_rights(manifest["rights"])
    roles=[item["role"] for item in manifest["inputs"]]
    expected_roles=_REQUIRED_INPUT_ROLES[manifest["adapter"]]; allowed_roles=expected_roles|_OPTIONAL_INPUT_ROLES.get(manifest["adapter"],frozenset())
    if len(roles) != len(set(roles)) or roles != sorted(roles) or roles != manifest["required_input_roles"] or len(manifest["required_input_roles"]) != len(set(manifest["required_input_roles"])) or set(roles) - allowed_roles or not expected_roles <= set(roles): raise JLegalError("MANIFEST_INPUT_ROLES")
    for item in manifest["inputs"]:
        if item["uri"] == _INLINE_MAPPING_URI:
            if item["role"] != "mapping": raise JLegalError("MANIFEST_INPUT_SYNTAX")
        elif content_uri_sha256(item["uri"]) != item["sha256"]:
            # content_uri_sha256 returns None for an unrecognized shape, which
            # also fails this comparison against the (always non-None) sha256.
            raise JLegalError("MANIFEST_INPUT_SYNTAX")
        key=(item["role"],item["uri"],item["sha256"])
        prior_sha=seen_uri_sha.setdefault(item["uri"],item["sha256"])
        if prior_sha != item["sha256"]: raise JLegalError("MANIFEST_INPUT_URI_CONFLICT")
        if previous is not None and key <= previous: raise JLegalError("MANIFEST_INPUT_ORDER")
        previous=key
    options = _manifest_options(manifest["adapter"],manifest["adapter_version"],manifest["canonicalization"],manifest["hierarchy_status"],manifest["inputs"],manifest["required_input_roles"],recipe,manifest.get("acquisition"),manifest.get("conversion"),manifest.get("rights"))
    if hashlib.sha256(canonical_json(options)).hexdigest() != manifest["build_options_sha256"]: raise JLegalError("MANIFEST_OPTIONS_TAMPERED")
    # role == "source" only: a node must never be able to claim a mapping
    # input's (uri, sha256) as its own provenance.
    declared_sources = {(item["uri"], item["sha256"]) for item in manifest["inputs"] if item["role"] == "source"}
    declared_hashes = {item["sha256"] for item in manifest["inputs"]}
    if any((node.source.uri, node.source.sha256) not in declared_sources for node in nodes): raise JLegalError("MANIFEST_NODE_PROVENANCE")
    if any(row.source_sha256 not in declared_hashes for row in crosswalk): raise JLegalError("MANIFEST_CROSSWALK_PROVENANCE")
    if verify_inputs:
        # The mapping input is always taken from build_recipe, embedded in the
        # manifest itself; it is never resolved back to a file (uri is a
        # logical identifier, not a path).
        for item in manifest["inputs"]:
            if item["uri"] == _INLINE_MAPPING_URI:
                if item["role"] != "mapping" or hashlib.sha256(canonical_json(recipe["mapping"])).hexdigest() != item["sha256"]: raise JLegalError("MANIFEST_RECIPE_MAPPING")
        # The source input is a logical identifier too, so replay cannot guess
        # a path from it; the caller must supply the file explicitly.
        if source is None: raise JLegalError("MANIFEST_REPLAY_SOURCE_REQUIRED")
        source_path = Path(source)
        if not source_path.exists(): raise JLegalError("MANIFEST_INPUT_UNAVAILABLE")
        source_item = next(item for item in manifest["inputs"] if item["role"] == "source")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_item["sha256"]: raise JLegalError("MANIFEST_REPLAY_SOURCE_MISMATCH")
        _rebuild_from_manifest(manifest,corpus,value,projection_value,source_path)
    return manifest


def _validate_adaptation(adaptation: Adaptation) -> None:
    if not isinstance(adaptation, Adaptation) or not isinstance(adaptation.adapter, str) or not adaptation.adapter or not isinstance(adaptation.version, str) or not adaptation.version:
        raise ValidationError("ADAPTATION_INVALID")
    if not isinstance(adaptation.nodes, tuple) or not isinstance(adaptation.crosswalk, tuple) or type(adaptation.partial_hierarchy) is not bool:
        raise ValidationError("ADAPTATION_INVALID")
    if not all(isinstance(item, BuildInput) and isinstance(item.role, str) and item.role and isinstance(item.uri, str) and item.uri and _lower_hex_digest(item.sha256) for item in adaptation.inputs):
        raise ValidationError("ADAPTATION_INVALID")
    roles = [item.role for item in adaptation.inputs]
    if not roles or len(roles) != len(set(roles)):
        raise ValidationError("ADAPTATION_INVALID")
    if adaptation.source_metadata is not None and type(adaptation.source_metadata) is not dict:
        raise ValidationError("ADAPTATION_INVALID")


def compile_adaptation(
    adaptation: Adaptation,
    *,
    corpus_id: str,
    out_dir: str | Path,
    mapping: dict[str, Any] | None = None,
    mapping_path: str | Path | None = None,
    acquisition: dict[str, Any] | None = None,
    converted_at: str | None = None,
    rights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a validated public adaptation into the four canonical artifacts."""
    _validate_adaptation(adaptation)
    rights = _rights(rights)
    destination = _safe(out_dir)
    if destination.exists(): raise JLegalError(f"OUTPUT_EXISTS_REFUSED: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mapping is not None: adaptation=replace(adaptation,inputs=adaptation.inputs+(_mapping_input(mapping,mapping_path),))
    _validate_adaptation(adaptation)
    recipe=_build_recipe(adaptation.adapter,mapping)
    acquisition = _egov_acquisition(adaptation, acquisition)
    if rights is not None and acquisition is None:
        # The rights area is defined for this profile's manifest only; the
        # legacy generic-adapter manifest keeps its v3 shape unchanged.
        raise ValidationError("RIGHTS_PROFILE_REQUIRED")
    if acquisition is not None:
        if converted_at is None:
            converted_at = _now_canonical_utc()
        elif not _canonical_utc_timestamp(converted_at):
            raise ValidationError("ACQUISITION_CONVERTED_AT")
    adaptation=_bind_build_provenance(adaptation,recipe,adaptation.inputs)
    nodes, crosswalk = list(adaptation.nodes), list(adaptation.crosswalk)
    validate_corpus(nodes, crosswalk)
    stage = Path(tempfile.mkdtemp(prefix=destination.name + ".stage.", dir=destination.parent))
    try:
        corpus = canonical_jsonl(nodes); crosswalk_bytes = canonical_crosswalk_jsonl(crosswalk); projection=make_projection(nodes); projection_bytes=canonical_projection_jsonl(projection)
        manifest = manifest_for(corpus_id, nodes, crosswalk, projection, adaptation, corpus, recipe, acquisition, converted_at, rights)
        _atomic_bytes(stage / "corpus.jsonl", corpus); _atomic_bytes(stage / "crosswalk.jsonl", crosswalk_bytes); _atomic_bytes(stage / "projection.jsonl", projection_bytes); _atomic_bytes(stage / "manifest.json", canonical_json(manifest) + b"\n")
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise
    return {"out_dir": str(destination), "corpus": str(destination / "corpus.jsonl"), "crosswalk": str(destination / "crosswalk.jsonl"), "projection":str(destination/"projection.jsonl"), "manifest": str(destination / "manifest.json"), "nodes": len(nodes), "corpus_id": corpus_id}


def compile_corpus(input_path: str | Path, *, adapter: str | None, out_dir: str | Path, corpus_id: str, mapping: dict[str, Any] | None = None, mapping_path: str | Path | None = None, acquisition: dict[str, Any] | None = None, converted_at: str | None = None, rights: dict[str, Any] | None = None) -> dict[str, Any]:
    adaptation = default_registry().adapt(input_path, name=adapter, mapping=mapping)
    return compile_adaptation(adaptation, corpus_id=corpus_id, out_dir=out_dir, mapping=mapping, mapping_path=mapping_path, acquisition=acquisition, converted_at=converted_at, rights=rights)
