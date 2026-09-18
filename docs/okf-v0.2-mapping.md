# OKF v0.2 Key Mapping

## Status and scope

This document maps the OKF v0.2 standard frontmatter keys and the `jlegal`
extension block to the canonical corpus fields that produce them, and states
the trust boundary a consumer of the exported bundle is left with. It
describes the exporter's actual output
(`src/jlegal_okf/legal_okf.py` `export_okf()`), verified by compiling
[`examples/synthetic_egov_law.xml`](../examples/synthetic_egov_law.xml)
through `jlegal compile --adapter egov_xml` and `jlegal export-okf` into a
scratch directory and reading the generated `source/*.md` and
`derived/knowledge.md` concept frontmatter directly, not by reading the
exporter source alone. Every mapping below is transcribed from that run's
actual YAML, not inferred from the code that produced it.

A bundle has two concept layers, and every OKF standard key is populated
differently in each:

- **Source layer** (`source/<version_id>.md`, one file per canonical node) —
  built by `src/jlegal_okf/legal_okf.py` `_source_frontmatter()`.
- **Derived layer** (`derived/knowledge.md`, exactly one file per bundle) —
  built by `src/jlegal_okf/legal_okf.py` `_derived_frontmatter()`.

## 1. OKF v0.2 standard keys

| Key | Source layer | Derived layer |
| --- | --- | --- |
| `type` | `src/jlegal_okf/legal_okf.py` `_type_for()`: `"Japanese Legal Document"` for a law root, `"Japanese Legal Appendix"` for an appendix/table/row/cell, `"Japanese Legal Provision"` otherwise. | Fixed `"AI-derived Legal Knowledge"`. |
| `title` | `node.heading or node.label or f"{node.kind.value}: {node.locator}"`. In the verified run the law's `MainProvision` node had neither a heading nor a label, so its title fell back to the locator form; the `Article` node's title was its `ArticleCaption` text, `（目的）`. | Fixed `"Derived legal knowledge boundary"`. |
| `description` | `f"Source-preserving {node.kind.value} from Japanese legal XML."`. | Fixed `"No AI-derived legal knowledge is included in this source-preserving export."`. |
| `resource` | `jlegal://law/<source_key-or-law_id>/<node_id>` (`quote()`-escaped). | `jlegal://derived/<law_id>`, or `jlegal://derived/multi-law` when the bundle spans more than one `law_id`. |
| `sources` | Two entries, both layers, unconditionally: `canonical-corpus` (`/canonical/corpus.jsonl`) and `official-source` (the embedded source reference path `src/jlegal_okf/legal_okf.py` `_source_reference()` returns — `/references/source.xml` for the single-source case this profile always produces; see `docs/known-limitations.md` §3 for the unused multi-source ledger). | Same two entries. |
| `generated` | `{"by": EXPORTER}`, where `EXPORTER` is the fixed string `jlegal-okf-exporter/0.1.0-draft`. | Same. |
| `verified` | Always `[]`. See §3 below. | Always `[]`. |
| `status` | Fixed literal `"draft"`. | Fixed literal `"draft"`. |

## 2. `jlegal` extension keys

The `jlegal` block is where every fact specific to this profile — not
representable in the OKF standard shape above — lives. Both layers carry
`profile`, `layer` (`"source"` or `"derived"`), `acquisition` (the full
e-Gov acquisition record, `rights` field always `null` —
`docs/known-limitations.md` §3), `conversion` (the fixed
`name`/`version`/`profile` triple carried unchanged from
`src/jlegal_okf/pipeline.py` `JLEGAL_CONVERTER` — in the verified run's
actual YAML this was
`{"name": "JORI Engine", "version": "0.1.0-draft", "profile": "J-LEGAL-OKF/0.2.0-draft"}`),
and `converted_at`.

The source layer additionally carries the canonical node's own identity and
content fields verbatim: `law_id`, `node_id`, `version_id`, `parent_id`,
`kind`, `locator`, `ordinal`, `branch`, `content_sha256` (a
`text_sha256(node.text)` digest), the full `SourceRef` (`uri`, `sha256`,
`adapter`, `source_key`, `page`, `byte_start`, `byte_end`), the full
`Temporal` (`valid_from`, `valid_to`, `promulgated`, `repealed` — see
`docs/known-limitations.md` §4 for what an `egov_xml`-adapted corpus
actually populates there), and `attributes` (the node's XML attribute
pairs — in the verified run this included `egov_tag` and
`build_provenance_sha256`, but the two are not attached at the same point:
`egov_tag` is written directly by
`src/jlegal_okf/egov.py` `egov_xml_adapter()` (confirmed present on its
output before any compile step runs), while `build_provenance_sha256` is
absent from that adapter's raw output and is attached afterward, once per
compile, by
`src/jlegal_okf/pipeline.py` `_bind_build_provenance()` — it fingerprints
the build recipe and inputs, not anything in the source XML).

The derived layer instead carries `source_version_ids` (always `[]`; no
current adapter or CLI path produces derived content that would reference
source versions — see `docs/known-limitations.md`, "Scope: LLM audition is
not part of v0.1") and `content_policy: none-generated`.

## 3. Why `verified` is always empty

`src/jlegal_okf/legal_okf.py` `_source_frontmatter()` and
`_derived_frontmatter()` both hard-code `"verified": []`; nothing in the
exporter or the canonical pipeline ever appends to it. This is deliberate,
not an omission: a `verified` entry asserts that a specific person or
process checked the concept, and no such check exists in this pipeline — a
deterministic XML-to-corpus-to-bundle projection is not human or
third-party review. Writing `"verified": []` is this profile's way of
saying so plainly rather than leaving the field out or filling it with an
assertion the pipeline cannot back up. An empty list is the honest
statement here, not a placeholder for this exporter to fill in later.

## 4. The trust discontinuity between OKF conformance and this profile

An OKF v0.2-conformant consumer is entitled to read the eight standard keys
in §1 and ignore every key it does not recognize, `jlegal` included — that
is what makes the extension mechanism additive rather than binding. A
consumer that does exactly that sees a "draft", never-independently-verified
document with no legal reasoning attached; it cannot see fail-closed
guarantees like "this node's `Temporal` came only from `egov_xml`, never a
generic-adapter caller claim" (`docs/known-limitations.md` §4), because that
guarantee lives entirely inside `jlegal`, which such a consumer is free to
skip.

**OKF v0.2 conformance is the floor this bundle's shape satisfies; passing
`jlegal validate-okf` is the ceiling this profile actually guarantees.**
Anything in between — reading the standard keys and trusting the result as
this profile's fail-closed guarantees, without also validating and
consuming `jlegal` — is outside what this profile promises.
`src/jlegal_okf/legal_okf.py` `validate_okf()` is the only check that
recomputes every `jlegal` field from the canonical corpus and rejects a
bundle whose frontmatter disagrees with it
(`src/jlegal_okf/legal_okf.py` `_validate_source_concept()`); reading the
OKF standard keys alone does not run any of that.
