# Known Limitations and Fail-Closed Behavior

## Status and scope

This document collects, in one place, the known limitations and fail-closed
behaviors that were previously scattered across
[`README.md`](../README.md), [`SECURITY.md`](../SECURITY.md), and
[`docs/jlegal-okf-profile-0.3.0-draft.md`](jlegal-okf-profile-0.3.0-draft.md).
It does not introduce new facts — every statement below is transcribed or
summarized from the reference implementation (`src/jlegal_okf/`) or from
one of those existing documents, each cited at point of use. Where those
documents still carry the fuller normative statement, this document links
back to them rather than duplicating it.

"Fail closed" means: when the implementation encounters an input it has not
been reviewed to handle correctly, it stops with a diagnostic rather than
guessing, discarding, or silently flattening the unreviewed part. The
sections below describe, for each area, what is supported and what
happens when it is not.

## 1. Supported structure

The reviewed e-Gov XML hierarchy is Law, Preamble, MainProvision, Part,
Chapter, Section, Subsection, Division, Article, Paragraph, Item, Subitem,
supplementary provisions, amendment provisions (with
`AmendProvisionSentence`), appendices, tables, rows, and cells
([profile §"Preservation and scope"](jlegal-okf-profile-0.3.0-draft.md#preservation-and-scope)).

- **`NewProvision` is rejected, not flattened.** It fails closed as
  `EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision` until it has a reviewed
  nested-hierarchy contract (`src/jlegal_okf/egov.py` `_ensure_supported_tree()`).
  The same fail-closed posture applies to any other structural element
  outside the reviewed set. Fixed by
  `tests/test_known_limitations.py` `test_new_provision_is_rejected_fail_closed()`.
  A `NewProvision` contains a second legal hierarchy for a material
  amendment. `_ensure_supported_tree()` runs, via `admit_egov_xml()`, over
  the *entire* `<Law>` element before any node is built, so a `NewProvision`
  anywhere in the document — even nested deep inside one amending
  supplementary provision, alongside an otherwise ordinary, fully supported
  `MainProvision` — aborts the whole conversion: `egov_xml_adapter()` raises
  before constructing a single `LegalNode`, not only for the amendment
  branch (verified: adding one `NewProvision` to an otherwise-valid law
  produced zero nodes, not a partial tree missing only that branch). **A
  law containing a `NewProvision` is therefore not partially supported; it
  is not processed at all.** The outer wrapper around it,
  `AmendProvisionSentence`, is read and preserved as source text on its
  own when no `NewProvision` sits inside it; it is the `NewProvision`
  itself, not the wrapper, that trips this all-or-nothing failure. **What
  fraction of all law is affected by this is not yet measured.** No count
  of how many laws, or what proportion of provisions, contain an
  unsupported `NewProvision` has been run against a corpus of real e-Gov
  law; that measurement still requires a future full-corpus survey. The offline
  inventory/survey tools in [measurement.md](measurement.md) now retain all
  inputs and failures for that work, but synthetic tests do not establish
  a real-law acceptance percentage or close the population-measurement task.
- **Appendix identity is source-tagged when the schema permits a number
  collision.** `AppdxTable` and `AppdxStyle` can both use the same `Num` under
  one `LawBody`; the adapter retains their common `appendix` node kind but
  includes each source XML tag in that appendix's canonical locator segment.
  This only disambiguates identity and does not infer that the appendices are
  equivalent. This is an unconditional rule applied to every `NodeKind.APPENDIX`
  node on every compile, not a conditional branch triggered only by a detected
  sibling collision; see rule `JLEGAL-NORM-5` in
  [`docs/normalization-rules.md`](normalization-rules.md#jlegal-norm-5-source-tagged-appendix-locator-identity)
  for the full definition, including its propagation to every numbered
  appendix's descendant `node_id`/`version_id`.
- **Admission (`jlegal validate-source`, and `compile --adapter egov_xml`
  internally) rejects, before conversion:** empty files, DTD/entity
  declarations (`EGOV_XML_DTD_OR_ENTITY_FORBIDDEN`), parse errors, API
  error responses, missing or conflicting official law IDs, and files over
  the 64 MiB admission cap (`EGOV_XML_INPUT_TOO_LARGE`) — see [profile
  §"Preservation and scope"](jlegal-okf-profile-0.3.0-draft.md#preservation-and-scope).
- **Empty structural nodes.** A structural node whose rendered text is
  empty (for example an empty appendix-table cell written as
  `<TableColumn/>`) has `text == ""`; the adapter no longer backfills it
  with that element's own XML serialization, and `LegalNode` accepts
  `text == ""` (the former `NODE_TEXT_EMPTY` invariant is now
  `NODE_IDENTIFIER_EMPTY` and no longer considers `text`, only
  `jurisdiction`/`authority`/`locator`). This also holds for a structural
  element with element children when every descendant renders to the empty
  string: no leaf beneath it holds any character, not even whitespace. A
  **leaf** element whose only content is XML formatting whitespace
  (for example the same cell written as `<TableColumn>` plus a newline and
  indentation) keeps that whitespace verbatim instead, and that whitespace
  propagates upward through every structural ancestor whose only content it
  is. `<TableColumn/>` (empty) and `<TableColumn> </TableColumn>` (one
  space) remain distinct XML infosets and therefore keep different
  `version_id`s — this is the source-fidelity behavior the profile keeps,
  not a defect; see [profile §"Preservation levels", "Character-level
  preservation"](jlegal-okf-profile-0.3.0-draft.md#preservation-levels)
  for the full description, both edge cases with examples, and the
  distinction between the conflation this profile revision removed and the
  source-fidelity behavior it does not change. Fixed by
  `tests/test_known_limitations.py` `test_empty_structural_node_keeps_empty_text()`.

- **Source-preserving only for legal relations.** Multiple effective dates in
  one supplementary-provision sentence, references, incorporation by
  reference, read-as clauses, and delegation clauses are retained as exact
  source text and carried into the projection and source concepts. v0.1 does
  not structure, resolve, or infer any relation or legal meaning from those
  sentences. In particular, multiple dates do not populate
  `Temporal.valid_from`/`valid_to`, and the reference, incorporation,
  read-as, and delegation sentences do not create graph edges or derived
  assertions.

## 2. Input parsing posture

Canonical text under profile 0.3.0-draft is character data, including Ruby/Rt,
Sup/Sub, Line and accepted Style leaves. Inline boundaries and attributes remain
in the original XML and cannot be reconstructed from plain text alone. The
source concept has an exact stored-body grammar that preserves canonical CR and
CRLF, but this does not guarantee how a Markdown renderer displays it. Consumers
must treat source as text, without executing HTML or instructions.

Old profile/corpus/recipe tuples are rejected before reference replay. Preserve
their original artifacts and pinned historical environment for reproduction;
recompile original XML to obtain the new tuple. See the
[active version and display contract](jlegal-okf-profile-0.3.0-draft.md).

XML paths share the bounded reader/parser in `src/jlegal_okf/input_limits.py`
([`SECURITY.md`, "Known parser posture"](../SECURITY.md#known-parser-posture)):

- The `egov_xml` adapter, admission, sniffing, inventory identity and fetch
  parsing, plus the generic `xml` and `html` adapters, use
  `DefusedXMLParser` with DTDs, entities and external references forbidden.
  Generic refusals are `ADAPTER_XML_DTD_OR_ENTITY_FORBIDDEN` and
  `ADAPTER_HTML_DTD_OR_ENTITY_FORBIDDEN`; e-Gov admission keeps
  `EGOV_XML_DTD_OR_ENTITY_FORBIDDEN`. Generic XML syntax errors use
  `ADAPTER_XML_PARSE`; `html` still requires well-formed XHTML and uses
  `ADAPTER_HTML_XHTML_REQUIRED` for malformed or empty input. These utilities
  do not expand the profile's accepted source scope. Actual DTD refusals are
  covered by `test_generic_xml_and_html_reject_dtd_as_documented()` in
  `tests/test_known_limitations.py`.
- Local XML/XHTML must be a regular file (regular symlink targets are allowed).
  The reader checks the opened descriptor with `fstat` and reads at most
  64 MiB + 1 byte from that same descriptor, rejecting over 64 MiB. POSIX
  nonblocking open avoids waiting for a FIFO writer before rejecting the
  nonregular input. Generic diagnostics are `INPUT_UNAVAILABLE`,
  `INPUT_NOT_REGULAR`, and `INPUT_TOO_LARGE`; e-Gov keeps the corresponding
  `EGOV_XML_INPUT_*` codes and rejects empty input as `EGOV_XML_INPUT_EMPTY`.
  Generic empty input reaches the syntax-error diagnostic instead.
- The parser independently checks the 64 MiB byte cap. Maximum XML depth is
  128, counting the root as 1; maximum cumulative element count is 250,000.
  Both are checked before creating each element, and exact limits pass.
  Excesses raise `INPUT_XML_DEPTH_LIMIT` / `INPUT_XML_ELEMENT_LIMIT` through
  admission and generic adapters. These are implementation resource limits,
  not judgments of official e-Gov XML conformance. There is no CLI bypass.
  Internal helpers accept positive integer keyword limits; invalid limits
  are `INPUT_LIMIT_VALUE`.
- Inventory preserves every input in its denominator: oversized identities
  remain `INPUT_TOO_LARGE`, excessive depth/elements use the two corresponding
  limit codes, and empty XML remains `INVALID_XML`. Survey exposes only the
  allowlisted diagnostic codes, without arbitrary exception details.
- **The 64 MiB cap already covers `jlegal fetch`.** Its HTTP streaming loop
  caps accumulated decoded response bytes before XML parsing or writing,
  rejecting excess as `EGOV_FETCH_TOO_LARGE`. `Content-Length` permits early
  rejection only. The shared parser then applies the tree limits; XML refusal
  on a successful HTTP response keeps `EGOV_FETCH_XML`. For an HTTP error,
  an unparseable or over-limit error body leaves the existing HTTP-status
  diagnostic without an extracted API code. HTTP decompression and individual
  chunk allocation occur before the accumulated-byte check; the cap is not a
  decompression-bomb or hard process memory guarantee.
- **Structured compile input:** source JSON has a 64 MiB byte cap, container
  depth 128 and 250,000 structural tokens. Mapping YAML/JSON and acquisition/
  rights JSON have 1 MiB input and canonical UTF-8 byte caps, depth 32 and
  10,000 tokens. Container starts, object keys and scalars each count once;
  root container depth is 1, scalar depth 0. The caps are inclusive, including
  unused fields and duplicate-key occurrences. JSON preflight precedes the
  standard decoder, preserving last-key-wins and UTF-8/16/32 byte encodings.
  CLI option files remain UTF-8. YAML events are checked before SafeLoader
  constructs objects; all aliases are forbidden, even acyclic ones. Anchors
  without references remain accepted. Invalid syntax/encoding is reported
  without parser exception text; see [the security policy](../SECURITY.md#known-parser-posture)
  for diagnostics.
- **Option graphs:** public adapter and compile API entries validate exact
  dict/list/JSON scalar types, string keys, finite floats and integers up to
  4096 bits before comparison or canonical serialization. Cycles, custom
  types, nonfinite numbers and lone surrogates fail closed; shared references
  consume the budget at every occurrence. Source JSON integers share the bit
  cap, with a 1234-digit decimal precheck before integer construction. JSON
  `1e400` is rejected as nonfinite even in an unused field. Mapping-file hash
  rereads are bounded without changing recipe/provenance semantics.
- **Remaining resource limits:** these checks do not impose hard process
  CPU, address-space or wall-clock limits, isolate conversion, or make all
  output publication transactional. Compilation and OKF export have the
  bounded publication checks in section 5 below. Parser/encoder temporary allocations and
  memory already held by an API caller are not hard-limited. Artifact readers
  in general and downstream legacy/evaluation inputs are outside this scope.
  Small synthetic cases in `tests/test_input_limits.py` and
  `tests/test_structured_input_limits.py` verify implemented boundaries;
  they are not a hostile-load endurance claim.

## 3. Acquisition provenance

- **An acquisition receipt's `rights` field is always null.** A non-null
  value in a receipt is rejected: e-Gov API delivery is not itself a rights
  assertion ([profile §"Provenance, normalization, and validation
  policy"](jlegal-okf-profile-0.3.0-draft.md#provenance-normalization-and-validation-policy)).
  Fixed by
  `tests/test_known_limitations.py` `test_acquisition_receipt_rights_is_always_null_and_non_null_is_rejected()`.
- **A recorded rights area is a claim, not a verified fact.** The separate,
  optional rights area ([profile §"Rights
  metadata"](jlegal-okf-profile-0.3.0-draft.md#rights-metadata)) is written
  only from an explicit caller assertion and is never inferred. Its four
  values are opaque: a licence identifier is not resolved, the two booleans
  are not derived from it, and neither is checked against the source. A
  compilation that asserts nothing records no rights area at all, which is
  what this repository's own README examples and fixtures do.
- **The rights area covers licensing and permission only.** Access control
  and usage-scope descriptions are out of scope for v0.1, as is any rights
  area on the legacy `jori-manifest/v3` generic-adapter manifest
  (`RIGHTS_PROFILE_REQUIRED`).
- **Retrieval time is recorded only when the acquisition process itself
  supplied it**, never inferred from a file's mtime or from bundle
  generation time. A saved XML file compiled without a receipt keeps
  `source_url` and `retrieved_at` as `null`.
- **Source identity is content-addressed, never a path.** Every
  `LegalNode.source` and manifest `inputs` entry carries a
  `jlegal:source:sha256:<hex>` URI, never a local file path — compiling
  identical bytes from two different directories reaches byte-identical
  output. Because the URI cannot be resolved back to a path, replay and
  export require the caller to pass the source file explicitly:
  `jlegal validate --verify-inputs` fails closed with
  `MANIFEST_REPLAY_SOURCE_REQUIRED` (or `..._MISMATCH` on a hash
  disagreement) and `jlegal export-okf` fails closed with
  `JLEGAL_OKF_SOURCE_REQUIRED` (or `..._MISMATCH`) if `--source` is
  omitted or wrong.
- **Known limitation — the multi-source ledger is unused.** The bundle
  format still defines a `references/source-reference.json` hash ledger
  for a genuinely multi-source corpus, but no adapter in this profile
  currently produces one; every corpus this reference implementation
  builds is single-source, and `validate-okf --verify-source` only
  supports that single-source `references/source.xml` embed path — it
  fails closed with `JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED` rather than
  silently skipping the check if a bundle used the ledger instead.
- `jlegal validate-source --report` produces an observation
  (`jlegal-egov-admission/v1`), not an authority `compile` trusts instead
  of rechecking the XML itself.

## 4. Temporal relations

- **Known limitation — the `egov_xml` adapter populates only
  `Temporal.promulgated`.** Every node from a single `egov_xml` compile is
  built with `Temporal(promulgated=...)` only
  (`src/jlegal_okf/egov.py` `egov_xml_adapter()`, the adapter's only `Temporal(...)`
  construction site); `valid_from`, `valid_to`, and `repealed` are always
  `null` for the `egov_xml` adapter's output specifically. Entry into
  force, amendment periods, and repeal are not derived from e-Gov source
  XML by any v0.1 adapter. This is narrower than "no adapter ever
  populates these fields": the generic `json`/`xml`/`html` adapters do
  read and set all four `Temporal` fields (`_temporal()` in, and the
  `valid_from`/`valid_to`/`promulgated`/`repealed` mapping keys consumed
  by, `src/jlegal_okf/adapters.py`) whenever the caller's input data or
  field mapping supplies them directly — that is a caller-supplied value,
  not something the adapter derives from a legal-document source the way
  `egov_xml`'s `promulgated` is.
- **The evidence grade behind a node's `Temporal` is discoverable from
  `LegalNode.source.adapter`.** `"egov_xml"` means every populated
  `Temporal` field on that node was derived from the e-Gov source XML
  itself, as described above; any other adapter name means the caller
  supplied the value directly, and it is an unverified claim, not a
  derivation. `export-okf`
  (`src/jlegal_okf/legal_okf.py` `_require_egov_profile_corpus()`) rejects, before export, any corpus
  whose manifest `adapter` is not `"egov_xml"` or whose nodes carry any
  other `source.adapter` — so a caller-supplied Temporal claim from a
  generic adapter never reaches a public OKF bundle; only the
  source-derived, `egov_xml`-only guarantee above does. This is an
  existing guarantee of the implementation, not new in this revision.
  Fixed by
  `tests/test_known_limitations.py` `test_egov_xml_nodes_only_populate_promulgated_and_export_okf_rejects_generic_adapter_corpus()`.
- **Promulgation date derivation is deliberately conservative.** The API
  envelope's `law_info/promulgation_date`, when present, takes precedence.
  For bare `<Law>` XML, a date is derived only from a complete
  Era/Year/PromulgateMonth/PromulgateDay tuple whose era is one of the
  five known public eras and whose resulting Gregorian date falls inside
  that era's known-unambiguous range; early-Meiji dates stay `null` by
  design, because Japan had not yet adopted Gregorian dating and a simple
  offset would assert a date the source does not actually support
  (`_ERA_DATE_RANGES`, `_bare_promulgated` in `src/jlegal_okf/egov.py`). A
  bare-XML date that disagrees with the envelope date fails closed as
  `EGOV_XML_PROMULGATION_CONFLICT` rather than picking one silently.
- **`TEMPORAL_OVERLAP` and `SEMANTIC_IDENTITY_DRIFT` are dormant for a
  single-snapshot compile.** `validate_corpus()` enforces `TEMPORAL_OVERLAP`
  (no two versions of the same node overlap in validity) and
  `SEMANTIC_IDENTITY_DRIFT` (a `node_id` never silently changes what it
  structurally identifies across versions) — see
  [`docs/validator-layers.md`](validator-layers.md) for the full
  code-to-layer map. Both compare multiple versions of the same
  `node_id` against each other, so on the output of any single adapter
  run — which never emits two versions of one node — they hold
  vacuously; they only become meaningful once a caller assembles a corpus
  spanning multiple versions of the same node, a workflow no current
  adapter or CLI command performs on its own.
- **`PARENT_TEMPORAL` is not dormant.** Unlike the two checks above,
  `PARENT_TEMPORAL` compares a child node's validity window against its
  *parent's* validity window, not against another version of itself, so
  it is fully active on an ordinary single-snapshot corpus: a child whose
  `Temporal` window is not contained within its parent's fails this check
  even when the corpus has exactly one version of every node (verified
  against a synthetic single-version parent/child pair with mismatched
  validity windows, compiled through the `json` adapter). All three
  claims in this and the preceding bullet are fixed by
  `tests/test_known_limitations.py` `test_temporal_overlap_and_semantic_identity_drift_are_vacuous_and_parent_temporal_is_active()`.
- `Temporal.__post_init__` rejects a node whose `valid_from` is not
  strictly before its `valid_to` when both are given
  (`src/jlegal_okf/model.py`); a single-instant or inverted validity
  window is refused at construction time, not caught later by
  `validate_corpus()`.

## 5. Output publication and interruption

Compilation retains the expected bytes of its four canonical products and,
after writing, checks the stage contains exactly those four names, each a
regular file without symlinks. Missing, extra or nonregular entries fail as
`STAGED_OUTPUT_FILE_SET`; changed bytes fail as `STAGED_OUTPUT_MISMATCH`.
`verify_canonical_artifacts` and `validate_corpus` then check disk content.
The trusted adaptation's adapter selects manifest validation: the supported
public adapters pass `verify_manifest`, while custom adaptations receive the
common checks without public-profile manifest validation
(`src/jlegal_okf/pipeline.py`, `_verify_staged_compilation`).

OKF export validates the completed stage with the existing
`validate_okf(stage, verify_source=False)` before publication, preserving its
existing diagnostics and validation scope. In particular, this does not add
compilation's stricter filesystem checks to the bundle validator. Ordinary
validation checks consistency and source-concept fidelity; it does not prove
the corpus was derived by re-compiling the embedded XML. That requires the
explicit `verify_source=True` mode
(`src/jlegal_okf/legal_okf.py`, `export_okf`, `validate_okf`).

Both producers attempt to remove only their own stage on `BaseException`,
including write/validation/rename failures, `KeyboardInterrupt` and `SystemExit`,
and re-raise the original exception. Existing outputs are refused before stage
creation; an existing file or nonempty directory causing final rename to fail
is left intact. Final directory rename is the commit point. Interruption after
that point preserves the complete validated final directory, so a missing API
success response does not imply the output is absent. Small fault-injection
tests exercise these paths in `tests/test_staged_output.py`.

These are bounded cleanup and consistency checks, not crash-durability or
hostile-filesystem guarantees. OS deletion denial, repeated interrupts,
`SIGKILL` and power loss can leave a stage. Concurrent creation of an empty
destination directory can still be overwritten by the replacement rename.
Concurrent no-replace publication and hard CPU/memory/time limits remain
separate work; see the [security policy](../SECURITY.md#output-publication-and-interruption).

## Scope: LLM audition is not part of v0.1

LLM execution, audition, enrichment, and provider integration are excluded
from this initial public-core slice
([profile §"Exclusions"](jlegal-okf-profile-0.3.0-draft.md#exclusions);
[`README.md`](../README.md)). To state this explicitly: LLM audition is
maintained as an independent responsibility of a Private overlay, and it is
not included in v0.1's required public-core implementation. A Private
overlay may consume this core's canonical and derived-knowledge boundary,
but this repository does not ship, require, or validate an LLM audition
step as part of v0.1.
