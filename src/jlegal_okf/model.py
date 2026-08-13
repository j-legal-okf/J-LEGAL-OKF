"""Immutable canonical data model for the J-LEGAL-OKF JORI Engine corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any, Iterable

SCHEMA = "jori-corpus/v1"
ID_NAMESPACE = uuid.UUID("9b7b7100-8305-5e41-b8d4-e541ce517491")
_WS = re.compile(r"[\t\n\r\f\v ]+")
_LOCATOR = re.compile(r"^/law(?:/[a-z][a-z0-9_-]*)+$")


def normalize_identifier(value: str, *, authority_or_jurisdiction: bool = False) -> str:
    """NFKC identifiers, with ASCII whitespace collapsed (never applied to text)."""
    result = _WS.sub(" ", unicodedata.normalize("NFKC", value).strip())
    return result.lower() if authority_or_jurisdiction else result


def _uuid(name: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, name))

def _name(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def law_identifier(jurisdiction: str, authority: str, law_number_key: str | None, source_law_key: str | None) -> str:
    normalized_jurisdiction=normalize_identifier(jurisdiction,authority_or_jurisdiction=True)
    normalized_authority=normalize_identifier(authority,authority_or_jurisdiction=True)
    if not normalized_jurisdiction or not normalized_authority: raise ValueError("jurisdiction and authority must be nonempty after normalization")
    if law_number_key is not None:
        key=normalize_identifier(law_number_key)
        if not key: raise ValueError("law_number_key is supplied but empty after normalization")
        key_kind="law_number"
    else:
        key=normalize_identifier(source_law_key or "")
        if not key: raise ValueError("source_law_key is required and nonempty after normalization")
        key_kind="source_law"
    return "law_" + _uuid(_name({"jurisdiction":normalized_jurisdiction,"authority":normalized_authority,"key_kind":key_kind,"key":key}))


def node_identifier(law_id: str, locator: str) -> str:
    return "node_" + _uuid(_name({"law_id":normalize_identifier(law_id),"locator":normalize_identifier(locator)}))


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_CONTENT_URI_PREFIX = "jlegal:source:sha256:"


def content_addressed_uri(sha256: str) -> str:
    """A logical, path-independent identifier for a build input's declared bytes.

    Two builds of the same bytes from different local paths must reach the
    same identifier, so this never encodes a filesystem location.
    """
    return _CONTENT_URI_PREFIX + sha256


def content_uri_sha256(uri: str) -> str | None:
    """The embedded lower-hex digest when uri is a content-addressed identifier, else None."""
    if not uri.startswith(_CONTENT_URI_PREFIX):
        return None
    digest = uri[len(_CONTENT_URI_PREFIX):]
    if len(digest) != 64 or digest != digest.lower() or any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def version_identifier(node_id: str, temporal: "Temporal", text: str, heading: str | None = None, label: str | None = None, attributes: tuple[tuple[str,str], ...] = ()) -> str:
    """Version identity is canonical structured content, never delimiter concatenation."""
    payload={"node_id":normalize_identifier(node_id),"temporal":temporal.to_dict(),"text":text,"heading":heading,"label":label,"attributes":list(sorted(attributes))}
    return "ver_" + _uuid(_name(payload))


class NodeKind(str, Enum):
    LAW = "law"
    PREAMBLE = "preamble"
    MAIN_PROVISION = "main_provision"
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    DIVISION = "division"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    ITEM = "item"
    SUBITEM = "subitem"
    APPENDIX = "appendix"
    SUPPLEMENTARY_PROVISION = "supplementary_provision"
    AMENDMENT_PROVISION = "amendment_provision"
    TABLE = "table"
    ROW = "row"
    CELL = "cell"


class CrosswalkRelation(str, Enum):
    EXACT = "exact"
    DERIVED = "derived"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Temporal:
    valid_from: str | None = None
    valid_to: str | None = None
    promulgated: str | None = None
    repealed: str | None = None

    def __post_init__(self) -> None:
        for name in ("valid_from", "valid_to", "promulgated", "repealed"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, date.fromisoformat(value).isoformat())
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to")

    def to_dict(self) -> dict[str, str | None]:
        return {"valid_from": self.valid_from, "valid_to": self.valid_to, "promulgated": self.promulgated, "repealed": self.repealed}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Temporal":
        expected = {"valid_from", "valid_to", "promulgated", "repealed"}
        if set(raw) != expected:
            raise ValueError("TEMPORAL_KEYS")
        return cls(**raw)


@dataclass(frozen=True)
class SourceRef:
    uri: str
    sha256: str
    adapter: str
    source_key: str | None = None
    page: int | None = None
    byte_start: int | None = None
    byte_end: int | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(value,str) or not value for value in (self.uri,self.sha256,self.adapter)) or (self.source_key is not None and (not isinstance(self.source_key,str) or not self.source_key)): raise ValueError("SOURCE_STRING")
        if len(self.sha256) != 64 or self.sha256 != self.sha256.lower() or any(char not in "0123456789abcdef" for char in self.sha256): raise ValueError("SOURCE_SHA256")
        if self.page is not None and (type(self.page) is not int or self.page <= 0): raise ValueError("SOURCE_PAGE")
        if (self.byte_start is None) != (self.byte_end is None): raise ValueError("SOURCE_RANGE_PAIR")
        if self.byte_start is not None and (type(self.byte_start) is not int or type(self.byte_end) is not int or self.byte_start < 0 or self.byte_end < self.byte_start): raise ValueError("SOURCE_RANGE")

    def to_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "sha256": self.sha256, "adapter": self.adapter, "source_key": self.source_key, "page": self.page, "byte_start": self.byte_start, "byte_end": self.byte_end}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceRef":
        expected = {"uri", "sha256", "adapter", "source_key", "page", "byte_start", "byte_end"}
        if set(raw) != expected:
            raise ValueError("SOURCE_KEYS")
        return cls(**raw)


@dataclass(frozen=True)
class LegalNode:
    jurisdiction: str
    authority: str
    law_number_key: str | None
    source_law_key: str | None
    locator: str
    kind: NodeKind
    depth: int
    text: str
    temporal: Temporal
    source: SourceRef
    parent_id: str | None = None
    ordinal: int | None = None
    branch: tuple[int, ...] = ()
    label: str | None = None
    heading: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    law_id: str = field(init=False)
    node_id: str = field(init=False)
    version_id: str = field(init=False)

    def __post_init__(self) -> None:
        if any(not isinstance(value,str) for value in (self.jurisdiction,self.authority,self.locator,self.text)) or any(value is not None and not isinstance(value,str) for value in (self.law_number_key,self.source_law_key,self.label,self.heading)):
            raise ValueError("NODE_STRING")
        if not normalize_identifier(self.jurisdiction,authority_or_jurisdiction=True) or not normalize_identifier(self.authority,authority_or_jurisdiction=True) or not normalize_identifier(self.locator) or not self.text:
            raise ValueError("NODE_TEXT_EMPTY")
        if not isinstance(self.kind,NodeKind) or not isinstance(self.temporal,Temporal) or not isinstance(self.source,SourceRef) or (self.parent_id is not None and not isinstance(self.parent_id,str)):
            raise ValueError("NODE_TYPES")
        if type(self.depth) is not int or self.depth < 0: raise ValueError("NODE_DEPTH")
        if self.ordinal is not None and (type(self.ordinal) is not int or self.ordinal <= 0): raise ValueError("NODE_ORDINAL")
        if self.branch is None: object.__setattr__(self, "branch", ())
        elif isinstance(self.branch, int): object.__setattr__(self, "branch", (self.branch,))
        else: object.__setattr__(self, "branch", tuple(self.branch))
        if any(type(value) is not int or value <= 0 for value in self.branch): raise ValueError("NODE_BRANCH")
        if not isinstance(self.attributes,tuple) or any(not isinstance(entry,tuple) or len(entry)!=2 or not all(isinstance(value,str) for value in entry) for entry in self.attributes): raise ValueError("NODE_ATTRIBUTES")
        if len({key for key,_ in self.attributes}) != len(self.attributes): raise ValueError("NODE_ATTRIBUTES_DUPLICATE")
        object.__setattr__(self, "attributes", tuple(sorted(self.attributes)))
        law_id = law_identifier(self.jurisdiction, self.authority, self.law_number_key, self.source_law_key)
        node_id = node_identifier(law_id, self.locator)
        object.__setattr__(self, "law_id", law_id)
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "version_id", version_identifier(node_id, self.temporal, self.text, self.heading, self.label, self.attributes))

    @property
    def valid_from(self) -> str | None:
        return self.temporal.valid_from

    @property
    def valid_to(self) -> str | None:
        return self.temporal.valid_to

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA, "jurisdiction": self.jurisdiction, "authority": self.authority, "law_number_key": self.law_number_key,
            "source_law_key": self.source_law_key, "law_id": self.law_id, "node_id": self.node_id, "version_id": self.version_id,
            "parent_id": self.parent_id, "kind": self.kind.value, "locator": self.locator, "depth": self.depth, "ordinal": self.ordinal,
            "branch": list(self.branch), "label": self.label, "heading": self.heading, "attributes": dict(self.attributes), "text": self.text,
            "temporal": self.temporal.to_dict(), "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegalNode":
        expected = {"schema", "jurisdiction", "authority", "law_number_key", "source_law_key", "law_id", "node_id", "version_id", "parent_id", "kind", "locator", "depth", "ordinal", "branch", "label", "heading", "attributes", "text", "temporal", "source"}
        if set(raw) != expected or raw.get("schema") != SCHEMA or not isinstance(raw["attributes"], dict):
            raise ValueError("NODE_KEYS")
        if not isinstance(raw["branch"], list) or not all(isinstance(x,int) for x in raw["branch"]): raise ValueError("BRANCH_TYPE")
        node = cls(jurisdiction=raw["jurisdiction"], authority=raw["authority"], law_number_key=raw["law_number_key"], source_law_key=raw["source_law_key"], locator=raw["locator"], kind=NodeKind(raw["kind"]), depth=raw["depth"], text=raw["text"], temporal=Temporal.from_dict(raw["temporal"]), source=SourceRef.from_dict(raw["source"]), parent_id=raw["parent_id"], ordinal=raw["ordinal"], branch=tuple(raw["branch"]), label=raw["label"], heading=raw["heading"], attributes=tuple(raw["attributes"].items()))
        for field_name in ("law_id", "node_id", "version_id"):
            if raw[field_name] != getattr(node, field_name):
                raise ValueError(f"RECOMPUTED_{field_name.upper()}")
        return node


@dataclass(frozen=True)
class LegacyCrosswalk:
    legacy_id: str
    target_node_id: str
    target_version_id: str
    relation: CrosswalkRelation
    reason: str | None = None
    source_sha256: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(value,str) or not value for value in (self.legacy_id,self.target_node_id,self.target_version_id)) or not isinstance(self.relation,CrosswalkRelation) or (self.reason is not None and not isinstance(self.reason,str)):
            raise ValueError("CROSSWALK_FIELDS")
        if not isinstance(self.source_sha256,str) or len(self.source_sha256)!=64 or self.source_sha256 != self.source_sha256.lower() or any(char not in "0123456789abcdef" for char in self.source_sha256): raise ValueError("CROSSWALK_SOURCE_SHA256")

    def to_dict(self) -> dict[str, str | None]:
        return {"legacy_id": self.legacy_id, "target_node_id": self.target_node_id, "target_version_id": self.target_version_id, "relation": self.relation.value, "reason": self.reason, "source_sha256": self.source_sha256}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegacyCrosswalk":
        expected = {"legacy_id", "target_node_id", "target_version_id", "relation", "reason", "source_sha256"}
        if set(raw) != expected:
            raise ValueError("CROSSWALK_KEYS")
        return cls(raw["legacy_id"], raw["target_node_id"], raw["target_version_id"], CrosswalkRelation(raw["relation"]), raw["reason"], raw["source_sha256"])


@dataclass(frozen=True)
class RetrievalDocument:
    projection_id: str
    projection_version: str
    node_id: str
    version_id: str
    law_id: str
    locator: str
    heading: str | None
    text: str
    kind: NodeKind
    temporal: Temporal
    evidence: SourceRef

    def __post_init__(self) -> None:
        required=(self.projection_id,self.projection_version,self.node_id,self.version_id,self.law_id,self.locator,self.text)
        if any(not isinstance(value,str) or not value for value in required) or not valid_locator(self.locator) or (self.heading is not None and not isinstance(self.heading,str)) or not isinstance(self.kind,NodeKind) or not isinstance(self.temporal,Temporal) or not isinstance(self.evidence,SourceRef): raise ValueError("PROJECTION_FIELDS")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "jori-projection/v1", "projection_id": self.projection_id, "projection_version": self.projection_version, "node_id": self.node_id, "version_id": self.version_id, "law_id": self.law_id, "locator": self.locator, "heading": self.heading, "text": self.text, "kind": self.kind.value, "temporal": self.temporal.to_dict(), "evidence": self.evidence.to_dict()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RetrievalDocument":
        expected = {"schema","projection_id","projection_version","node_id","version_id","law_id","locator","heading","text","kind","temporal","evidence"}
        if set(raw) != expected or raw["schema"] != "jori-projection/v1": raise ValueError("PROJECTION_KEYS")
        return cls(raw["projection_id"],raw["projection_version"],raw["node_id"],raw["version_id"],raw["law_id"],raw["locator"],raw["heading"],raw["text"],NodeKind(raw["kind"]),Temporal.from_dict(raw["temporal"]),SourceRef.from_dict(raw["evidence"]))


def semantic_locator(law_id: str, parent_locator: str | None, kind: NodeKind, segment: str, *, ordinal: int | None = None, branch: tuple[int, ...] = (), source_key: str | None = None, title: str | None = None, source_tag: str | None = None) -> str:
    """Canonical AST path; adapters never preserve uncontrolled external locators."""
    safe = re.sub(r"[^a-z0-9_-]+", "-", normalize_identifier(segment, authority_or_jurisdiction=True)).strip("-")
    if ordinal is not None:
        if source_tag is not None:
            normalized_tag = re.sub(r"[^a-z0-9_-]+", "-", normalize_identifier(source_tag, authority_or_jurisdiction=True)).strip("-")
            if not normalized_tag:
                raise ValueError("LOCATOR_SOURCE_TAG_REQUIRED")
            safe = f"{kind.value}-{normalized_tag}-{ordinal}"
        else:
            safe = f"{kind.value}-{ordinal}"
        safe += ("-" + "-".join(str(x) for x in branch) if branch else "")
    elif not safe:
        if not source_key: raise ValueError("LOCATOR_STABLE_SOURCE_KEY_REQUIRED")
        safe = "u-" + text_sha256(normalize_identifier(source_key))[:16]
    elif ordinal is None:
        safe = "u-" + text_sha256(normalize_identifier(segment))[:16] + "-" + safe[:32]
    if parent_locator is None: return "/law/root"
    return f"{parent_locator}/{kind.value}/{safe}"


def valid_locator(locator: str) -> bool:
    return bool(_LOCATOR.fullmatch(locator))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_jsonl(nodes: Iterable[LegalNode]) -> bytes:
    ordered = sorted(nodes, key=lambda n: (n.law_id, n.node_id, n.temporal.valid_from or "", n.temporal.valid_to or "9999-12-31", n.version_id))
    return b"".join(canonical_json(node.to_dict()) + b"\n" for node in ordered)
