"""Structured, mapping-driven public adapters; no legacy fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from .errors import AdapterError
from .model import LegalNode, LegacyCrosswalk, NodeKind, SourceRef, Temporal, content_addressed_uri, law_identifier, semantic_locator


@dataclass(frozen=True)
class BuildInput:
    """A role-labelled build dependency, separate from node evidence."""
    role: str
    uri: str
    sha256: str

    @classmethod
    def from_source(cls, role: str, source: SourceRef) -> "BuildInput":
        return cls(role, source.uri, source.sha256)


@dataclass(frozen=True)
class Adaptation:
    nodes: tuple[LegalNode, ...]
    crosswalk: tuple[LegacyCrosswalk, ...] = ()
    adapter: str = "unknown"
    version: str = "1"
    inputs: tuple[BuildInput, ...] = ()
    partial_hierarchy: bool = False
    # Retrieval evidence is separate from deterministic legal-node identity.
    source_metadata: dict[str, Any] | None = None


Adapter = Callable[[Path, dict[str, Any] | None], Adaptation]


class AdapterRegistry:
    def __init__(self) -> None: self._adapters: dict[str, tuple[int, Callable[[Path], bool], Adapter]] = {}
    def register(self, name: str, adapter: Adapter, *, sniff: Callable[[Path], bool], priority: int) -> None:
        if name in self._adapters: raise AdapterError(f"ADAPTER_DUPLICATE: {name}")
        self._adapters[name] = (priority, sniff, adapter)
    def adapt(self, path: str | Path, *, name: str | None = None, mapping: dict[str, Any] | None = None) -> Adaptation:
        source = Path(path)
        if name is not None:
            if name not in self._adapters: raise AdapterError(f"ADAPTER_UNKNOWN: {name}")
            return self._adapters[name][2](source, mapping)
        choices = [(priority, candidate, adapter) for candidate, (priority, test, adapter) in self._adapters.items() if test(source)]
        if not choices: raise AdapterError("ADAPTER_UNRECOGNIZED")
        best = max(x[0] for x in choices); winners = [x for x in choices if x[0] == best]
        if len(winners) != 1: raise AdapterError("ADAPTER_AMBIGUOUS: " + ",".join(sorted(x[1] for x in winners)))
        return winners[0][2](source, mapping)
    @property
    def names(self) -> tuple[str, ...]: return tuple(sorted(self._adapters))


def _ref(raw: bytes, adapter: str, **kwargs: Any) -> SourceRef:
    sha256 = hashlib.sha256(raw).hexdigest()
    return SourceRef(uri=content_addressed_uri(sha256), sha256=sha256, adapter=adapter, **kwargs)


def _temporal(raw: dict[str, Any]) -> Temporal:
    value = raw.get("temporal") or {}
    if isinstance(value, dict):
        return Temporal(valid_from=value.get("valid_from"), valid_to=value.get("valid_to"), promulgated=value.get("promulgated"), repealed=value.get("repealed"))
    raise AdapterError("ADAPTER_TEMPORAL")


def _branch(value: Any) -> tuple[int,...]:
    if value is None: return ()
    if isinstance(value,int): return (value,)
    if isinstance(value,list) and all(isinstance(x,int) for x in value): return tuple(value)
    raise AdapterError("ADAPTER_BRANCH")


def _tree_nodes(root: dict[str, Any], context: dict[str, Any], source: SourceRef, parent_id: str | None = None, parent_locator: str | None = None, depth: int = 0) -> list[LegalNode]:
    required = {"locator", "kind", "text"}
    if not required <= set(root): raise AdapterError("ADAPTER_RAW_NODE_FIELDS")
    merged = {**context, **root}; kind = NodeKind(merged["kind"])
    law_id = law_identifier(merged["jurisdiction"], merged["authority"], merged.get("law_number_key"), merged.get("source_law_key"))
    branch=_branch(merged.get("branch")); ordinal=merged.get("ordinal")
    locator = semantic_locator(law_id, parent_locator, kind, str(merged["locator"]), ordinal=ordinal, branch=branch, source_key=source.source_key or str(merged["locator"]))
    node = LegalNode(jurisdiction=merged["jurisdiction"], authority=merged["authority"], law_number_key=merged.get("law_number_key"), source_law_key=merged.get("source_law_key"), locator=locator, kind=kind, depth=depth, text=str(merged["text"]), temporal=_temporal(merged), source=source, parent_id=parent_id, ordinal=ordinal, branch=branch, label=merged.get("label"), heading=merged.get("heading"), attributes=tuple((str(k), str(v)) for k, v in merged.get("attributes", {}).items()))
    result = [node]
    child_segments: set[str] = set()
    for child in root.get("children", []):
        child_kind=NodeKind(child["kind"]); child_ordinal=child.get("ordinal"); child_branch=_branch(child.get("branch")); raw_segment=str(child.get("locator", ""))
        segment=semantic_locator(law_id,node.locator,child_kind,raw_segment,ordinal=child_ordinal,branch=child_branch,source_key=source.source_key or raw_segment)
        if segment in child_segments and "temporal" not in child: raise AdapterError("ADAPTER_SIBLING_COLLISION")
        child_segments.add(segment)
        result.extend(_tree_nodes(child, context, source, node.node_id, node.locator, node.depth + 1))
    return result


def json_adapter(path: Path, mapping: dict[str, Any] | None = None) -> Adaptation:
    if mapping: raise AdapterError("ADAPTER_JSON_MAPPING")
    raw = path.read_bytes(); value = json.loads(raw)
    if not isinstance(value, dict) or "nodes" not in value: raise AdapterError("ADAPTER_RAW_JSON_SHAPE")
    required = {"jurisdiction", "authority"}
    if not required <= set(value): raise AdapterError("ADAPTER_RAW_LAW_FIELDS")
    source = _ref(raw, "json", source_key=value.get("source_key"))
    context = {key: value.get(key) for key in ("jurisdiction", "authority", "law_number_key", "source_law_key", "temporal")}
    nodes: list[LegalNode] = []
    for item in value["nodes"]: nodes.extend(_tree_nodes(item, context, source))
    return Adaptation(tuple(nodes), adapter="json", inputs=(BuildInput.from_source("source", source),))


def _value(element: ET.Element, spec: Any) -> Any:
    if isinstance(spec, str): selector, typ = spec, "str"
    elif isinstance(spec, dict) and set(spec) <= {"path", "type"} and "path" in spec: selector, typ = spec["path"], spec.get("type", "str")
    else: raise AdapterError("ADAPTER_MAPPING_SELECTOR")
    value = element.get(selector[1:]) if selector.startswith("@") else (element.findtext(selector) or "")
    if value == "": return None
    if typ == "str": return value
    if typ == "int": return int(value)
    if typ == "date": return date.fromisoformat(value).isoformat()
    raise AdapterError("ADAPTER_MAPPING_TYPE")


def _mapped(root: ET.Element, raw: bytes, mapping: dict[str, Any], adapter: str) -> Adaptation:
    if set(mapping) != {"row", "fields"} or not isinstance(mapping["fields"], dict): raise AdapterError("ADAPTER_MAPPING_REQUIRED")
    fields = mapping["fields"]; needed = {"jurisdiction", "authority", "locator", "kind", "depth", "text"}
    if not needed <= set(fields) or not ({"law_number_key","source_law_key"}&set(fields)): raise AdapterError("ADAPTER_MAPPING_FIELDS")
    source = _ref(raw, adapter); prepared: list[dict[str, Any]] = []
    for element in root.findall(mapping["row"]):
        values = {name: _value(element, spec) for name, spec in fields.items()}
        values["temporal"] = Temporal(valid_from=values.pop("valid_from", None), valid_to=values.pop("valid_to", None), promulgated=values.pop("promulgated", None), repealed=values.pop("repealed", None))
        values["parent_locator"] = values.pop("parent_locator", None)
        prepared.append(values)
    ids: dict[str, tuple[str, str]] = {}; result: list[LegalNode] = []
    for values in prepared:
        parent_raw = values.pop("parent_locator"); parent = ids.get(parent_raw) if parent_raw else None
        if parent_raw and parent is None: raise AdapterError("ADAPTER_PARENT_UNRESOLVED")
        raw_locator = str(values.pop("locator")); kind = NodeKind(values.pop("kind"))
        law_id = law_identifier(values["jurisdiction"], values["authority"], values.get("law_number_key"), values.get("source_law_key"))
        ordinal=values.pop("ordinal",None); branch=_branch(values.pop("branch",None))
        locator = semantic_locator(law_id, parent[1] if parent else None, kind, raw_locator, ordinal=ordinal, branch=branch, source_key=raw_locator)
        node = LegalNode(source=source, parent_id=parent[0] if parent else None, law_number_key=values.pop("law_number_key", None), source_law_key=values.pop("source_law_key", None), ordinal=ordinal, branch=branch, label=values.pop("label", None), heading=values.pop("heading", None), attributes=tuple(), locator=locator, kind=kind, **values)
        ids[raw_locator] = (node.node_id, node.locator); result.append(node)
    return Adaptation(tuple(result), adapter=adapter, inputs=(BuildInput.from_source("source", source),))


def xml_adapter(path: Path, mapping: dict[str, Any] | None = None) -> Adaptation:
    if mapping is None: raise AdapterError("ADAPTER_XML_MAPPING_REQUIRED")
    raw = path.read_bytes(); return _mapped(ET.fromstring(raw), raw, mapping, "xml")


def html_adapter(path: Path, mapping: dict[str, Any] | None = None) -> Adaptation:
    if mapping is None: raise AdapterError("ADAPTER_HTML_MAPPING_REQUIRED")
    raw = path.read_bytes()
    try: root = ET.fromstring(raw)
    except ET.ParseError as exc: raise AdapterError("ADAPTER_HTML_XHTML_REQUIRED") from exc
    return _mapped(root, raw, mapping, "html")


def _suffix(suffix: str) -> Callable[[Path], bool]: return lambda p: p.suffix.lower() == suffix


def default_registry() -> AdapterRegistry:
    from .egov import egov_xml_adapter, is_egov_xml
    registry = AdapterRegistry(); registry.register("json", json_adapter, sniff=_suffix(".json"), priority=10); registry.register("xml", xml_adapter, sniff=_suffix(".xml"), priority=10); registry.register("egov_xml", egov_xml_adapter, sniff=is_egov_xml, priority=20); registry.register("html", html_adapter, sniff=lambda p: p.suffix.lower() in {".html", ".xhtml"}, priority=10)
    return registry
