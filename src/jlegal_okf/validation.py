"""Stable, aggregate corpus diagnostics for the v1 contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import ValidationError
from .model import CrosswalkRelation, LegalNode, LegacyCrosswalk, NodeKind, law_identifier, node_identifier, valid_locator, version_identifier


@dataclass(frozen=True, order=True)
class Diagnostic:
    code: str
    subject: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "subject": self.subject, "detail": self.detail, "layer": DIAGNOSTIC_LAYERS[self.code]}


# Which of the four validator layers (see docs/validator-layers.md) each
# diagnostic code belongs to. Every code this module's collect_diagnostics()
# can emit via add(...) must have an entry here — enforced by
# tests/test_validator_layers.py, which also checks this table against the
# human-readable copy in docs/validator-layers.md.
DIAGNOSTIC_LAYERS: dict[str, str] = {
    # syntax: type, required-value, and forbidden-character checks on a single field.
    "STRING_TYPE": "syntax",
    "NUL_FORBIDDEN": "syntax",
    "ORDINAL_POSITIVE": "syntax",
    "BRANCH_POSITIVE": "syntax",
    "CROSSWALK_FIELDS": "syntax",
    # structure: tree shape, parent/child relations, and identifier/locator uniqueness.
    "CORPUS_EMPTY": "structure",
    "IDENTITY_NORMALIZED": "structure",
    "ID_LAW": "structure",
    "ID_NODE": "structure",
    "ID_VERSION": "structure",
    "DUPLICATE_VERSION": "structure",
    "LOCATOR_DUPLICATE": "structure",
    "LOCATOR_GRAMMAR": "structure",
    "ROOT_KIND": "structure",
    "ROOT_DEPTH": "structure",
    "PARENT_DEPTH": "structure",
    "PARENT_MISSING": "structure",
    "PARENT_LAW": "structure",
    "KIND_TRANSITION": "structure",
    "LAW_ROOT_COUNT": "structure",
    "TREE_CYCLE": "structure",
    "TREE_UNREACHABLE": "structure",
    "CROSSWALK_DUPLICATE_TARGET": "structure",
    "CROSSWALK_TARGET": "structure",
    # source_fidelity: correspondence to the original source bytes (hash/range/page/URI).
    "SOURCE_SHA256": "source_fidelity",
    "SOURCE_RANGE": "source_fidelity",
    "SOURCE_PAGE": "source_fidelity",
    "SOURCE_URI": "source_fidelity",
    "CROSSWALK_SOURCE_MISMATCH": "source_fidelity",
    "MALFORMED_SHA": "source_fidelity",
    # semantic_temporal: time-based relations, cross-version identity, and crosswalk judgment reasons.
    "TEMPORAL_OVERLAP": "semantic_temporal",
    "SEMANTIC_IDENTITY_DRIFT": "semantic_temporal",
    "PARENT_TEMPORAL": "semantic_temporal",
    "CROSSWALK_AMBIGUOUS_REASON": "semantic_temporal",
    "CROSSWALK_EXACT_REASON": "semantic_temporal",
    "CROSSWALK_REPEATED_POLICY": "semantic_temporal",
}


_ALLOWED: dict[NodeKind, set[NodeKind]] = {
    NodeKind.LAW: {NodeKind.PREAMBLE, NodeKind.MAIN_PROVISION, NodeKind.PART, NodeKind.CHAPTER, NodeKind.SECTION, NodeKind.SUBSECTION, NodeKind.DIVISION, NodeKind.ARTICLE, NodeKind.APPENDIX, NodeKind.SUPPLEMENTARY_PROVISION, NodeKind.TABLE},
    NodeKind.PREAMBLE: {NodeKind.PARAGRAPH},
    NodeKind.MAIN_PROVISION: {NodeKind.PART, NodeKind.CHAPTER, NodeKind.SECTION, NodeKind.SUBSECTION, NodeKind.DIVISION, NodeKind.ARTICLE, NodeKind.PARAGRAPH, NodeKind.APPENDIX, NodeKind.TABLE},
    NodeKind.PART: {NodeKind.CHAPTER, NodeKind.SECTION, NodeKind.SUBSECTION, NodeKind.DIVISION, NodeKind.ARTICLE},
    NodeKind.CHAPTER: {NodeKind.SECTION, NodeKind.SUBSECTION, NodeKind.DIVISION, NodeKind.ARTICLE},
    NodeKind.SECTION: {NodeKind.SUBSECTION, NodeKind.DIVISION, NodeKind.ARTICLE},
    NodeKind.SUBSECTION: {NodeKind.DIVISION, NodeKind.ARTICLE},
    NodeKind.DIVISION: {NodeKind.ARTICLE},
    NodeKind.ARTICLE: {NodeKind.PARAGRAPH, NodeKind.ITEM, NodeKind.TABLE},
    NodeKind.PARAGRAPH: {NodeKind.ITEM, NodeKind.TABLE, NodeKind.AMENDMENT_PROVISION}, NodeKind.ITEM: {NodeKind.SUBITEM, NodeKind.TABLE}, NodeKind.SUBITEM: {NodeKind.SUBITEM, NodeKind.TABLE},
    NodeKind.APPENDIX: {NodeKind.TABLE, NodeKind.ROW, NodeKind.CELL}, NodeKind.SUPPLEMENTARY_PROVISION: {NodeKind.CHAPTER, NodeKind.ARTICLE, NodeKind.PARAGRAPH, NodeKind.ITEM, NodeKind.SUBITEM, NodeKind.APPENDIX, NodeKind.TABLE},
    NodeKind.AMENDMENT_PROVISION: set(),
    NodeKind.TABLE: {NodeKind.ROW}, NodeKind.ROW: {NodeKind.CELL}, NodeKind.CELL: set(),
}


def _contains(parent: LegalNode, child: LegalNode) -> bool:
    start_ok = parent.valid_from is None or (child.valid_from is not None and parent.valid_from <= child.valid_from)
    end_ok = parent.valid_to is None or (child.valid_to is not None and child.valid_to <= parent.valid_to)
    return start_ok and end_ok


def collect_diagnostics(nodes: Iterable[LegalNode], crosswalk: Sequence[LegacyCrosswalk] = ()) -> tuple[Diagnostic, ...]:
    items = list(nodes); problems: list[Diagnostic] = []
    def add(code: str, subject: str, detail: str = "") -> None: problems.append(Diagnostic(code, subject, detail))
    by_node: dict[str, list[LegalNode]] = {}
    seen_versions: set[str] = set()
    locator_law: dict[tuple[str, str], str] = {}
    root_laws: dict[str, list[LegalNode]] = {}
    if not items: add("CORPUS_EMPTY", "corpus")
    for n in items:
        subject = n.node_id
        try:
            law_identifier(n.jurisdiction,n.authority,n.law_number_key,n.source_law_key)
        except (TypeError,ValueError) as exc:
            add("IDENTITY_NORMALIZED",subject,str(exc)); continue
        if n.law_id != law_identifier(n.jurisdiction, n.authority, n.law_number_key, n.source_law_key): add("ID_LAW", subject)
        if n.node_id != node_identifier(n.law_id, n.locator): add("ID_NODE", subject)
        if n.version_id != version_identifier(n.node_id, n.temporal, n.text, n.heading, n.label, n.attributes): add("ID_VERSION", subject)
        if n.version_id in seen_versions: add("DUPLICATE_VERSION", n.version_id)
        seen_versions.add(n.version_id)
        key = (n.law_id, n.locator)
        prior = locator_law.setdefault(key, n.node_id)
        if prior != n.node_id: add("LOCATOR_DUPLICATE", subject, n.locator)
        if not valid_locator(n.locator): add("LOCATOR_GRAMMAR", subject, n.locator)
        by_node.setdefault(n.node_id, []).append(n)
        if n.ordinal is not None and (type(n.ordinal) is not int or n.ordinal <= 0): add("ORDINAL_POSITIVE", subject)
        if any(type(value) is not int or value <= 0 for value in n.branch): add("BRANCH_POSITIVE", subject)
        if n.source.sha256 != n.source.sha256.lower() or len(n.source.sha256) != 64 or any(c not in "0123456789abcdef" for c in n.source.sha256): add("SOURCE_SHA256", subject)
        pair = (n.source.byte_start, n.source.byte_end)
        if (pair[0] is None) != (pair[1] is None) or (pair[0] is not None and (type(pair[0]) is not int or type(pair[1]) is not int or pair[0] < 0 or pair[0] > pair[1])): add("SOURCE_RANGE", subject)
        if n.source.page is not None and (type(n.source.page) is not int or n.source.page <= 0): add("SOURCE_PAGE", subject)
        strings = (n.jurisdiction, n.authority, n.locator, n.text, n.source.uri, n.source.adapter, n.source.source_key or "", n.label or "", n.heading or "")
        if any(not isinstance(value,str) for value in strings): add("STRING_TYPE", subject)
        elif any("\0" in value for value in strings): add("NUL_FORBIDDEN", subject)
        if n.parent_id is None:
            root_laws.setdefault(n.law_id, []).append(n)
            if n.kind is not NodeKind.LAW: add("ROOT_KIND", subject)
            if n.depth != 0: add("ROOT_DEPTH", subject)
        elif n.depth <= 0:
            add("PARENT_DEPTH", subject)
        if not n.source.uri or not n.source.adapter or not isinstance(n.source.uri, str): add("SOURCE_URI", subject)
    for node_id, versions in by_node.items():
        versions.sort(key=lambda x: (x.valid_from is not None, x.valid_from or ""))
        for left, right in zip(versions, versions[1:]):
            if left.valid_to is None or right.valid_from is None or right.valid_from < left.valid_to:
                add("TEMPORAL_OVERLAP", node_id)
        identities={(x.parent_id,x.kind,x.ordinal,x.branch) for x in versions}
        if len(identities) != 1: add("SEMANTIC_IDENTITY_DRIFT", node_id)
    for n in items:
        if n.parent_id is None: continue
        parents = by_node.get(n.parent_id, [])
        if not parents: add("PARENT_MISSING", n.node_id); continue
        if not any(p.law_id == n.law_id for p in parents): add("PARENT_LAW", n.node_id)
        if not any(p.depth + 1 == n.depth for p in parents): add("PARENT_DEPTH", n.node_id)
        if not any(n.kind in _ALLOWED.get(p.kind, set()) for p in parents): add("KIND_TRANSITION", n.node_id)
        if not any(_contains(p, n) for p in parents): add("PARENT_TEMPORAL", n.node_id)
    for law_id in {x.law_id for x in items}:
        roots = root_laws.get(law_id, [])
        if len({x.node_id for x in roots}) != 1: add("LAW_ROOT_COUNT", law_id)
    for n in items:
        seen: set[str] = set(); current = n
        while current.parent_id:
            if current.node_id in seen: add("TREE_CYCLE", n.node_id); break
            seen.add(current.node_id)
            parents = by_node.get(current.parent_id, [])
            if not parents: break
            current = parents[0]
        if current.parent_id is not None: add("TREE_UNREACHABLE", n.node_id)
    targets = {n.version_id: n for n in items}
    old_ids: dict[str,list[LegacyCrosswalk]] = {}
    for x in crosswalk:
        identifier=x.legacy_id if isinstance(x.legacy_id,str) else "<malformed-legacy-id>"
        if not isinstance(x.legacy_id,str) or not isinstance(x.target_node_id,str) or not isinstance(x.target_version_id,str) or not isinstance(x.relation,CrosswalkRelation) or (x.reason is not None and not isinstance(x.reason,str)): add("CROSSWALK_FIELDS",identifier)
        prior=old_ids.setdefault(identifier, [])
        if any(y.target_version_id == x.target_version_id for y in prior): add("CROSSWALK_DUPLICATE_TARGET", identifier)
        prior.append(x)
        target = targets.get(x.target_version_id) if isinstance(x.target_version_id, str) else None
        if target is None or target.node_id != x.target_node_id: add("CROSSWALK_TARGET", identifier)
        elif x.source_sha256 != target.source.sha256: add("CROSSWALK_SOURCE_MISMATCH", identifier)
        if x.relation is CrosswalkRelation.AMBIGUOUS and not x.reason: add("CROSSWALK_AMBIGUOUS_REASON", identifier)
        if x.relation is CrosswalkRelation.EXACT and x.reason: add("CROSSWALK_EXACT_REASON", identifier)
        if not isinstance(x.source_sha256,str) or len(x.source_sha256) != 64 or x.source_sha256.lower() != x.source_sha256 or any(c not in "0123456789abcdef" for c in x.source_sha256): add("MALFORMED_SHA", identifier)
    for legacy_id, rows in old_ids.items():
        if len(rows)>1 and (any(x.relation is not CrosswalkRelation.AMBIGUOUS or not x.reason for x in rows) or len({str(x.target_version_id) for x in rows}) != len(rows)): add("CROSSWALK_REPEATED_POLICY", legacy_id)
    return tuple(sorted(set(problems)))


def validate_corpus(nodes: Iterable[LegalNode], crosswalk: Sequence[LegacyCrosswalk] = (), *, raise_on_error: bool = True) -> tuple[Diagnostic, ...]:
    diagnostics = collect_diagnostics(nodes, crosswalk)
    if diagnostics and raise_on_error:
        message = "validation failed: " + "; ".join(f"{x.code}:{x.subject}" for x in diagnostics)
        raise ValidationError(message, diagnostics)
    return diagnostics
