# J-LEGAL-OKF scope

## Names

- Specification: `J-LEGAL-OKF`
- Python package: `jlegal_okf`
- Distribution: `jlegal-okf`
- CLI: `jlegal`
- Reference implementation: `JORI Engine`

## In scope for v0.1

The canonical `jori-corpus/v3` model, deterministic identifiers, hashes,
manifests, crosswalk serialization, and retrieval projection; validator
diagnostics; generic JSON/XML/XHTML adapters; saved e-Gov national-law XML
conversion and the explicit `fetch` helper; OKF v0.2 export and validation for
verified e-Gov corpora; the `jlegal` CLI; and authored synthetic fixtures with
their offline regression tests.

The public input utilities include `src/jlegal_okf/input_limits.py`: bounded
regular-file reads, XML DTD/entity/external-reference rejection, and structured
input checks. XML and source JSON are capped at 64 MiB and depth 128, with
250,000 XML elements or JSON structural tokens. Conversion options use 1 MiB
input/canonical byte caps, depth 32, 10,000 tokens and 4096-bit integers.
JSON/YAML preflight and API graph checks reject aliases, cycles, custom types
and nonfinite values as applicable. These implementation limits do not change
accepted-source profile scope or claim official XML conformance or hard
process resource isolation. See
[`SECURITY.md`](../../SECURITY.md) for the exact boundaries.

## Out of scope for v0.1

LLM execution, audition, enrichment, and provider integration; OCR; municipal
ordinances; case law; legal interpretation or advice; Akoma Ntoso output;
index, search, and evaluation; and benchmark corpora. Adding any of these
requires a reviewed profile revision.

Index, search, and retrieval-quality benchmarking are out of scope because they
measure a search implementation rather than a conversion, not because they are
held back. They belong to a separate openly licensed project that takes OKF
bundles and this project's retrieval projection as its input.
