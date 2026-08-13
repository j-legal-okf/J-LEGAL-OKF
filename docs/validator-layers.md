# Validator Layer × Diagnostic Code Map

## Status and scope

[`jlegal-okf-profile-0.1.0-draft.md`, "Provenance, normalization, and
validation policy"](jlegal-okf-profile-0.1.0-draft.md#provenance-normalization-and-validation-policy)
organizes `validate_corpus()`'s checks into four layers (syntax, structure,
source fidelity, semantic and temporal relations) but states that the
code-to-layer map itself was not yet written. This document is that map.

It does not introduce new diagnostic codes, change what any existing code
means, or change when a code fires. It only classifies the 36 diagnostic
codes `collect_diagnostics()` (`src/jlegal_okf/validation.py`) can emit. The
same classification is encoded machine-readably as `DIAGNOSTIC_LAYERS` in
`src/jlegal_okf/validation.py`, and `Diagnostic.to_dict()` includes it as a
`"layer"` field. `tests/test_validator_layers.py` checks, section by
section, that this document's `{code: layer}` assignment (which numbered
`### N.` section each code's table row is under) equals `DIAGNOSTIC_LAYERS`
exactly, and that `DIAGNOSTIC_LAYERS` names exactly the codes
`validation.py` can actually emit — so a code added, removed, renamed, or
moved to a different layer in only one of the three places (doc section,
`DIAGNOSTIC_LAYERS`, `validation.py`) fails the test suite.

Run `jlegal validate --corpus ... --manifest ... --diagnostics-json` to get
each diagnostic's layer alongside its code, subject, and detail as a JSON
array (see the CLI section below).

## The four layers

### Classification principle

Layers are assigned by the **field family a check targets**, not by the
mechanical shape of the check. Syntax and source fidelity both contain
plain type/range checks (`ORDINAL_POSITIVE` and `SOURCE_PAGE` reject
exactly the same shape of value — a present-but-non-positive `int` — on
different fields); what separates them is which field is being checked.
Source fidelity is every check, regardless of whether it validates a
format or actually cross-references recorded evidence, on a field from the
source-evidence family: `SourceRef`'s `uri`/`sha256`/`adapter`/
`source_key`/`page`/`byte_start`/`byte_end`, and its crosswalk-side analog
`source_sha256`. Only `CROSSWALK_SOURCE_MISMATCH` in that family performs
an actual byte-level cross-reference (comparing a crosswalk row's recorded
hash against the resolved target node's own hash); `SOURCE_SHA256`,
`SOURCE_RANGE`, `SOURCE_PAGE`, `SOURCE_URI`, and `MALFORMED_SHA` are format
or presence checks on those same source-evidence fields, not comparisons
against the original bytes themselves — they are grouped with
`CROSSWALK_SOURCE_MISMATCH` by field family, not by check nature. Syntax is
the same family of type/required-value/forbidden-character checks applied
everywhere else. Two of its codes, `STRING_TYPE` and `NUL_FORBIDDEN`, are
whole-node sweeps: they check every string-valued field of a node in one
pass, which necessarily includes `source.uri`, `source.adapter`, and
`source.source_key`. They are classified as syntax because they do not
target the source-evidence family specifically — they apply a uniform
type/character rule across the whole node, source-evidence fields
included, rather than singling that family out. The check that targets
`source.uri` and `source.adapter` specifically (not as part of a
whole-node sweep) is `SOURCE_URI`, which lives in source fidelity.

### 1. Syntax

Type, required-value, and forbidden-character checks on a single field
outside the source-evidence family described above (see "Classification
principle"), independent of where that field sits in the corpus tree or
how it relates to other nodes.

| Code | What it checks |
| --- | --- |
| `STRING_TYPE` | `jurisdiction`, `authority`, `locator`, `text`, `source.uri`, `source.adapter`, `source.source_key`, `label`, and `heading` are all `str`. |
| `NUL_FORBIDDEN` | None of those same string fields contain a NUL (`\0`) character. |
| `ORDINAL_POSITIVE` | `ordinal`, when present, is a positive `int`. |
| `BRANCH_POSITIVE` | Every entry of `branch` is a positive `int`. |
| `CROSSWALK_FIELDS` | A `LegacyCrosswalk` row's `legacy_id`, `target_node_id`, `target_version_id`, `relation`, and `reason` all have the required types. |

### 2. Structure

Tree shape, parent/child relations, and identifier/locator uniqueness —
whether the corpus forms one well-formed, referentially consistent tree per
law.

| Code | What it checks |
| --- | --- |
| `CORPUS_EMPTY` | The corpus has at least one node. |
| `IDENTITY_NORMALIZED` | `law_identifier()` can be computed at all from a node's `jurisdiction`/`authority`/`law_number_key`/`source_law_key` (fails when one normalizes to empty). Precedes, and shares its identity family with, `ID_LAW`/`ID_NODE`/`ID_VERSION` below. |
| `ID_LAW` | A node's stored `law_id` matches `law_identifier()` recomputed from its fields. |
| `ID_NODE` | A node's stored `node_id` matches `node_identifier()` recomputed from `law_id` and `locator`. |
| `ID_VERSION` | A node's stored `version_id` matches `version_identifier()` recomputed from its content fields. |
| `DUPLICATE_VERSION` | No `version_id` appears more than once in the corpus. |
| `LOCATOR_DUPLICATE` | No `(law_id, locator)` pair resolves to more than one `node_id`. |
| `LOCATOR_GRAMMAR` | `locator` matches the `/law(/segment)+` grammar (`valid_locator()`). |
| `ROOT_KIND` | A node with no `parent_id` has `kind == NodeKind.LAW`. |
| `ROOT_DEPTH` | A node with no `parent_id` has `depth == 0`. |
| `PARENT_DEPTH` | A non-root node's `depth` is exactly one greater than some version of its declared parent's `depth`. |
| `PARENT_MISSING` | A non-root node's `parent_id` resolves to at least one known node. |
| `PARENT_LAW` | At least one version of the declared parent shares the child's `law_id`. |
| `KIND_TRANSITION` | At least one version of the declared parent allows the child's `kind` as a child (`_ALLOWED` table). |
| `LAW_ROOT_COUNT` | Each `law_id` has exactly one distinct root `node_id`. |
| `TREE_CYCLE` | Walking a node's `parent_id` chain never revisits a `node_id` already seen. |
| `TREE_UNREACHABLE` | Walking a node's `parent_id` chain terminates at a root (a node with no `parent_id`), rather than dead-ending on a missing parent. |
| `CROSSWALK_DUPLICATE_TARGET` | No `legacy_id` maps to the same `target_version_id` more than once. |
| `CROSSWALK_TARGET` | A crosswalk row's `target_version_id` resolves to a known node whose `node_id` matches the row's `target_node_id`. |

### 3. Source fidelity

Every check — format, presence, or actual cross-reference — on the
source-evidence field family: a node's or crosswalk row's recorded hash,
byte/page range, and URI pointing back to the original source bytes it was
derived from (see "Classification principle" above for why format checks
on these fields live here rather than in syntax).

| Code | What it checks |
| --- | --- |
| `SOURCE_SHA256` | `source.sha256` is a well-formed 64-character lowercase hex digest. |
| `SOURCE_RANGE` | `source.byte_start`/`source.byte_end` are both present or both absent, both `int` when present, non-negative, and ordered (`byte_start <= byte_end`). |
| `SOURCE_PAGE` | `source.page`, when present, is a positive `int`. |
| `SOURCE_URI` | `source.uri` and `source.adapter` are both present, non-empty strings. |
| `CROSSWALK_SOURCE_MISMATCH` | A crosswalk row's `source_sha256` matches the resolved target node's `source.sha256`. |
| `MALFORMED_SHA` | A crosswalk row's `source_sha256` is a well-formed 64-character lowercase hex digest (the crosswalk-side counterpart of `SOURCE_SHA256`). |

### 4. Semantic and temporal relations

Time-based relations between versions of the same node, cross-version
semantic identity, and the reasoning recorded for crosswalk judgments.

| Code | What it checks |
| --- | --- |
| `TEMPORAL_OVERLAP` | Consecutive versions of the same `node_id`, ordered by `valid_from`, do not have overlapping validity windows. |
| `SEMANTIC_IDENTITY_DRIFT` | All versions sharing a `node_id` agree on `(parent_id, kind, ordinal, branch)` — a `node_id` never silently changes what it structurally identifies. |
| `PARENT_TEMPORAL` | At least one version of the declared parent's validity window contains the child's validity window (`_contains()`). |
| `CROSSWALK_AMBIGUOUS_REASON` | A crosswalk row with `relation == AMBIGUOUS` has a non-empty `reason`. |
| `CROSSWALK_EXACT_REASON` | A crosswalk row with `relation == EXACT` has no `reason` (a reason would contradict "exact"). |
| `CROSSWALK_REPEATED_POLICY` | When the same `legacy_id` appears in more than one crosswalk row, every row for it is `AMBIGUOUS` with a `reason`, and each row targets a distinct `target_version_id`. |

## CLI: machine-readable diagnostics

`jlegal validate`'s default output is unchanged:
`{"valid": true, "nodes": N}` on success, or a `ValidationError` message on
stderr with exit code 2 on failure.

Passing `--diagnostics-json` instead prints the full diagnostic list —
success or failure — as a JSON array of
`{"code": ..., "subject": ..., "detail": ..., "layer": ...}` objects, and
exits 2 if the array is non-empty (0 otherwise). This applies only to
`validate_corpus()`'s diagnostics: `--diagnostics-json` runs after
`verify_manifest()`, so a manifest-level failure (a tampered or
inconsistent `corpus.jsonl`/`manifest.json`/`crosswalk.jsonl`, e.g.
`MANIFEST_CORPUS_TAMPERED`) still raises before the flag has any effect
and is still reported as a plain-text message on stderr, not as a JSON
array. Its exit code follows the CLI's general error mapping rather than
this flag's: manifest tamper/provenance failures (for example
`MANIFEST_CORPUS_TAMPERED`, `MANIFEST_REPLAY_SOURCE_REQUIRED`) raise
`JLegalError` and exit 3, while manifest schema/type failures (for example
`MANIFEST_JSON`, `MANIFEST_KEYS`, `MANIFEST_RECIPE`) raise `ValidationError`
and exit 2.

```
$ jlegal validate --corpus corpus.jsonl --manifest manifest.json --diagnostics-json
[]
$ echo $?
0
```

```
$ jlegal validate --corpus broken.jsonl --manifest manifest.json --diagnostics-json
[{"code": "ROOT_KIND", "detail": "", "layer": "structure", "subject": "node_..."}]
$ echo $?
2
```
