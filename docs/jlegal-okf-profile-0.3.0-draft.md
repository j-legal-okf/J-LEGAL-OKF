# J-LEGAL-OKF Profile 0.3.0-draft

## Status and purpose

This is the active normative profile for the public core. It supersedes
[0.2.0-draft](jlegal-okf-profile-0.2.0-draft.md), whose complete document remains
unchanged as historical evidence. J-LEGAL-OKF remains an unofficial draft for
source-preserving Japanese national-law bundles, without government or OKF
endorsement, legal interpretation, or a guarantee of legal accuracy.

This revision corrects character-data rendering and requires the complete
source-display grammar. It implements DB-TEXT-1 and DB-DISPLAY-1 of the
[deterministic acceptance contract](deterministic-bundle-contract.md).
Resource limits, execution attestation, and use-eligibility decisions pending in
that document are not activated by this profile revision.

## Normative inheritance and precedence

The following provisions of the unchanged 0.2.0-draft document are incorporated
by reference. This table is exhaustive for inherited normative sections.

| Inherited section | Scope retained |
| --- | --- |
| Normative and authoritative references | The XML, API and OKF format sources and non-endorsement boundary. |
| Preservation and scope | Priority order; source/canonical/derived separation; national-law-only input; explicit identity; admission, unsupported structures, acquisition and single-source export/replay boundaries. |
| Preservation levels | All of `JLEGAL-BYTE-PRESERVE-1`, `JLEGAL-TEXT-PRESERVE-1` and `JLEGAL-DISPLAY-TRIM-1`, including the exact structural-whitespace exception, leaf and mixed-content treatment, and examples. |
| Provenance, normalization, and validation policy | Acquisition facts, conversion timestamps, content-addressed source references, explicit source requirement, identifier rules, deterministic identity inputs, and the four diagnostic families. |
| Rights metadata | Optional explicit four-field assertions, exact types, no inference, manifest/bundle key sets, hash binding, and canonical/export agreement. |
| Exclusions | LLM execution, OCR, municipal ordinances, case law, interpretation, and the remaining excluded capabilities. |

The supported version tuple and display requirements below take precedence
over conflicting version literals or presentation behavior in inherited text.
Historical change narratives and claims that prior revision artifacts remain
byte-identical are not imported as compatibility promises across revisions.
Within one supported tuple and fixed recipe, the inherited deterministic and
rights-absence byte guarantees continue to apply. Links in historical documents
remain historical; their statements that 0.2.0-draft is active do not override
this document. The unchanged [normalization catalog](normalization-rules.md)
continues to define `JLEGAL-NORM-1` through `JLEGAL-NORM-5`.

## Supported version tuple

| Component | Required value |
| --- | --- |
| Profile and admission profile | `J-LEGAL-OKF/0.3.0-draft` |
| Canonical corpus | `jori-corpus/v3` |
| Reference converter | `JORI Engine` / `0.2.0-draft` |
| e-Gov adapter | `egov_xml` / string `"2"` |
| Reference exporter (`generated.by`) | `jlegal-okf-exporter/0.2.0-draft` |
| Projection | `jori-projection/v1`, string `"1"`, `full-node-v1` |
| Manifest / bundle, without rights | `jori-manifest/v5` / `jlegal-okf-bundle/v1` |
| Manifest / bundle, with asserted rights | `jori-manifest/v6` / `jlegal-okf-bundle/v2` |

The generic JSON/XML/HTML adapters retain version `"1"` and their v3 manifest
shape, but use the shared `jori-corpus/v3` model. They remain outside this
national-law export profile. Package versions and Git tags are independent.

The common fixed-case checker accepts a different nonempty converter name and
version when the metadata is internally consistent with this profile. It still
requires e-Gov adapter version `"2"`. The reference manifest/export/replay path
requires the exact reference converter tuple. Reference-byte regression is
separate from common conformance; another producer need not share YAML bytes or
the reference generator name.

## Preservation and scope

The inherited source, hierarchy, temporal, rights, and unsupported-structure
boundaries apply. `NewProvision` still rejects the entire conversion with
`EGOV_XML_UNSUPPORTED_STRUCTURE:NewProvision`. Unknown nontrivial structure is
not newly accepted by this change. Only already-admitted structures are rendered.

## Preservation levels

Original XML bytes remain unchanged in `references/source.xml`, with their
original hash. Canonical text is parsed character data in source order: Ruby/Rt,
Sup/Sub, Line, and an admitted Style leaf contribute text and tails, without
XML serialization. Only directly owned XML S whitespace under a non-leaf member
of the inherited structural set can be omitted. Leaves, mixed-content headers,
U+3000, NBSP, repeated spaces and combining characters remain unchanged. A parent
never re-elides a child's retained whitespace. Heading/label trimming still uses
`JLEGAL-DISPLAY-TRIM-1` and never trims canonical text.

The original XML retains inline boundaries and attributes such as `Line Style`;
the reviewed canonical representation retains its node hierarchy, locators,
parents, order/numbering and meaningful attributes. Plain text cannot recover
Ruby/Rt or Line boundaries. The text correction does not add canonical inline
nodes or claim that text alone represents the entire XML information set.

XML's parsing of literal CR/CRLF into LF and of `&#xD;` into CR is separate from
byte preservation. Once canonical text exists, its CR/CRLF must survive export,
storage and reading without another newline conversion. The fixed
[text/display oracle](text-display-oracle.md) supplies independent literals for
these cases; the existing full-law fixtures check the separate byte/structure
contract.

## Complete source-display grammar

For the first nonempty canonical `heading`, `label`, or `locator` as `title`:

```text
begin = "<!-- jlegal-source:" + version_id + ":begin -->"
end   = "<!-- jlegal-source:" + version_id + ":end -->"
body  = "# " + title + "\n\n## Source text\n\n" + begin + text + end + "\n"
```

The complete decoded source body must equal this construction. Empty and
whitespace-only payloads are valid. Matching marker strings inside known payload
are literal data, including the same version-bound begin/end strings. There is
no first-marker search, substring fallback, title substitution, added prose,
trimming, or newline normalization. A missing final LF is a mismatch.

Frontmatter delimiters may use LF or CRLF. After the closing delimiter line,
zero or one empty line (LF or CRLF) is a separator outside the body; a second
empty line belongs to the body and fails the exact grammar. The reference
producer emits LF frontmatter followed by exactly one LF separator line.
The reference validator reports `JLEGAL_OKF_SOURCE_CONTENT`; the independent
checker reports `SOURCE_DISPLAY_CONTRACT`. Its `CONCEPT_TEXT` separately checks
the declared content hash. Format-floor acceptance alone does not establish
this profile's display contract. Consumers must display source as text without
executing it as HTML or instructions; stored-character fidelity is not a
promise about arbitrary Markdown renderers.

The literal same-version-marker fixture is a grammar-boundary example. It is
not evidence of a complete law artifact with a self-referential version ID.

## Provenance, normalization, and validation policy

All inherited identity inputs and formulas remain unchanged. Schema/profile/
adapter labels do not enter `version_id`; unchanged text, heading, label,
attributes and temporal inputs retain it. Corrected text changes the affected
version ID and its full-node projection ID. Every corpus file changes schema
bytes, even when its node IDs and projection bytes remain unchanged. Recipe
metadata changes build-options and manifest hashes; exporter/profile metadata
changes concept, index and outer-bundle bytes.

The ordinary corpus reader rejects v1, v2 and unknown schemas with
`CORPUS_SCHEMA_UNSUPPORTED` before replay. The manifest verifier rejects an old
adapter version with `MANIFEST_OPTIONS`, and an old/mixed reference
converter/profile or e-Gov declared under the generic v3 manifest schema with
`MANIFEST_ACQUISITION`, before replay. A missing required v5/v6 key remains
`MANIFEST_KEYS`; malformed option types retain `MANIFEST_TYPES`.
The checker reports `NODE_SCHEMA`, `ADAPTER_METADATA`,
`CONVERTER_METADATA`, `CONCEPT_PROVENANCE` or `BUNDLE_SCHEMA` for their respective
boundaries; type errors can additionally report `MANIFEST_TYPES`. The complete
diagnostic scope is documented in [validator-layers.md](validator-layers.md).

Old artifacts must be recompiled from the original XML bytes under a supported
new recipe. Do not patch schema strings, IDs or hashes in place as migration.
Keep old artifacts with a pinned historical verifier for historical
reproduction only. The archived
[0.2.0 catalog](../examples/conformance/cases-profile-0.2.0-draft.json) and
[old golden](../examples/fixtures/synthetic_egov_structure_matrix.golden.json)
are evidence for that environment; the new checker does not recertify an old
passing result. See [the new golden and dependency changes](synthetic-golden-matrix.md).

## Rights metadata

The inherited four-field, explicit-assertion contract is unchanged. Neither the
text correction nor a new version label verifies a licence or permission.

## Exclusions

The inherited exclusions remain. This revision adds no generic-parser resource
limits, execution-evidence schema, temporal applicability inference, or legal-use
eligibility feature. Replay agreement and fixed synthetic conformance are
bounded evidence, not source authenticity or legal correctness.
