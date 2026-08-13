# J-LEGAL-OKF scope

## Names

- Specification: `J-LEGAL-OKF`
- Python package: `jlegal_okf`
- Distribution: `jlegal-okf`
- CLI: `jlegal`
- Reference implementation: `JORI Engine`

## In scope for v0.1

The canonical `jori-corpus/v1` model, deterministic identifiers, hashes,
manifests, crosswalk serialization, and retrieval projection; validator
diagnostics; generic JSON/XML/XHTML adapters; saved e-Gov national-law XML
conversion and the explicit `fetch` helper; OKF v0.2 export and validation for
verified e-Gov corpora; the `jlegal` CLI; and authored synthetic fixtures with
their offline regression tests.

## Out of scope for v0.1

LLM execution, audition, enrichment, and provider integration; OCR; municipal
ordinances; case law; legal interpretation or advice; Akoma Ntoso output;
index, search, and evaluation; and benchmark corpora. Adding any of these
requires a reviewed profile revision.

Index, search, and retrieval-quality benchmarking are out of scope because they
measure a search implementation rather than a conversion, not because they are
held back. They belong to a separate openly licensed project that takes OKF
bundles and this project's retrieval projection as its input.
