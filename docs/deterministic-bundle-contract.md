# Deterministic bundle acceptance contract

## Status and authority

Design revision 1, 2026-10-06. This is the implementation contract for the next
acceptance changes, not a claim that the current tools enforce every row below.
The [0.2.0-draft profile](jlegal-okf-profile-0.2.0-draft.md) remains the active
profile until the coordinated revision described under [Version transition](#version-transition).
Existing normative rules are cited rather than silently redefined. New strict
acceptance requirements are explicitly labelled **target**. No producer, parser,
validator, runtime schema identifier, fixture oracle or golden is changed by
this design. The executable fixed-case requirements remain separately identified
in [requirements.json](../examples/conformance/requirements.json).

No result here certifies legal truth, source authenticity, completeness of all
applicable law, or correctness of a legal answer. Hash agreement establishes
agreement with recorded bytes; it cannot authenticate the party that recorded
them. Source preservation is compatible with holding a bundle for every
proposed legal use. AI output is neither a source nor an oracle.

## Four separate decisions

| Decision | Required evidence | Meaning and limit |
| --- | --- | --- |
| Source preservation | Original bytes, declared identity and acquisition facts; byte comparison | The recorded bytes were retained. Authentic origin requires separate evidence. |
| Canonical fidelity | Reviewed transformation rule, independent source-authored examples, source-to-canonical comparison | The stated rule preserves the reviewed information. Replay alone shares the producer's possible defects. |
| Bundle integrity | Exact schemas, identifiers, counts, references and file digests | The artifacts are internally consistent; this can hold for consistently falsified artifacts. |
| Use eligibility | The preceding evidence plus explicit purpose, jurisdiction, uniquely selected version, time and required reference evidence | The stated mechanical preconditions hold for that request. This is not legal advice or a guarantee of legal correctness. |

For each decision record `pass`, `fail`, `not_checked` or `unsupported`, its
requirement IDs, input/artifact digests, rule/profile version and observations.
These are target logical evidence fields, not additions to an existing runtime
report schema. A consumer must not turn a missing, unsupported or unexecuted
check into `pass`. A case-level expected rejection may pass a test of rejection
behavior while the input remains rejected; keep those two outcomes distinct.
The existing four validator layers classify diagnostic families, not degrees of
assurance; see [the diagnostic map](validator-layers.md).

## Requirement matrix

Rule sources are the active profile's
[preservation levels](jlegal-okf-profile-0.2.0-draft.md#preservation-levels),
[provenance policy](jlegal-okf-profile-0.2.0-draft.md#provenance-normalization-and-validation-policy),
[rights metadata](jlegal-okf-profile-0.2.0-draft.md#rights-metadata), the unchanged
[normalization catalog](normalization-rules.md), and the
[fixed-case specification](conformance-suite.md). Counts and projection
identities additionally cite the reference definitions below. Target rules are
specified by this document; they are not attributed to an external legal rule.

`C` denotes an existing contract clarified here; `T` denotes a target strict
acceptance rule. All rows apply to the reviewed e-Gov national-law path only,
unless they explicitly describe a consumer or parser boundary. Diagnostics in
backticks without a `target:` prefix already exist, but the stated broader
coverage can still be pending. A `target:` diagnostic is reserved for later
implementation and must not be reported as an available CLI feature.

| ID / kind | Source of rule and input condition | Deterministic acceptance predicate | Failure or hold diagnostic | Normal example / counterexample; oracle basis |
| --- | --- | --- | --- | --- |
| DB-SOURCE-1 / C | Profile, byte preservation; one admitted XML source | Embedded bytes equal the explicitly supplied source bytes; SHA-256, content URI and declared source input agree | `JLEGAL_OKF_SOURCE_MISMATCH`, checker `SOURCE_BYTES` | Preserve the invented `edges` source exactly / append one byte and reseal the outer manifest: reject against the independently fixed source digest. |
| DB-ACQUISITION-1 / C | Profile, provenance policy; optional receipt | Receipt hash, explicit official/requested ID, URL/query, format, time and XML facts agree; absent receipt leaves URL/time null; receipt rights stays null | `ACQUISITION_CONFLICT`; unsupported authenticity claim: `target: USE_EVIDENCE_INSUFFICIENT` | No receipt with null URL/time is archival input / a receipt hash conflicts with the admitted XML hash: reject. Mtime is not retrieval evidence; an unchecked or self-authored timestamp is not authenticated by passing consistency checks. |
| DB-COUNTS-1 / C | Manifest counts in `manifest_for()` and `verify_manifest()`; parsed canonical files | Every count is an integer excluding booleans, at least zero, and equals its definition below | `MANIFEST_TYPES`, `MANIFEST_COUNT_TAMPERED`; checker `MANIFEST_TYPES`, `MANIFEST_COUNTS` | For three nodes in one law, empty crosswalk and two projections: `(3,1,0,2)` / change only law or crosswalk count to 999 and reseal: reject. Values are independently counted, not trusted from the producer. |
| DB-PROJECTION-1 / C | Full-node projection policy; supported corpus versions | Exactly one projection per substantive node version; no law-root projection, duplicates, missing or surplus records; all copied fields and evidence agree | `PROJECTION_DERIVATION_MISMATCH`, `PROJECTION_DUPLICATE`; checker `PROJECTION_SET`, `PROJECTION_CONTENT`, `PROJECTION_SOURCE` | One non-root version maps to one record, even for empty text / duplicate it while keeping the same total by removing another: reject. |
| DB-PROJECTION-2 / C | Identity rule below; `jori-projection/v1` | `projection_version` is exactly string `"1"`; ID equals the defined digest and is unique within the submitted set | Existing reference `PROJECTION_DERIVATION_MISMATCH`; `target: PROJECTION_VERSION`, `target: PROJECTION_IDENTITY`, `target: PROJECTION_ID_DUPLICATE` in checker | Another producer implements the same rule and uses `"1"`: accept / `"test-1"`, integer 1, unknown version, one wrong ID or identical IDs: reject even after resealing. |
| DB-TEXT-1 / C | `JLEGAL-TEXT-PRESERVE-1`; reviewed source tree | Concatenate character data with only the profile's structural XML-whitespace exception; retain meaningful structure/attributes in their declared representation and source bytes | Checker `NODE_TEXT`, `NODE_ATTRIBUTES`; unsupported structure: `EGOV_XML_UNSUPPORTED_STRUCTURE:<tag>` | `<Style>abc</Style>` contributes `abc`, not markup; `<Sentence>A<Sup>2</Sup>B</Sentence>` gives `A2B` / insert XML serialization into canonical text: reject. Expectations are read from invented XML and the published rule. |
| DB-DISPLAY-1 / T | Source concept with canonical node; strict display acceptance | Exactly the body grammar below, with a version-bound payload equal to canonical text; no added prose and no markerless fallback | Reference `JLEGAL_OKF_SOURCE_CONTENT`; checker `target: SOURCE_DISPLAY_CONTRACT` | Exact empty or whitespace-only payload: accept / absent marker, changed payload or commentary before/after the body: reject strict display acceptance. Format-floor results remain separate. |
| DB-TIME-1 / C | Profile, conversion history; same fixed source, recipe, corpus ID, rules, environment and assertions | All canonical and bundle file bytes agree across executions when `converted_at` is fixed; do not include local paths or execution durations in artifacts | Existing relation checks; `target: REPRODUCIBILITY_MISMATCH` for execution evidence | Run in two directories with the same explicit corpus ID / same fixed recipe but one byte or one file differs: reject. A changed filename-derived corpus ID is instead a different recipe, not a reproducibility comparison. |
| DB-REPLAY-1 / T | Profile, source re-verification; explicit source and supported recipe | Source input is rechecked; source-to-canonical reproduction and evidence are bound to the exact bundle, recipe, code and dependencies | `MANIFEST_REPLAY_SOURCE_REQUIRED`, `MANIFEST_REPLAY_SOURCE_MISMATCH`, `MANIFEST_REBUILD_CORPUS`; `target: USE_EVIDENCE_INSUFFICIENT` | Matching independently observed replay is evidence for that input / hash-only validation, evidence for another bundle, or unknown converter recipe: hold use eligibility. |
| DB-MULTISOURCE-1 / C | Profile, single-source limitation | Strict source re-verification accepts exactly the supported single XML source; a multi-source hash ledger is not a substitute | `JLEGAL_OKF_VERIFY_SOURCE_UNSUPPORTED` | One admitted embedded XML source / two-source ledger: retain if otherwise valid for archival handling, but report unsupported for this source-reverified path. |
| DB-TEMPORAL-1 / T | Profile's unknown-date preservation; request with explicit date | Unknown and evidence-backed unbounded endpoints are distinct in separate use evidence; all requested temporal conditions have independently checkable support | `target: USE_TIME_UNKNOWN`, `target: USE_TIME_CONFLICT`, `target: USE_OUTSIDE_INTERVAL` | Finite supported interval contains the date / null start, conflicting versions, or expiry of evidence: no eligible result. See the decision table below. |
| DB-RIGHTS-1 / C | Profile, rights metadata; optional caller assertion | Exact four keys and types, not all null; v5/v1 without assertion or v6/v2 with assertion; canonical and exported values agree | `RIGHTS_SHAPE`, `RIGHTS_VALUES`, `RIGHTS_EMPTY`, `JLEGAL_OKF_RIGHTS_MISMATCH` | An opaque assertion may retain an unknown permission as null / change that null to true only in the export and reseal: reject the canonical/export mismatch. A URL or a caller-supplied true value is not evidence of verified permission. |
| DB-PARSER-1 / T | Admission and parser policy; bounded local input | No DTD or entity declarations, external entities or external resolution; predefined XML entities and numeric character references follow the character-data rule; explicit byte/depth/element/time/memory limits; no committed partial output on failure | Existing e-Gov admission diagnostics; generic limit diagnostics to be fixed with their parser implementation | Small invented input within the selected bounds / one unit over a bound or external entity: reject and preserve the prior output. Numeric generic limits remain an implementation prerequisite, not a current guarantee. |
| DB-USE-1 / T | Purpose-specific request and the four decisions above | All mandatory predicates in the use table hold; retrieval rank, model output and manually entered dates never substitute for evidence | `target: USE_EVIDENCE_INSUFFICIENT`, `target: USE_REFERENCE_UNRESOLVED`, `target: USE_VERSION_CONFLICT`, `target: USE_INCOMPLETE_SEARCH` | Complete, fresh evidence for one reviewed request may pass / truncated search or unresolved necessary reference: hold, even when bundle hashes agree. |
| DB-ORACLE-1 / C | Fixed-case suite and measurement separation | Fixed source-authored expected values, independent checker and tamper tests; executing the producer is a separate observation | Existing checker case/relation failures; missing observation stays `not_checked` | Independently enumerate text and counts / bless regenerated golden values solely because the producer emitted them: reject the acceptance argument. |

### Applicable contract versions

The `C` rows clarify `J-LEGAL-OKF/0.2.0-draft` with `jori-corpus/v2`,
`jori-projection/v1` / `"1"`, and the v5/v1 or rights-bearing v6/v2
manifest/bundle pair. DB-PROJECTION-1/2 use the projection policy independently
of producer name/version; DB-RIGHTS-1 selects the appropriate pair. These
requirements carry forward unchanged to the coordinated target tuple below.
DB-COUNTS-1 and DB-PROJECTION-2 clarify existing output formats. At design
review, their checker enforcement was incomplete; the
[conformance suite](conformance-suite.md#acceptance-contract-and-current-gaps)
records subsequent implementation status. DB-TEXT-1 is an existing rule with a
known implementation discrepancy.

The `T` rows apply only to the new strict acceptance path under
`J-LEGAL-OKF/0.3.0-draft` and the coordinated target tuple, once implemented.
DB-DISPLAY-1 has its complete grammar here; DB-TEMPORAL-1 and DB-USE-1 use the
request decision table. DB-REPLAY-1 and DB-PARSER-1 require separately versioned
execution-evidence and parser-limit contracts before implementation acceptance.
Their identifiers/serialization and numeric limits remain the explicit
prerequisites listed under [Implementation gaps and handoff](#implementation-gaps-and-handoff).
No `T` row may be advertised as checked by a current schema or tool merely
because its requirement ID is present in documentation.

Reference definitions used by the count/projection clarification are
`src/jlegal_okf/pipeline.py` `manifest_for()`,
`src/jlegal_okf/pipeline.py` `verify_manifest()`, and
`src/jlegal_okf/model.py` `Temporal`. They describe existing implementation
contracts; none establish legal applicability.

### Count definitions and scope

For successfully parsed canonical records `N`, crosswalk records `X` and
projection records `P`:

- `node_count = len(N)`, including root and all version records;
- `law_count = len({n.law_id for n in N})`, not root-row or file count;
- `crosswalk_count = len(X)`, not unique targets or nonblank-file count;
- `projection_count = len(P)`.

Syntax, uniqueness, hierarchy and semantic checks remain independent. Correct
counts do not excuse malformed rows, duplicates, invalid crosswalk targets or
wrong projection content. The current seven fixed cases require an empty
crosswalk and one source law; they are not a general nonempty-crosswalk test.
Recompute enclosing hashes in negative tests so a checksum failure cannot mask
these predicates. Test wrong positive values, wrong zero, negative values,
booleans and strings; a correctly counted zero is valid.

### Projection policy, version and identity

The policy is `full-node-v1`. Its wire identifier is
`schema = "jori-projection/v1"`, `projection_version = "1"`. This version names
the projection rule, not a producer's product version. Every canonical kind
except `law` is substantive in the current reviewed kind set; unknown kinds
remain unsupported. Match projections by `(node_id, version_id)`, not just by
`node_id`, because a corpus can represent multiple versions. The current fixed
cases have only one version per node; their checker must not claim general
multi-version coverage from those cases.

Copy `node_id`, `version_id`, `law_id`, `locator`, `heading`, `text`, `kind`,
`temporal` and `source` (as `evidence`) exactly from that canonical version.
No child-text subtraction, ranking, summarization or whitespace normalization
is permitted. Identity is:

```text
projection_id = "projection_" + lowerhex(SHA256(UTF8(
    version_id + "|full-node-v1|" + text
)))[0:32]
```

This exact existing expression is preserved. It is not NFKC normalization and
must not change as a side effect of refactoring. The version ID has its existing
validated `ver_` prefix and UUID form; `text` is unmodified Unicode character data. Validate both
the formula and uniqueness; truncating SHA-256 to 128 bits is collision
resistance, not proof of impossibility. A collision is a rejection, never a
reason to invent a salt.

Source of this clarification: `src/jlegal_okf/pipeline.py` `make_projection()`
and `src/jlegal_okf/model.py` `RetrievalDocument`. The normal artifact verifier
already compares against this derived projection; the independent checker must
implement the formula without importing producer code.

`conversion.name` and `conversion.version` are producer metadata. A different
nonempty producer name/version is allowed by the common fixed-case contract
when internally consistent with the profile and provenance. This does not
allow an arbitrary `projection_version`. The reference manifest/export/replay
path currently requires its exact converter metadata; it is a reference-recipe
verifier, not the common acceptance gate for every producer. Unsupported replay
for another producer is reported separately and cannot be turned into a common
profile failure solely because the producer name differs.

### Character data and display grammar

The existing text rule remains unchanged: no NFKC, stripping, case folding,
Ruby removal or inferred punctuation on canonical text. Sup/Sub, Ruby/Rt and
reviewed Style content contribute character data in source order; their markup
is not inserted into text. Structure and attributes must stay traceable to the
retained XML and the reviewed canonical representation. Unsupported nontrivial
structure is rejected rather than stripped.

Required source-authored examples include `A<Ruby>B<Rt>C</Rt></Ruby>D` ->
`ABCD`, `A<Sub>2</Sub>B` -> `A2B`, self-closing empty elements -> empty text,
leaf XML whitespace -> the identical whitespace, and U+3000/U+00A0 -> the same
characters. Predefined XML entities and numeric character references are parsed
into character data, for example `A&amp;B&#x20;C` -> `A&B C`; they are distinct
from forbidden DTD/entity declarations. Parent text includes already-rendered child content; it must not
re-elide leaf whitespace. A structural parent may omit only its own XML
formatting whitespace as defined by the profile. XML parser newline/entity
processing and the resulting character data are distinct from byte preservation:
the original XML bytes remain available regardless of that parse.

For target strict source-display acceptance define `title` as the first
nonempty value of canonical `heading`, `label`, `locator`, and define:

```text
begin = "<!-- jlegal-source:" + version_id + ":begin -->"
end   = "<!-- jlegal-source:" + version_id + ":end -->"
body  = "# " + title + "\n\n## Source text\n\n" + begin + text + end + "\n"
```

Compare the complete decoded body to that construction. Match the two framing
markers at their constructed positions; marker-like characters inside the
known payload are source data, not additional framing. No trimming, substring
presence test or insertion of helpful commentary is allowed. This is an
explicit common target grammar, implementable by another producer, not a
requirement for that producer's complete YAML formatting or byte golden to
match JORI. Existing markerless or differently headed submissions may still
receive their historical bounded result; they cannot receive this new strict
display result. This checks stored character data, not the visual output of an
arbitrary Markdown renderer. Consumers must display source as text, not execute
or reinterpret it as HTML or instructions.

## Temporal and use decision table

Keep the canonical `Temporal` fields and their historical meanings intact.
A null field records absence of a known value, never evidence of infinite
validity. Existing structural interval checks and research search behavior do
not establish use eligibility.

Target use evidence records each endpoint separately as `unknown`, `finite`
(with an ISO date) or `unbounded` (without a date), together with evidence
references and the reviewed rule establishing it. A finite or unbounded
endpoint without evidence is unknown for acceptance. An absent repeal date,
absence of a matching search result, or a user's unchecked date assertion is
not evidence for an unbounded endpoint. The evidence is separate from canonical
source facts; it must never fill a canonical null by inference.

A use request identifies purpose, jurisdiction, source law identity, selected
version(s), date, required-reference scope and the acceptance-rule version.
The evidence binds those to source/bundle digests, code/dependency/recipe
identities, observation time and an explicit validity horizon or revalidation
rule. Evidence for a different request, expired evidence or an unevaluated
freshness rule cannot pass. Cross-references necessary to the request must be
resolved to unique evidenced targets; completion of a truncated search cannot
be claimed. No automatic legal interpretation is introduced.

| Condition, evaluated in this order | Mechanical outcome |
| --- | --- |
| Contradictory identity, source mismatch, conflicting version evidence, malformed evidence or incompatible rule version | Reject; identify the conflicting requirement. |
| Missing source verification, unknown endpoint, unsupported replay, missing reference, stale evidence or incomplete search | Hold; name every missing prerequisite. Saving the source is still allowed. |
| All required evidence exists; finite interval `[start, end)` excludes request date | Reject for this requested date. At `start` it is included; at `end` it is excluded. |
| All required evidence exists; finite/unbounded endpoints contain request date; version and necessary references are unambiguous | Eligible for the specified mechanical conditions only. Legal correctness is not certified. |

A finite start and evidenced unbounded end may pass the interval predicate;
the identical canonical values with a merely unknown end must hold. Do not
choose among conflicting versions using search score or a model. An implementation
may hold every legal-use request until an independently evidenced policy is
available; it must not manufacture a passing example from an actual law.
Synthetic decision-table inputs test the algorithm, not real legal applicability.

## Time, evidence and execution

At fixed `converted_at`, explicit `corpus_id`, source bytes, recipe, rights,
profile/rule versions, code, dependencies and settings, compare the complete
canonical and bundle file set and bytes across separate processes/directories.
Keep observation time, duration, local paths and execution logs outside those
artifacts. Do not use a copied output as evidence of two executions.

With only `converted_at` changed, `corpus.jsonl`, `crosswalk.jsonl`,
`projection.jsonl`, their digests, node/version identities and
`build_options_sha256` remain identical. The canonical manifest and concept
provenance timestamps, their containing files and hashes, and the outer bundle
manifest may change. Recompute the expected artifact dependency graph rather
than asserting that only one file changes. A change to rights or the recipe is
a different build and may change provenance, identities and hashes.

The independent artifact checker attests only its fixed input assertions.
Reference source replay checks the recorded recipe on a particular input and
can reproduce a shared bug. Target strict acceptance requires both the reviewed
rule/independent conformance evidence for the implementation and a source check
for the particular bundle; neither implies the other. The evidence schema and
execution resource limits must be reviewed before their checks become available.
Standard OKF `verified` retains its standard meaning; do not put custom legal
assurance levels there. An empty `verified` is not evidence of a legal review.

## Version transition

The following version plan is fixed for the coordinated text/display correction;
the values are reserved here, not activated in runtime code by this document.

| Identifier | Current | Coordinated target and reason |
| --- | --- | --- |
| Profile | `J-LEGAL-OKF/0.2.0-draft` | `J-LEGAL-OKF/0.3.0-draft`: explicit acceptance and changed output contract |
| Canonical wire schema | `jori-corpus/v2` | `jori-corpus/v3`: prevent silent reinterpretation of old text/identity products |
| Reference converter | `JORI Engine` / `0.1.0-draft` | `JORI Engine` / `0.2.0-draft`: distinguish the corrected transformation |
| e-Gov adapter | `egov_xml` / `1` | `egov_xml` / `2`: changed character-data rendering; generic adapters retain their own version until separately revised |
| Projection | `jori-projection/v1`, version `"1"`, `full-node-v1` | Retain: its field mapping and ID formula are unchanged; changed version content changes derived IDs, while unchanged content retains them |
| Manifest / bundle | v5/v1 without rights; v6/v2 with rights | Retain exact key shapes if unchanged; validate the supported profile/converter/adapter tuple, not schema names alone |
| Package version / Git tag | Independent of the above | No automatic change; distribution and release decisions are separate |

Count/identity validator fixes enforce the clarified current contract and do
not by themselves change producer bytes or rewrite old golden files. The
text/display transition must change the profile, corpus schema, converter and
e-Gov adapter tuple together, document every changed digest/identity dependency,
and retain the old normative document and golden evidence. Do not mix the new
parser/renderer with old recipe labels. A new normalization or preservation
meaning requires a new rule ID; correcting the implementation to match the
existing character-data rule does not change that rule's definition.

Schema/profile/adapter labels do not themselves enter `version_id`. Its
inputs remain `node_id`, temporal fields, text, heading, label and attributes;
`law_id`/`node_id` continue to follow their existing identity rules. Therefore
unaffected nodes can retain both version and projection IDs across this
transition. The schema/profile/recipe tuple and complete artifact hashes, not
an assumption that every ID changes, distinguish the contracts. A rights-only
change alters its bound manifest/provenance hashes, not canonical node IDs.
See `src/jlegal_okf/model.py` `version_identifier()`.

Archive old bundles and their pinned historical verifier environment. The new
strict path must reject the old corpus/profile/recipe tuple before replay;
reading historical artifacts is not strict acceptance. Recompile from the
original bytes for a new bundle; never patch the schema string, hashes or IDs
in place to simulate migration. An old environment is for reproduction of its
historical result, not automatic fallback after new acceptance fails.

## Implementation gaps and handoff

- At design review, the normal manifest verifier checked all four counts but
  the fixed checker compared only node/projection counts. Subsequent count
  enforcement and resealed negative tests are recorded in the
  [conformance suite](conformance-suite.md#acceptance-contract-and-current-gaps).
  That implementation status does not widen the fixed catalog's scope.
- The fixed checker currently accepts nonempty arbitrary projection ID/version
  strings. Add the exact rule and uniqueness checks; retain valid distinct
  producer metadata. Its single-version catalog does not measure multi-version
  implementations.
- Reference Style rendering currently disagrees with the character-data rule.
  Preserve the measured discrepancy until the coordinated correction and its
  independent source-authored expectations pass; do not turn it into an
  allowed exception. Extend examples for inline content and whitespace.
- The reference source-body builder already rejects a same-version framing
  marker inside payload with `JLEGAL_OKF_SOURCE_MARKER_COLLISION`, and its
  verifier uses first-occurrence search plus whole-body comparison. The fixed
  checker also rejects any additional `<!-- jlegal-source:` occurrence, even
  inside literal source text. The target constructed-body comparison changes
  that rejection policy intentionally: known payload is data, not framing.
  Add an independent literal-marker payload example at the grammar boundary;
  do not claim this current refusal silently accepts incorrect source text.
- The strict display rule and use-evidence decisions are target requirements.
  Generic parser limits, transactional output completion, execution-attestation
  evidence and supported replay environments require implementation and tests.
- Concrete depth/element/time/memory limits and evidence serialization are
  deferred to those implementations. They cannot be left implicit there:
  until reviewed and implemented, record `unsupported` or `not_checked` and
  hold use acceptance. This is a defined default, not discretionary approval.
- Rights-bearing and multi-source recipes are outside the present fixed
  catalog's measured coverage. Future catalogs need separately reviewed
  fixtures/oracles; adding an identifier to this document does not execute a test.
- Current generic adapter utilities do not expand the national-law profile to
  municipal HTML/PDF, OCR, case law or legal interpretation.

The common requirement predicates above are producer-independent. Their
accept/reject result must depend on the submitted input, declared supported
contract and evidence, not the name of the producing model or implementation.
Exact reference replay and optional reference-byte regression remain explicitly
separate, narrower observations.
