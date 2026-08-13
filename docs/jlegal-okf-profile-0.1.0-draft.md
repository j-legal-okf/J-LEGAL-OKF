# J-LEGAL-OKF Profile 0.1.0-draft

## Status and purpose

J-LEGAL-OKF is a draft public profile for reproducible, source-preserving
Japanese national-law knowledge bundles. It is not an official e-Gov, Japanese
Government, or Open Knowledge Format endorsement, and it does not determine the
legal meaning or correctness of a source.

JORI Engine is the profile's reference implementation. Its canonical internal
form remains `jori-corpus/v1`; official OKF v0.2 is an export projection, not a
replacement for canonical evidence.

This document is the normative v0.1 profile for the public core. Research
notes, review records, and Private overlays do not alter this contract.

## Normative and authoritative references

Format-dependent behavior in this profile follows these primary sources:

- [e-Gov 法令標準XMLスキーマ解説](https://laws.e-gov.go.jp/docs/law-data-basic/419a603-xml-schema-for-japanese-law/)
- [e-Gov Law API v2 Swagger UI](https://laws.e-gov.go.jp/api/2/swagger-ui/)
- [Open Knowledge Format v0.2 specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

They define the referenced XML, API, and OKF formats. They do not endorse
J-LEGAL-OKF itself, which remains this project's independent draft profile.

## v0.1 contract

### Preservation and scope

The following priorities apply in order: source fidelity, structural
preservation, source traceability, deterministic transformation, and separation
of derived knowledge. Readability or generated prose must not override them.

v0.1 is limited to Japanese national-law XML supplied by e-Gov. It does not
infer a national-law source from a title, filename, or a different input type.
Each accepted source has three distinct concerns:

- **source**: the received bytes/text and their provenance;
- **canonical**: the deterministic structural representation derived from that
  source; and
- **derived**: optional knowledge produced by rules or models, which is never
  source or canonical evidence.

The source text is immutable. A converter must retain meaningful hierarchy,
ordering, text, attributes, and branch numbering, and must stop with a stable
diagnostic when an unreviewed nontrivial structure would otherwise be guessed,
discarded, or flattened.

- Input is a saved e-Gov Law API v2 XML full-text response or bare native
  `<Law>` XML. A bare document with no official law ID must receive an explicit
  `--law-id`; titles and file names are never used to infer it.
- Before conversion, `jlegal validate-source` applies the same admission
  function that the `egov_xml` adapter uses. It accepts only a bounded (64 MiB)
  regular XML file with a single reviewed e-Gov `<Law>` or API v2
  `<law_data_response>` shape, a single `LawBody`, and one consistent official
  law ID. Empty files, DTD/entity declarations, parse errors, API error
  responses, missing or conflicting IDs, and unsupported/empty structures
  fail closed. `compile --adapter egov_xml` calls that function itself before
  it creates an output directory, so admission cannot be bypassed by omitting
  the standalone command.
- `validate-source --acquisition receipt.json` applies the same receipt
  contract as compile: source hash, e-Gov URL/query, official/requested ID,
  retrieval timestamp, `as_of`, and `rights: null` must agree. Its optional
  `--report` creates a deterministic `jlegal-egov-admission/v1` record and
  refuses to overwrite an existing report. The report is an observation, not
  an authority that compile trusts instead of rechecking the XML.
- The `egov_xml` adapter preserves the source XML hash, source key, original
  text, hierarchy, meaningful XML attributes, and branch article numbering.
  It fails with a stable diagnostic when nontrivial unsupported structure would
  otherwise be lost.
- The reviewed hierarchy includes Law, Preamble, MainProvision, Part, Chapter,
  Section, Subsection, Division, Article, Paragraph, Item, Subitem,
  supplementary provisions, amendment provisions with
  `AmendProvisionSentence`, appendices, tables, rows, and cells.
  `NewProvision` is intentionally rejected as
  `EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision` until it has a reviewed nested
  hierarchy contract; it is never silently flattened.
- `law_info/promulgation_date` from an API envelope is retained as
  `Temporal.promulgated` on the root and every source node. Bare `<Law>` XML
  uses only a complete, valid Era/Year/PromulgateMonth/PromulgateDay tuple from
  a known public era; incomplete or unknown attributes remain null, and a
  conflict with envelope metadata fails closed.
- `jlegal export-okf` produces an OKF v0.2-shaped bundle
  (`jlegal-okf-bundle/v1`, or `/v2` when the corpus asserts a rights area)
  with source, canonical structure, and
  AI-derived-knowledge boundary in separate paths. This project runs no
  conformance test against the Open Knowledge Format v0.2 specification. Its
  validator checks this project's bundle shape: identifiers, parent links,
  source and content hashes, provenance, and generated-bundle hashes. Export
  and validation accept only a verified `egov_xml` corpus with `egov_xml`
  source references.
- `jlegal validate-okf --verify-source` performs an optional, standalone
  re-verification on top of the default hash-agreement check: it re-converts
  the bundle's embedded `references/source.xml` with the declared adapter and
  build recipe (reusing `verify_manifest(..., verify_inputs=True)`) and
  byte-compares the result against `canonical/corpus.jsonl`,
  `crosswalk.jsonl`, and `projection.jsonl`. The default `validate-okf` (no
  flag) only confirms that a bundle's declared hashes agree with each
  other and with its own files; it does not prove the canonical corpus was
  actually produced by converting the embedded source. `--verify-source`
  only supports the single-source `references/source.xml` embed path — the
  only path any adapter in this profile currently produces — and fails
  closed with `JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED` rather than silently
  skipping the check if a bundle instead used the multi-source
  `source-reference.json` ledger.

### Preservation levels

Release-checklist item 8 separates two preservation contracts that earlier
drafts of this profile conflated. Each is defined and verified independently;
neither substitutes for the other.

#### Byte preservation (source layer) — rule `JLEGAL-BYTE-PRESERVE-1`

The received XML bytes are never altered. `source.sha256` is the SHA-256 of
exactly those bytes (`egov_xml_adapter` hashes `path.read_bytes()` with no
decoding or reformatting). `jlegal export-okf` embeds exactly those bytes as
`references/source.xml`, after checking the caller-supplied file's hash
against the corpus's declared `source` input and failing closed
(`JLEGAL_OKF_SOURCE_MISMATCH`) on disagreement. `jlegal validate-okf` checks
the embedded file the same way: a byte comparison against the declared hash,
never a re-rendering or re-serialization of the XML.

#### Character-level preservation (canonical layer, `LegalNode.text`) — rule `JLEGAL-TEXT-PRESERVE-1`

**Applicability**: every `LegalNode.text` produced by the `egov_xml` adapter.

**Rule**: text is rendered by walking the source element tree and
concatenating character data verbatim, with one narrowly scoped exception for
XML formatting whitespace. "Whitespace" here is exactly XML 1.0's `S`
production — space (`#x20`), tab (`#x9`), CR (`#xD`), LF (`#xA`) — never
Python's Unicode-aware definition, which would also treat U+3000 IDEOGRAPHIC
SPACE, U+00A0, and other Unicode spaces as whitespace even though they are
source character data. A fixed set of structural tags — element-only content
models: every canonical node tag except `TableHeaderColumn` (excluded because
it is mixed content in the e-Gov schema and may carry character data
directly), plus transparent containers such as `LawBody` and sentence/list
wrapper elements such as `ParagraphSentence`, `SubitemSentence`, and `List`
that may themselves group child elements — is enumerated in code as
`_STRUCTURAL_TAGS`. When an element whose local tag is in that set has at
least one child element, a text node directly inside it (`element.text`, or a
child's `tail`) that consists solely of XML `S`-production whitespace is XML
formatting and is not emitted. A text node containing any non-whitespace
character, or any Unicode whitespace outside the XML `S` production, is
always emitted verbatim, character for character, regardless of that
element's tag. A leaf element, or any element whose tag is outside the
structural set — including every `Sentence`, title, caption, label, and
`*Num` tag — has all of its text nodes emitted verbatim, unconditionally.
This rule never rewrites character data; it only omits the subset of XML
`S`-production whitespace that the content model guarantees is layout, not
source text.

**Known limitation**: a structural node with no character data of its own
(for example, an empty appendix-table cell written as `<TableColumn/>`)
currently carries that element's own XML serialization as `text` instead of
an empty string, because the canonical model's existing non-empty-text
invariant (`NODE_TEXT_EMPTY` in `model.py`) rejects a node with `text == ""`.
This is a known source/canonical conflation, retained here for compatibility
with that invariant rather than resolved by this revision; resolving it —
for example, by relaxing the invariant or introducing an explicit null/empty
representation — requires a separate reviewed change. This limitation is
also indexed in [`docs/known-limitations.md`, "Supported
structure"](known-limitations.md#1-supported-structure).

That substitution is keyed on the rendered text being the empty string, which
is narrower than "content-free". A leaf element has no children, so it is
never subject to formatting elision: the same empty cell written as
`<TableColumn>` plus a newline and indentation renders as that indentation,
which is not empty and therefore keeps the layout whitespace rather than
reaching the substitution. The two spellings therefore disagree with each
other, and their `version_id`s differ. A content-free element that does have
element children is layout-dependent inside the substitution branch as well,
because the element's own serialization re-emits the whitespace between them.

Excluding `TableHeaderColumn` from the structural set has the same shape of
cost: its whitespace may be character data in mixed content, so it is always
preserved, and a `TableHeaderColumn` node's `text` is therefore
layout-dependent as well. That is the deliberate conservative trade — no
character is ever lost — and `TableHeaderColumn` is the only canonical node
tag so excluded.

Formatting independence is a property of the elision rule, not of a node.
Whitespace between the child elements of a structural tag is dropped, so
re-indenting those text nodes does not change `text`. Whitespace that lands
inside any element outside the structural set — every `Sentence`, title,
caption, label, and `*Num` tag — is preserved verbatim and does change the
enclosing node's `text` and `version_id`, as do the content-free case and
`TableHeaderColumn` above. A node that carries character data is therefore
not guaranteed to be layout-stable; only the elided text nodes are.

**Examples**:

1. Full-width space preserved. Input `<ItemSentence>　全角空白で始まる号本文　</ItemSentence>`
   (leading and trailing U+3000 IDEOGRAPHIC SPACE). `ItemSentence` has no
   child elements here, so every text node is kept regardless of the
   structural set: `text == "　全角空白で始まる号本文　"`, both U+3000
   characters preserved, at the Item node and at every ancestor node whose
   rendered text includes it.
2. Indentation dropped. Pretty-printed input:

   ```xml
   <Article Num="1">
     <ArticleCaption>（目的）</ArticleCaption>
     <Paragraph Num="1">
       <ParagraphSentence>本文です。</ParagraphSentence>
     </Paragraph>
   </Article>
   ```

   `Article` and `Paragraph` are structural tags with child elements here, so
   the newline-and-indentation text nodes between `ArticleCaption`,
   `Paragraph`, and `ParagraphSentence` are formatting and are dropped;
   `ArticleCaption`'s and `ParagraphSentence`'s own content is not. The
   `Article` node's `text == "（目的）本文です。"` — identical to compiling
   the same content with no inter-element whitespace at all.

#### Trimmed comparison fields (`heading`, `label`, and other non-`text` consumers) — rule `JLEGAL-DISPLAY-TRIM-1`

**Applicability**: not only display fields. `_plain_text` is the shared
implementation behind `heading`, `label`, the titles used to build them, the
envelope `law_id`, and branch/ordinal number parsing (genuinely
display/comparison fields) — and also `LawNum`, which becomes
`source_metadata["law_number"]` and is recorded provenance checked against an
acquisition receipt, not a display field; the envelope's
`law_info/promulgation_date`, which becomes `Temporal.promulgated`; and the
e-Gov API's `error_info/code` on a failed fetch. **Never** `LegalNode.text`.

**Rule**: the same content-model-aware render (`JLEGAL-TEXT-PRESERVE-1`) is
computed first, but taking character data only — an inline element such as
Ruby contributes its own text, never an XML snippet, matching what
`element.itertext()` produced before this render was made content-model
aware. Leading and trailing whitespace is then trimmed with Python's ordinary
(Unicode-aware) `str.strip()`, which — unlike `JLEGAL-TEXT-PRESERVE-1`'s
internal formatting-whitespace elision — does trim a boundary full-width
space here, because these are structured comparison fields and recorded
provenance, not preserved source text; trimming here does not touch `text`.

**Example**: input `<ArticleCaption>　　padded　　</ArticleCaption>` produces
`heading == "padded"`. The identical padded text placed inside a
`<ParagraphSentence>` instead is not trimmed: `text == "　　padded　　"`. An
inline element inside a caption is also flattened to plain text here (never
XML markup): `<ArticleCaption>（<Ruby>目的<Rt>もくてき</Rt></Ruby>）</ArticleCaption>`
produces `heading == "（目的もくてき）"`.

`JLEGAL-BYTE-PRESERVE-1`, `JLEGAL-TEXT-PRESERVE-1`, and `JLEGAL-DISPLAY-TRIM-1`
are a distinct rule series from the future identifier-normalization rules
referenced in the next section; a normalization rule is never given a
`JLEGAL-BYTE-PRESERVE-*`, `JLEGAL-TEXT-PRESERVE-*`, or `JLEGAL-DISPLAY-TRIM-*`
ID, and these preservation rule IDs are never reused for identifier
normalization.

### Provenance, normalization, and validation policy

Acquisition provenance is input-derived evidence. A conforming workflow records
the supplied source authority, source URL when supplied, source format,
official identifiers, and source hash. It records a retrieval time only when
the acquisition process supplied it; it must not infer that value from a file
timestamp or bundle generation time.

`jlegal fetch --receipt-out` writes a separate, hash-bound
`jlegal-egov-acquisition/v1` receipt. It records the e-Gov authority, final
response URL, UTC retrieval time, XML format, requested law ID, `as_of`,
returned official law ID, law number when present, and XML SHA-256. `jlegal
compile --acquisition` accepts the receipt explicitly and rejects a mismatch
in its source hash, identifier, law number, format, URL, query parameters, or
retrieval time. A saved XML compiled without a receipt retains only XML facts;
its `source_url` and `retrieved_at` are null.

New e-Gov compilations use `jori-manifest/v5` — or `jori-manifest/v6` when a
rights area is asserted, see "Rights metadata" below — adding hash-covered
`acquisition` and static `conversion` records, plus a `converted_at`
conversion-history timestamp in the same canonical UTC `Z`-suffixed form as
`acquisition.retrieved_at`. The same three records are copied to the
`jlegal` extension in source and derived YAML frontmatter and checked by
bundle validation. `converted_at` is conversion history, not an input to any
deterministic identifier: it is deliberately excluded from
`build_options_sha256` (it is set directly on the assembled manifest, never
passed into the function that builds `build_options_sha256`'s input), so
compiling the same source bytes at two different wall-clock times still
reaches byte-identical `corpus_sha256`, `crosswalk_sha256`,
`projection_sha256`, and `build_options_sha256`; only `converted_at` itself,
and therefore `manifest.json`'s raw bytes, may differ. `jori-manifest/v3` is
what compilation produces for the generic JSON, XML, and HTML adapters; it
carries no `acquisition`, `conversion`, or `converted_at` record and cannot
be exported as a v0.1 J-LEGAL-OKF bundle for that reason. An acquisition
receipt's own `rights` field is always null: a non-null value in a receipt is
rejected, because e-Gov API delivery is not a rights assertion. Licensing
facts are recorded in the separate rights area below, from an explicit
assertion rather than from delivery.

Every `LegalNode.source` and manifest `inputs` entry carries a content-addressed
`uri` (`jlegal:source:sha256:<hex>`), never a local file path. Compiling the
same bytes with the same `corpus_id` from two different directories therefore
reaches byte-identical `corpus.jsonl`, `version_id`s, and manifest hashes; a
local absolute path is never part of a canonical identifier. `corpus_id`
itself is caller-chosen and, without an explicit `--corpus-id`, `jlegal
compile` defaults it to the input file's stem, so two different file names
still produce two different `manifest.json` files for identical bytes. This
path-independence is unrelated to `acquisition.source_url`, which is the
retrieval URL from the fetch receipt
and is never derived from `source.uri`. Because `source.uri` cannot be
resolved back to a path, `verify_manifest`/`jlegal validate --verify-inputs`
requires the caller to pass the file explicitly as `source`/`--source`; it
fails closed with `MANIFEST_REPLAY_SOURCE_REQUIRED` rather than guessing a
path or searching the current directory, and with
`MANIFEST_REPLAY_SOURCE_MISMATCH` if the supplied file's hash does not match
the declared `source` input. `jlegal export-okf` requires the same explicit
`--source` for a single-source corpus (every `egov_xml` compilation), so the
bundle embeds the immutable `references/source.xml` snapshot rather than only
a hash pointer; it fails closed with `JLEGAL_OKF_SOURCE_REQUIRED` when
`--source` is omitted and `JLEGAL_OKF_SOURCE_MISMATCH` on a hash disagreement.
The `references/source-reference.json` hash ledger remains for a genuinely
multi-source corpus, which no adapter in this profile currently produces.

Normalization never rewrites source text. It is limited to identifiers and
other explicitly designated canonical comparison fields, while the original
form remains available as source evidence. Five identifier/comparison-field
normalization rules are already implemented and already relied upon by every
compile — identifier normalization, kanji-numeral conversion, ordinal/branch
decomposition, locator-segment sanitization, and source-tagged appendix
locator identity — and are documented with stable rule IDs (`JLEGAL-NORM-1`
through `JLEGAL-NORM-5`), applicability, and verified input/output examples
in [`docs/normalization-rules.md`](normalization-rules.md). The fifth,
`JLEGAL-NORM-5`, is an unconditional rule keyed on `NodeKind.APPENDIX`: every
numbered appendix's locator always includes its own source XML tag, not only
when a sibling `Num` collision is present, and this propagates to the
`node_id`/`version_id` of every numbered appendix and its full descendant
subtree; see
[`docs/normalization-rules.md#jlegal-norm-5-source-tagged-appendix-locator-identity`](normalization-rules.md#jlegal-norm-5-source-tagged-appendix-locator-identity)
for the full definition. Any additional normalization rule beyond those five
must be documented the same way, with a stable rule ID, applicability, and
input/output examples, before it is relied upon by this profile. The
"Preservation levels" section above documents the
already-effective, separately-verified byte- and character-preservation
rules; the identifier-normalization rules are additional to that series,
never a replacement for it, and draw their rule IDs from a different series
(see that section's closing paragraph).

Validators are organized as four complementary layers:

1. syntax: file shapes, required fields, and types;
2. structure: identity, hierarchy, ordering, and parent relations;
3. source fidelity: source/content hashes and preservation against the source;
   and
4. semantic and temporal relations: references, derived/source separation, and
   reviewed time relations.

This organization is a policy map, not a replacement for existing diagnostic
codes. Existing UUID-based IDs, diagnostic codes, and their compatibility
contracts remain in force. The illustrative identifiers, diagnostic codes, and
bundle paths in a review document are not adopted by this profile.

The canonical model remains the authority for validation and export. Official
OKF v0.2 remains a projection; this profile does not adopt an alternative
bundle layout or wire format merely because it appears in an example.

### Rights metadata

A conforming workflow can record licensing facts about a compiled corpus and
about the bundle exported from it. The area is optional and is written only
when a caller asserts it (`jlegal compile --rights <file.json>`, or `rights=`
on `compile_corpus`/`compile_adaptation`). Nothing in the source bytes, the
API response, or the adapter can produce it.

```json
{
  "source_license": "Public Data License 1.0",
  "bundle_license": "Apache-2.0",
  "redistribution_allowed": true,
  "commercial_use_allowed": null
}
```

- Exactly those four keys must be present. An unknown key, a missing key, or a
  non-object value is rejected (`RIGHTS_SHAPE`).
- `source_license` and `bundle_license` are a non-empty string without NUL, or
  null. `redistribution_allowed` and `commercial_use_allowed` are `true`,
  `false`, or null; `0`/`1` and `"true"` are rejected (`RIGHTS_VALUES`).
- An assertion whose four fields are all null is rejected (`RIGHTS_EMPTY`).
  Absence of the area is the single representation of "no rights recorded".
- The four values are opaque labels. This profile stores and hashes them; it
  does not resolve a licence identifier, does not derive the two booleans from
  a licence, and does not check either against the source or against each
  other. A recorded value is the caller's claim, not a verified fact.
- The area is defined for this profile's manifest only. Asserting rights for a
  generic `json`/`xml`/`html` compilation is rejected
  (`RIGHTS_PROFILE_REQUIRED`); `jori-manifest/v3` is unchanged.
- Presence changes the manifest schema to `jori-manifest/v6` (v5 plus
  `rights`) and the exported bundle manifest to `jlegal-okf-bundle/v2` (v1
  plus `rights`). The key set of each schema is exact, so a v5 manifest
  carrying a rights area and a v6 manifest missing one are both rejected
  (`MANIFEST_KEYS`), as is a v2 bundle manifest whose area is malformed
  (`JLEGAL_OKF_MANIFEST_SHAPE`).
- **A compilation that asserts nothing keeps producing `jori-manifest/v5` and
  `jlegal-okf-bundle/v1` byte for byte**, so digests recorded before this area
  existed remain reproducible.
- Unlike `converted_at`, an asserted area is part of `build_options_sha256`:
  changing it changes that digest, and a manifest whose recorded area no
  longer matches its digest fails closed (`MANIFEST_OPTIONS_TAMPERED`).
  Compiling the same input twice with the same assertion reaches the same
  `build_options_sha256`, and — at a fixed `converted_at`, the one field that
  may differ between two compiles — a byte-identical `manifest.json`. The
  order in which a caller supplies the four keys does not affect either.
- An exported bundle carries over exactly what the canonical manifest asserts.
  `validate_okf` compares the two in both directions, so a bundle can neither
  invent an assertion its corpus does not make nor drop one it does
  (`JLEGAL_OKF_RIGHTS_MISMATCH`).
- Access control and usage-scope descriptions are out of scope for v0.1; this
  area holds licensing and permission facts only.

## Exclusions

This initial public-core slice excludes LLM execution, audition, enrichment,
provider integration, OCR, municipal ordinances, case law, legal interpretation
or advice, Akoma Ntoso output, index/search/evaluation, and benchmark corpora.
Future capabilities require a separately reviewed profile revision and must
not mutate source or canonical data. LLM execution and audition specifically
remain the independent responsibility of a Private overlay; they are not
part of v0.1's required public-core implementation. See
[`docs/known-limitations.md`](known-limitations.md) for this scope statement
alongside the profile's other known limitations and fail-closed behaviors.
