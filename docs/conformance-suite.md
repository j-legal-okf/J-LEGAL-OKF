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
| `jori_byte_regression` | Optional immutable reference hashes from the existing structure-matrix golden | Exact compatibility with that JORI recipe; never required for another producer's common result |

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

When a concept uses versioned `jlegal-source` comments, the checker requires
exactly one matching begin/end pair and exact enclosed text, including empty
and whitespace-only text. Headings and presentation outside the pair are not
compared to the reference template. Markerless bodies receive only a text
presence check; that check does not establish exact display-body fidelity or
exclude additional prose. Canonical node text is always checked exactly.

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

### Observed reference discrepancy

The current reference converter preserves a `Style` leaf as literal
`<Style>…</Style>` inside the appendix and root canonical text. The profile's
`JLEGAL-TEXT-PRESERVE-1` character-data rule does not specify this exception.
Accordingly, the unmodified reference submission reports `NODE_TEXT` for
`matrix`, `edges`, `relocated`, `different-time` and `tampered-source`.
`appendix-alone` and `new-provision` pass their profile checks; the matrix still
passes the separate existing JORI byte golden. These are measurements, not a
change to the converter or the normative profile.

Checker tests also construct a fixture-only producer stand-in with
character-only rendering and a distinct producer name. Its artifacts pass the
common checks and fail the optional JORI bytes. This is a checker acceptance
test, not evidence of a released second implementation. Tests explicitly keep
the unmodified reference discrepancy visible and reject arbitrary added markup.

## Acceptance contract and current gaps

The [deterministic acceptance contract](deterministic-bundle-contract.md)
defines count equality, full-node projection identity/version and target strict
display/use requirements. The checker enforces `DB-COUNTS-1`: all four counts
must be nonnegative integers excluding booleans and equal the submitted data.
It counts every node record, distinct `law_id` values, crosswalk records and
projection records independently. The fixed cases still require an exactly
empty crosswalk file; a correctly counted nonempty crosswalk remains rejected.

Resealed mutation tests change each count separately, including incorrect zero,
negative, boolean and string values, so a digest failure cannot mask a missing
count predicate. A genuine zero crosswalk count passes. These tests use the
fixture-only producer described above and do not repair the Style discrepancy.

The checker still accepts arbitrary nonempty projection ID/version strings.
That gap is not evidence that the missing predicates hold. The target display
grammar is stricter than the marker/presence behavior documented above and is
not yet enforced here.

`requirements.json` records the implemented count requirement in its
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
