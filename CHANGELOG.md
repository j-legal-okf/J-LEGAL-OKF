# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for released tags.

## [Unreleased]

Nothing has been tagged or released yet.

### Added

- `tools/check_boundary.py`, a CI check that scans the tracked tree for
  private path markers, local absolute paths, credential patterns, and e-mail
  addresses other than the project's own. It complements
  `tools/verify_distribution.py`, which reads built artifacts: until now
  nothing ran automatically against the repository tree itself. It fails
  closed on an unreadable baseline or an undecodable text file. Its built-in
  patterns deliberately name nothing outside this project — a name that is
  private is itself private information — so such patterns are supplied with
  `--extra-patterns FILE` from wherever that knowledge already lives, and a
  malformed, missing, or empty file is an error rather than a quiet reduction
  in coverage. Only the test is exempt from the content scan, because it
  plants a violation for every rule; a test asserts that the checker's own
  sources need no exemption, and the exemption is printed on every run.
- `tools/check_dco.py`, a CI check that requires a `Signed-off-by` trailer
  matching the author or committer on every non-merge commit a pull request
  proposes. `CONTRIBUTING.md` and `GOVERNANCE.md` already required the DCO;
  nothing enforced it. The check runs over the pull request's `base..head`
  range, so this repository's own first two commits — which carry no sign-off
  and cannot be rewritten without discarding the audited single-commit
  history — are out of range by design rather than by exemption. The commit
  that added this check is the second of those two.
- The canonical `jori-corpus/v1` model, with deterministic corpus, node, and
  hash identifiers.
- `jori-manifest/v5`, with hash-covered `acquisition` and static `conversion`
  records, plus a `converted_at` conversion-history timestamp in the same
  canonical UTC `Z`-suffixed form as `acquisition.retrieved_at`.
  `converted_at` is deliberately excluded from `build_options_sha256` (it is
  set directly on the assembled manifest, never passed into the function
  that builds that hash's input), so compiling the same source bytes at two
  different wall-clock times still reaches byte-identical `corpus_sha256`,
  `crosswalk_sha256`, `projection_sha256`, and `build_options_sha256`; only
  `converted_at`, and therefore `manifest.json`'s raw bytes, may differ. The
  same three records (`acquisition`, `conversion`, `converted_at`) are
  copied to the `jlegal` extension in source and derived bundle frontmatter
  as sibling keys and checked by bundle validation. **Breaking**: renamed
  from `jori-manifest/v4`; nothing has been tagged or released, so there is
  no migration path to document.
- An optional rights area recording `source_license`, `bundle_license`,
  `redistribution_allowed`, and `commercial_use_allowed`, written only from
  an explicit caller assertion (`jlegal compile --rights <file.json>`, or
  `rights=` on `compile_corpus`/`compile_adaptation`) and never inferred from
  the source, the API response, or the adapter. An assertion changes the
  manifest schema to `jori-manifest/v6` (v5 plus `rights`) and an exported
  bundle to `jlegal-okf-bundle/v2` (v1 plus `rights`); **a compilation that
  asserts nothing keeps producing v5 and v1 byte for byte**, so digests
  recorded before this area existed remain reproducible. Malformed
  assertions fail closed (`RIGHTS_SHAPE`, `RIGHTS_VALUES`, `RIGHTS_EMPTY`),
  as does asserting rights for a generic `json`/`xml`/`html` compilation
  (`RIGHTS_PROFILE_REQUIRED`). An asserted area is part of
  `build_options_sha256`, and `validate_okf` requires a bundle's area to
  match its canonical manifest's in both directions
  (`JLEGAL_OKF_RIGHTS_MISMATCH`). The recorded values are opaque labels: no
  licence identifier is resolved, and no permission is derived from one.
- `jlegal validate-okf --verify-source` and `validate_okf(bundle,
  verify_source=True)`, an optional standalone re-verification on top of
  the default hash-agreement check: it re-converts a bundle's embedded
  `references/source.xml` with the declared adapter and build recipe
  (reusing `verify_manifest(..., verify_inputs=True)`) and byte-compares the
  result against `canonical/corpus.jsonl`, `crosswalk.jsonl`, and
  `projection.jsonl`. The default `validate_okf` only confirms that a
  bundle's declared hashes agree with each other and with its own files; it
  does not prove the canonical corpus was actually produced by converting
  the embedded source. Only the single-source `references/source.xml` embed
  path supports this; a bundle using the multi-source
  `source-reference.json` ledger (which no adapter in this profile
  currently produces) fails closed with
  `JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED` rather than silently skipping the
  check. The result dict gains a `source_reverified` key reflecting whether
  this check ran.
- `compile_adaptation`/`compile_corpus` now reject a malformed explicit
  `converted_at` (any value that does not round-trip through
  `_canonical_utc_timestamp`, including a non-`Z`-suffixed ISO string or a
  non-string) at compile time, with `ACQUISITION_CONVERTED_AT`, before any
  artifact is staged to disk — matching how `acquisition` is already
  validated by `_egov_acquisition` at the same point. Previously an invalid
  `converted_at` was written straight into `manifest.json` and only
  surfaced later, as `MANIFEST_ACQUISITION`, the next time that manifest was
  verified. `converted_at=None` (the default, meaning "generate now") is
  unaffected and still succeeds.
- Stable, aggregate validator diagnostics for identity, hierarchy, ordering,
  parent relations, temporal overlap, and crosswalk integrity. The profile's
  four-layer map (syntax, structure, source fidelity, semantic and temporal
  relations) organizes these codes as policy; diagnostics do not yet carry a
  machine-readable layer, and layer coverage is not complete. Source-byte
  fidelity is checked separately by `validate --verify-inputs` and
  `validate-okf`.
- Generic JSON, XML, and XHTML adapters. The `xml` and `html` adapters are
  mapping-driven and require a mapping; the `json` adapter reads a structured
  node tree directly and rejects a mapping.
- Saved e-Gov national-law XML conversion via the `egov_xml` adapter.
- `jlegal validate-source`, an optional pre-compilation e-Gov XML admission
  gate. It writes a deterministic `jlegal-egov-admission/v1` report when
  requested and validates receipt provenance with the same contract used by
  compile. The `egov_xml` adapter always runs the shared admission function,
  which rejects non-regular, empty, oversized (over 64 MiB), DTD/entity,
  malformed, API-error, ambiguous-ID, missing-body, unsupported, and
  structurally empty inputs before compilation creates an output directory.
- An explicit `fetch` helper that writes a `jlegal-egov-acquisition/v1`
  receipt.
- Deterministic export of a verified e-Gov corpus into an OKF v0.2-shaped
  bundle (`jlegal-okf-bundle/v1`), plus an offline validator for that bundle.
  The validator checks this project's bundle shape, canonical links, and
  hashes; it is not a conformance test against the Open Knowledge Format v0.2
  specification.
- The `jlegal` CLI, with subcommands `validate-source`, `compile`, `validate`,
  `fetch`, `export-okf`, and `validate-okf`.
- Offline synthetic e-Gov fixtures, including
  `examples/synthetic_egov_law.xml`, with regression tests that compile,
  validate, export, and validate them without a network request.
- An entirely invented structure-matrix fixture at
  `examples/fixtures/synthetic_egov_structure_matrix.xml` and its fixed
  `jlegal-synthetic-golden/v1` regression data, validated against the current
  official e-Gov XML Schema and covering source-preserving structural cases
  such as gaps, deletion markers, branches, appendices, tables, supplementary
  provisions, and amendment provisions. Appendix identity retains the source
  XML tag when schema-valid appendices share a number under one parent (rule
  `JLEGAL-NORM-5`, `docs/normalization-rules.md`).
- Content-addressed `source.uri` (`jlegal:source:sha256:<hex>`) in place of a
  local `file://` path, so compiling the same bytes with the same
  `corpus_id` from two different directories reaches byte-identical
  `corpus.jsonl`, `crosswalk.jsonl`, `projection.jsonl`, and `manifest.json`.
  This requires the same explicit `corpus_id`: `jlegal compile` without
  `--corpus-id` still defaults it to the input file's stem (`cli.py`), which
  is chosen by the caller and is not part of `source.uri`; two different
  file names still produce two different `manifest.json` files even for
  identical bytes. **Breaking**: every identifier
  derived from `source.uri` changes, including `version_id`, `corpus_sha256`,
  `projection_sha256`, `build_options_sha256`, and
  `attributes.build_provenance_sha256`. Nothing has been tagged or released,
  so there is no migration path to document. `acquisition.source_url` is
  unaffected; it still carries the real e-Gov retrieval URL.
- `verify_manifest(..., source=...)` and `jlegal validate --source`, for
  replaying a manifest's declared recipe against an explicitly supplied file.
  `--verify-inputs` without `--source` fails closed with
  `MANIFEST_REPLAY_SOURCE_REQUIRED` rather than guessing a path from the
  (now logical) `source.uri` or searching the current directory. A supplied
  file that does not hash to the declared `source` input fails closed with
  `MANIFEST_REPLAY_SOURCE_MISMATCH`.
- `export_okf(..., source=...)` and `jlegal export-okf --source`, required
  for the single-source corpus every `egov_xml` compilation produces, so the
  bundle still embeds the immutable `references/source.xml` snapshot instead
  of only a hash pointer. `source.uri` cannot be resolved to a path, so
  export fails closed with `JLEGAL_OKF_SOURCE_REQUIRED` when `--source` is
  omitted, and with `JLEGAL_OKF_SOURCE_MISMATCH` when the supplied file does
  not hash to the corpus's declared source. The `source-reference.json` hash
  ledger is reserved for a genuinely multi-source corpus.
- `verify_manifest`'s input-syntax check now also rejects a `source`/mapping
  entry whose `sha256` field disagrees with the hex embedded in its own
  content-addressed `uri`, not just a malformed `uri`.
- `egov_xml_adapter`'s text rendering is now content-model aware
  (`_STRUCTURAL_TAGS` in `egov.py`) instead of blanket-stripping every node's
  text. Byte preservation (source layer) and character-level preservation
  (canonical layer, `LegalNode.text`) are now defined and verified as two
  separate contracts; see the profile's new "Preservation levels" section
  (rules `JLEGAL-BYTE-PRESERVE-1`, `JLEGAL-TEXT-PRESERVE-1`,
  `JLEGAL-DISPLAY-TRIM-1`). The "whitespace" a structural element's own
  formatting text/tail may now have elided is exactly XML 1.0's `S`
  production (space/tab/CR/LF), never Python's Unicode-aware `str.strip()`,
  so a leading/trailing full-width space (U+3000) or other Unicode space
  that is source text is never dropped by that elision, including between
  sibling elements such as two `<Sentence>` children of a
  `<ParagraphSentence>`. **Breaking**: `LegalNode.text` no longer drops a
  leading/trailing full-width space (U+3000) or other non-XML-whitespace
  character that was previously stripped from the outermost text of a node,
  and no longer carries XML pretty-printing indentation/newlines between
  child elements of a structural tag. Because `text` feeds `version_id`,
  every affected node's `version_id` changes. The structural-tag set
  excludes `TableHeaderColumn` (mixed content in the e-Gov schema, so its own
  text is character data) and includes the un-numbered `SubitemSentence` and
  `List`/`Sublist{1..10}`/`Sublist{1..10}Sentence` wrappers alongside their
  already-included numbered `Subitem{1..10}Sentence` counterparts, so
  identical content produces identical text regardless of which recognised
  spelling of the same element-only wrapper shape the source uses.
  `_plain_text` (used for `heading`, `label`, titles, the envelope `law_id`,
  `LawNum`/`source_metadata["law_number"]`, the envelope promulgation date,
  the API error code, and number parsing) keeps producing character data
  only, exactly as `element.itertext()` did before — an inline element such
  as Ruby still contributes only its own text there, never an XML snippet —
  now built on the same content-model-aware, XML-`S`-production-only
  formatting-whitespace elision as `LegalNode.text`, and would elide such
  indentation if a structural wrapper were ever used as a title/caption
  source, then trimmed as before. No `_plain_text` call site currently
  reaches that elision at its top level, and display and comparison field
  values are unchanged for every schema-shaped input. The empty-text fallback is unchanged: a structural node
  with no character data of its own still carries that element's own XML
  serialization as `text` rather than an empty string, because the model's
  existing non-empty-text invariant (`NODE_TEXT_EMPTY`) rejects `text == ""`;
  see the profile's "Known limitation" note in "Preservation levels" for why
  this source/canonical conflation is retained rather than resolved here, and
  for why a content-free node that was pretty-printed keeps its layout
  whitespace instead of reaching that fallback.
  Nothing has been tagged or released, so there is no migration path to
  document.
- `DIAGNOSTIC_LAYERS` in `validation.py`, mapping every one of
  `collect_diagnostics()`'s 36 diagnostic codes to one of the four validator
  layers (syntax, structure, source fidelity, semantic and temporal
  relations) already named in the profile's "Provenance, normalization, and
  validation policy" section. `Diagnostic.to_dict()` now includes a
  `"layer"` key alongside the existing `code`/`subject`/`detail` keys — an
  additive output-shape change, not a removal or rename of any existing
  key. See `docs/validator-layers.md` for the full code-to-layer map and
  the classification principle behind it.
- `jlegal validate --diagnostics-json`, printing the full diagnostic list
  (`code`, `subject`, `detail`, `layer`) as a JSON array on success or
  failure of `validate_corpus()`, exiting 2 if the array is non-empty. This
  covers only `validate_corpus()`'s diagnostics: a `verify_manifest()`
  failure (a tampered or inconsistent `corpus.jsonl`/`manifest.json`/
  `crosswalk.jsonl`) runs first and still raises a plain-text message on
  stderr, not a JSON array, regardless of this flag. Its exit code follows
  the CLI's general error mapping: manifest tamper/provenance failures
  (for example `MANIFEST_CORPUS_TAMPERED`) exit 3, while manifest
  schema/type failures (for example `MANIFEST_JSON`) exit 2. The
  default `jlegal validate` output (`{"valid": true, "nodes": N}` on
  success, a plain-text `ValidationError` message on stderr with exit code
  2 on failure) is unchanged when this flag is omitted.
- Continuous integration (`.github/workflows/ci.yml`), running on every push
  and pull request to `main`: a `tests` job across Python 3.10, 3.11, 3.12,
  and 3.13; a `cli-e2e` job that runs the README's offline synthetic example
  and then compiles the same fixture twice into separate directories and
  compares `corpus.jsonl`, `crosswalk.jsonl`, and `projection.jsonl` byte for
  byte; and a `package-distribution` job that builds the sdist and wheel and
  checks their contents against an allowlist derived from the Git-tracked
  public files (`tools/verify_distribution.py`).

### Known limitations

- This is a draft profile (`0.1.0-draft`), not a release.
- Input is limited to e-Gov national-law XML; nothing is inferred from a
  title or file name.
- `NewProvision` is rejected with
  `EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision` rather than flattened.
- A saved XML compiled without an acquisition receipt keeps `source_url` and
  `retrieved_at` null, and never infers them from a file timestamp.
- An acquisition receipt's `rights` field is always null; a non-null value in
  a receipt is rejected, because e-Gov API delivery is not a rights
  assertion. Licensing facts go in the separate, optional rights area
  instead, and what that area records is the caller's claim, not a fact this
  project verified.
- `jori-manifest/v3` is what `compile` writes for the generic `json`, `xml`,
  and `html` adapters. It carries no `acquisition`, `conversion`, or
  `converted_at` record and therefore cannot be exported as a v0.1 bundle;
  only an `egov_xml` compilation produces `jori-manifest/v5`, or
  `jori-manifest/v6` when it also asserts a rights area.
- `validate_okf`'s default (no `verify_source`) check only confirms a
  bundle's declared hashes agree with each other and with its own files. It
  does not, by itself, prove the canonical corpus was actually produced by
  converting the embedded `references/source.xml`; that requires the
  optional `verify_source=True` / `--verify-source` re-derivation.
- The four validator layers are a policy map. There is no cross-reference
  resolution between provisions.
- `--verify-inputs` no longer re-reads an external `xml`/`html` mapping file's
  bytes from disk. The mapping that replay actually re-executes is always the
  normalized mapping already embedded in the manifest's
  `build_recipe.mapping`, which `build_options_sha256` covers; editing the
  external mapping file on disk after `compile` is not detected. The
  `sha256` recorded for a `mapping`-role entry in `inputs[]` is the original
  file's bytes hash at compile time; it cannot be re-checked from the
  manifest alone, since `source.uri`/mapping `uri` are logical identifiers,
  not resolvable paths.
- `jlegal compile` without `--corpus-id` (and without `--law-id`) defaults
  `corpus_id` to the input file's stem (`Path(input_path).stem`, `cli.py`).
  `corpus_id` is part of `manifest.json`, so compiling identical bytes under
  two different file names still produces two different `manifest.json`
  files; path-independence applies to identical bytes compiled under the
  same explicit `corpus_id`, not to the file name.
- `verify_manifest`'s `MANIFEST_INPUT_URI_CONFLICT` check is unreachable for
  any manifest that already passes input-role uniqueness and the
  uri-embedded-hex/`sha256` consistency check added above: those two
  invariants already guarantee that two `inputs[]` entries can share a `uri`
  only if their `sha256` also agrees. The check is kept as a second,
  currently-redundant line of defense rather than removed.
- A structural `egov_xml` node with no character data of its own (for
  example, an empty appendix-table cell written as `<TableColumn/>`) carries
  that element's own XML serialization as `text` rather than an empty
  string, because the canonical model's non-empty-text invariant
  (`NODE_TEXT_EMPTY`) rejects `text == ""`. This is a known source/canonical
  conflation; resolving it — for example, by relaxing that invariant or
  introducing an explicit null/empty representation — requires a separate
  reviewed change. The substitution is keyed on the rendered text being
  empty, so the same empty cell written across two lines renders as its
  indentation, keeps that whitespace, and never reaches the substitution;
  the two spellings therefore disagree and their `version_id`s differ.
  `TableHeaderColumn` text is layout-dependent for a related reason — it is
  excluded from the structural set so that mixed-content whitespace is never
  lost. More generally, whitespace inside any element outside that set is
  preserved verbatim, so re-indenting a source document can change a node's
  `version_id` even when the node carries character data.
- The synthetic fixture exercises only a small part of the reviewed
  hierarchy.
- The project excludes LLM execution, audition, enrichment, OCR, municipal
  ordinances, case law, and legal interpretation.

[Unreleased]: https://github.com/j-legal-okf/J-LEGAL-OKF/commits/main
