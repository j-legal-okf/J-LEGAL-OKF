# Known Limitations and Fail-Closed Behavior

## Status and scope

This document collects, in one place, the known limitations and fail-closed
behaviors that were previously scattered across
[`README.md`](../README.md), [`SECURITY.md`](../SECURITY.md), and
[`docs/jlegal-okf-profile-0.1.0-draft.md`](jlegal-okf-profile-0.1.0-draft.md).
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
([profile §"Preservation and scope"](jlegal-okf-profile-0.1.0-draft.md#preservation-and-scope)).

- **`NewProvision` is rejected, not flattened.** It fails closed as
  `EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision` until it has a reviewed
  nested-hierarchy contract (`src/jlegal_okf/egov.py`, `_ensure_supported_tree`).
  The same fail-closed posture applies to any other structural element
  outside the reviewed set.
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
  §"Preservation and scope"](jlegal-okf-profile-0.1.0-draft.md#preservation-and-scope).
- **Known limitation — empty structural nodes.** A structural node with no
  character data of its own (for example an empty appendix-table cell
  written as `<TableColumn/>`) currently carries that element's own XML
  serialization as `text` instead of an empty string, because the
  canonical model's non-empty-text invariant (`NODE_TEXT_EMPTY` in
  `model.py`) rejects `text == ""`. The equivalent cell written as
  `<TableColumn>` plus whitespace does not hit this substitution and keeps
  the whitespace instead, so the two spellings disagree and produce
  different `version_id`s. This is a known source/canonical conflation,
  retained for compatibility with the non-empty-text invariant rather than
  resolved; see [profile §"Preservation levels", "Known
  limitation"](jlegal-okf-profile-0.1.0-draft.md#preservation-levels) for
  the full description and the two other whitespace-elision edge cases
  documented alongside it (`TableHeaderColumn`'s always-preserved
  whitespace, and content-free elements with element children).

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

XML parsing takes two different paths with two different hardening
postures ([`SECURITY.md`, "Known parser
posture"](../SECURITY.md#known-parser-posture)):

- The `egov_xml` adapter, `jlegal validate-source`, `compile --adapter
  egov_xml`, and `jlegal fetch` — the only profile-accepted input path —
  parse with `defusedxml`, rejecting DTDs, entity declarations, and
  external references, which blocks entity-expansion bombs and XXE. These
  flags do not bound memory or CPU consumption from a large but
  well-formed document, and give no decompression-bomb protection.
- **The 64 MiB admission cap also covers `jlegal fetch`.** The saved-file
  path enforces the cap with `_read_admissible_xml`; `fetch_egov_xml`
  enforces the same `MAX_EGOV_XML_BYTES` cap independently, by reading the
  HTTP response body incrementally and aborting as soon as the accumulated
  byte count exceeds it, before the full body is ever materialized in
  memory and before anything is written to disk. Exceeding the cap fails
  closed with `EGOV_FETCH_TOO_LARGE`; no output file or acquisition receipt
  is created. A server-supplied `Content-Length` over the cap is used only
  as an early-exit optimization — correctness never depends on it, since
  the header is absent for chunked responses and is a self-declared value
  from an untrusted peer.
- The generic `xml` and `html` adapters (`src/jlegal_okf/adapters.py`)
  parse with the standard library's `xml.etree.ElementTree`, which is
  **not** hardened against entity-expansion or quadratic-blowup
  denial-of-service input. They are implementation utilities and do not
  expand v0.1's accepted source scope beyond e-Gov national-law XML
  ([`README.md`](../README.md)); treat XML fed to them as trusted input.

## 3. Acquisition provenance

- **An acquisition receipt's `rights` field is always null.** A non-null
  value in a receipt is rejected: e-Gov API delivery is not itself a rights
  assertion ([profile §"Provenance, normalization, and validation
  policy"](jlegal-okf-profile-0.1.0-draft.md#provenance-normalization-and-validation-policy)).
- **A recorded rights area is a claim, not a verified fact.** The separate,
  optional rights area ([profile §"Rights
  metadata"](jlegal-okf-profile-0.1.0-draft.md#rights-metadata)) is written
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
  validity windows, compiled through the `json` adapter).
- `Temporal.__post_init__` rejects a node whose `valid_from` is not
  strictly before its `valid_to` when both are given
  (`src/jlegal_okf/model.py`); a single-instant or inverted validity
  window is refused at construction time, not caught later by
  `validate_corpus()`.

## Scope: LLM audition is not part of v0.1

LLM execution, audition, enrichment, and provider integration are excluded
from this initial public-core slice
([profile §"Exclusions"](jlegal-okf-profile-0.1.0-draft.md#exclusions);
[`README.md`](../README.md)). To state this explicitly: LLM audition is
maintained as an independent responsibility of a Private overlay, and it is
not included in v0.1's required public-core implementation. A Private
overlay may consume this core's canonical and derived-knowledge boundary,
but this repository does not ship, require, or validate an LLM audition
step as part of v0.1.
