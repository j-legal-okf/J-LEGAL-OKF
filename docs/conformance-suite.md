# Fixed-case artifact conformance

The suite checks submitted files independently of the converter. It imports no
producer model, adapter, pipeline, or bundle validator and runs no submitted
program. The reviewed catalog is
[`examples/conformance/cases.json`](../examples/conformance/cases.json), with
normative anchors, levels, methods and case links in
[`requirements.json`](../examples/conformance/requirements.json).

Passing means that these fixed artifacts meet the listed checks. It does not
prove arbitrary-input conformance, attest which implementation produced them,
or prove that a rejection record came from executing a program. In particular,
identical files submitted for two runs demonstrate artifact equality, not two
independently witnessed executions. Producer execution belongs to a separately
recorded measurement workflow.

## Three separately reported layers

| Layer | What is checked | What a pass means |
| --- | --- | --- |
| `okf_format` | UTF-8 concepts, YAML frontmatter and nonempty string `type`; reserved index frontmatter placement and log date headings | Mechanical checks of the fixed official specification's format floor; no editorial or prose interpretation |
| `profile` | Fixed source bytes and explicit law key; every expected node, text, own XML attribute, parent, ordinal, branch, temporal field and UUID; projections, source concepts, build/source digests and cross-case relations | The listed fixed-case profile invariants hold |
| `jori_byte_regression` | Optional fixed reference hashes for all five normal cases under profile 0.3.0-draft | Exact compatibility with that JORI recipe; never required for another producer's common result |

The official source is [OKF v0.2 at commit
`ad30107c31c06aec8a7d5636e0d1058118604e6f`](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/ad30107c31c06aec8a7d5636e0d1058118604e6f/SPEC.md#11-conformance).
The checker accepts unknown types and extension keys, absent optional metadata,
bare `verified` mappings, missing indexes and broken links. It does not impose
JORI's generator name or title strings on this format layer. Optional metadata
recommendations, attested-computation execution, human review and legal meaning
are outside its claim. The specification digest is recorded in the requirements
catalog; the runner uses the reviewed local catalog and does not fetch it.

## Cases and immutable expectations

The seven required cases are:

1. `matrix`: the existing 16-feature structure matrix, copied byte-for-byte.
2. `edges`: preserved U+3000/U+00A0, repeated spaces and leaf newlines; empty
   Sentence/structural nodes; absent promulgation day means unknown dates.
3. `appendix-alone`: the same matrix with its `AppdxStyle` sibling removed.
4. `relocated`: the matrix recipe repeated under another input/output directory.
5. `different-time`: the matrix with a different fixed conversion timestamp.
6. `tampered-source`: a matrix bundle whose embedded source bytes are changed.
   The runner itself must detect the mismatch; a bare rejection claim is
   insufficient. Other profile failures still fail this case.
7. `new-provision`: a schema-valid but unsupported nested amendment, with a
   rejection record carrying `EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision`.

The matrix covers missing article numbers, deletion, branch numbering, implicit
first paragraphs, all three イ・ロ・ハ subitems, supplementary and amendment
provisions, appendices, table hierarchy, effective-date prose, transitional
measures, and reference/incorporation/read-as/delegation sentences.
Exact per-node values in `expected/*.json` are source-authored test material;
tests never generate or update them through a converter. UUID formulas are
reimplemented with standard-library hashing, normalization and UUID primitives.
Conversion metadata can name another implementation, but must remain internally
consistent with its manifest and source concepts. Build provenance is recomputed
from the submitted recipe and declared inputs, not forced to a JORI digest.
All catalog recipes assert no rights area, so their wire contracts are
`jori-manifest/v5`, `jlegal-okf-bundle/v1` and `jori-projection/v1`.
Rights-bearing v6/v2 cases require a separately reviewed recipe; changing only
a schema name cannot pass these no-rights cases.

The active [0.3.0-draft profile](jlegal-okf-profile-0.3.0-draft.md) requires
`jori-corpus/v3` and e-Gov adapter version string `"2"`. `NODE_SCHEMA` and
`ADAPTER_METADATA` reject old, unknown or malformed values; non-string adapter
versions additionally fail `MANIFEST_TYPES`. Converter name/version remain
producer-independent, with the supported profile required by
`CONVERTER_METADATA` and concept provenance checked by `CONCEPT_PROVENANCE`.

Every source concept must match the complete `DB-DISPLAY-1` construction,
including its canonical heading/label/locator title, markers and final LF.
`SOURCE_DISPLAY_CONTRACT` rejects commentary, markerless bodies, title or
payload changes and missing framing. Marker-like characters inside the known
payload are retained. `CONCEPT_TEXT` separately checks the content hash.
The parser preserves CR/CRLF inside the body; after the frontmatter delimiter
it excludes at most one optional LF or CRLF blank separator line. A second
blank line is part of the body and fails the grammar. Canonical node text is
always checked exactly against the immutable expected records.

Own XML attributes are required. The fixed expectations separately enumerate
optional copies of source-descendant `Delete` and `AmendLawNum` flags on
ancestors; these copies are not required, and unrelated attributes are rejected.
The normative profile requires preservation of meaningful attributes, but does
not require those flags to be duplicated on every ancestor. This allowance
does not relax any own-attribute, child-node, text, or identity assertion.

The full official [e-Gov v3 XSD](https://laws.e-gov.go.jp/file/XMLSchemaForJapaneseLaw_v3.xsd)
validated all four XML inputs on 2026-09-19. The complete XSD has no imports or
includes; its SHA-256 is
`f5e11ddb0d91c26232d6eb49a59001c3f5d418ef34fd2aef3b59223a6f633276`.
The schema is not distributed. All inputs are entirely invented, not legal
sources. An empty table cell uses a schema-valid empty `Sentence` child.

### Historical reference discrepancy and coordinated correction

Under profile 0.2.0-draft, the reference converter preserved a `Style` leaf as literal
`<Style>…</Style>` inside the appendix and root canonical text. The profile's
`JLEGAL-TEXT-PRESERVE-1` character-data rule does not specify this exception.
Accordingly, that unmodified reference submission reported `NODE_TEXT` for
`matrix`, `edges`, `relocated`, `different-time` and `tampered-source`.
`appendix-alone` and `new-provision` passed their profile checks; the matrix
passed the separate historical JORI byte golden. These observations remain
historical evidence; they never made markup an exception to the text rule.

Profile 0.3.0-draft corrects the renderer and enforces the complete display
grammar. All seven cases now exercise the real producer without a rendering
patch. The five normal cases pass common checks, source replay and their new
reference hashes. `tampered-source` passes the expected-detection test while
the input is rejected; `new-provision` passes the expected-rejection test while
conversion remains unsupported. Passing these tests does not accept those two
inputs.

A fixture-only producer stand-in changes only converter name/version. Its
artifacts pass the common checks and fail optional reference bytes. This is a
checker acceptance test, not evidence of a released second implementation.
The old [catalog](../examples/conformance/cases-profile-0.2.0-draft.json) and
old matrix golden remain byte-identical for use with their pinned historical
environment, not for recertification by this checker. Source and expected JSON
files and their digests remain unchanged.

## Acceptance contract and current gaps

The [deterministic acceptance contract](deterministic-bundle-contract.md)
defines count equality, full-node projection identity/version, strict display
and pending use requirements. The checker enforces `DB-COUNTS-1`: all four counts
must be nonnegative integers excluding booleans and equal the submitted data.
It counts every node record, distinct `law_id` values, crosswalk records and
projection records independently. The fixed cases still require an exactly
empty crosswalk file; a correctly counted nonempty crosswalk remains rejected.

Resealed mutation tests change each count separately, including incorrect zero,
negative, boolean and string values, so a digest failure cannot mask a missing
count predicate. A genuine zero crosswalk count passes. These tests retain the
fixture-only producer metadata described above.

The checker enforces `DB-PROJECTION-1/2` independently of producer helpers.
It matches projections by `(node_id, version_id)`, requires exactly one for
every non-law canonical version, and rejects duplicate pairs, missing or
surplus records and law-root projections with `PROJECTION_SET`. Copied fields
and source evidence remain checked by `PROJECTION_CONTENT` and
`PROJECTION_SOURCE`. The fixed cases have one version per node; using a pair
as the key does not establish general multi-version coverage.

`projection_version` must be exactly the string `"1"` (`PROJECTION_VERSION`).
The checker computes `projection_` plus the first 32 lowercase SHA-256 hex
digits of UTF-8 `version_id + "|full-node-v1|" + text`, without normalizing
text (`PROJECTION_IDENTITY`), and checks ID uniqueness separately
(`PROJECTION_ID_DUPLICATE`). These diagnostics can coexist; duplicate IDs do
not suppress identity checks. Invalid projection field types are rejected by
`PROJECTION_SCHEMA` before hashing or indexing them. Resealed tests cover
ID, version, pair, copied-field and type failures, keep record counts
consistent for set mutations, and retain positive empty/whitespace and
different-producer cases.

The ordinary `verify_canonical_artifacts()` rejects the same well-formed
projection mutations with `PROJECTION_DERIVATION_MISMATCH`; malformed fields
fail its `PROJECTION_LINE_<n>` reader. This agreement on acceptance does not
imply identical diagnostics. That artifact verifier accepts the unmodified
fixture-only producer's canonical files. `verify_manifest()` additionally
requires the reference converter metadata and rejects that producer with
`MANIFEST_ACQUISITION`; this reference-recipe restriction is separate from
common fixed-case conformance.

The implemented `DB-TEXT-1` and `DB-DISPLAY-1` checks use the independent
[text/display oracle](text-display-oracle.md) and complete-body mutation tests.
Execution attestation, additional parser limits and use eligibility remain
pending; fixed artifact checks do not imply any of those capabilities.

`requirements.json` records the implemented count, projection, text and display requirements in its
`requirements` array. Its separate `contract_design` link remains non-executable
metadata; a design reference adds no executed test or guarantee. The seven
catalog cases and their immutable source-authored oracles remain unchanged.

## Submission and execution

Create a submission JSON file alongside its artifact directories. Paths are
POSIX relative paths beneath that file's directory: absolute paths, `..`,
Windows drive paths, symlinks and special files are rejected. Catalog fixture/oracle paths are
similarly confined to the catalog directory. Source and expected hashes protect
the reviewed catalog inputs; trust in the catalog itself remains the caller's
responsibility. Keep the catalog hash in any cited result.

```json
{
  "schema": "jlegal-conformance-submission/v1",
  "jori_byte_regression": false,
  "cases": [
    {
      "id": "matrix",
      "outcome": "artifacts",
      "source": "matrix/source.xml",
      "source_sha256": "c7018e5dc6546ccf3534d11d78e8bc613f14ab4b0cea81082679c4a4a7fcf8d0",
      "official_law_id": "SyntheticStructureMatrix001",
      "bundle": "matrix/bundle"
    }
  ]
}
```

This excerpt intentionally shows one entry; submitting it alone fails because
all seven case IDs are required. Duplicate or unknown IDs fail too. Use each
catalog case's exact source, law key, corpus ID and fixed `converted_at` recipe.
For `new-provision`, use `outcome: "rejected"` and a relative `rejection` file
instead of `bundle`. That JSON object contains `accepted: false`, `code`,
`source_sha256`, and `official_law_id`, matching the catalog case.

```bash
python -m jlegal_okf.assurance check \
  --catalog examples/conformance/cases.json \
  --submission submission.json --out-dir new-conformance-report
```

The output directory must not exist. `conformance.json` contains case/layer
statuses, safe diagnostic codes, relation checks, denominator counts and input
JSON digests, with no submitted filesystem paths or raw exception strings.
`conformance.md` is a readable counterpart. `common_passed` excludes the
optional reference-byte layer; `passed` includes it when requested. CLI exit 0
means passed, 1 means completed nonconformance, 2 invalid configuration and 3
runtime failure. Both an honest reference failure and a missing required case
therefore produce a nonzero result.

The bundle checker is bounded to 1,024 files and 16 MiB per file. It is a local
artifact reader, not an execution sandbox, authenticity authority, or exhaustive
hostile-input parser. Use immutable submitted trees while checking. External
tool results remain separate observations and cannot override this report.
