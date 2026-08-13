# J-LEGAL-OKF

`J-LEGAL-OKF` is a draft public profile and reference core for reproducible,
source-preserving Japanese national-law knowledge bundles. Its Python package
is `jlegal_okf`, its CLI is `jlegal`, and its reference implementation is
`JORI Engine`.

## 日本語概要

J-LEGAL-OKFは、日本の国法令を対象に、原典を保持しながら再現可能な知識バンドルを作るためのドラフト公開プロファイルと参照コアです。非公式のプロジェクトであり、e-Gov等の公的承認を示すものではなく、法的助言・法令解釈・正確性の保証を提供しません。

## 採用している規範とデータ形式

v0.1はe-Govの法令標準XMLを入力とし、`jori-corpus/v1`を正準形式、`jori-manifest/v5`を取得・変換証跡を含むmanifest、公式Open Knowledge Format v0.2に形を合わせたbundle（OKF v0.2-shaped）を出力投影として採用します。同仕様への適合性試験は行っていません。原典忠実性、構造保持、出典追跡可能性、決定論的変換、derived knowledgeの分離を優先し、未レビューの構造を推測・平坦化しないfail-closedの方針です。詳細は[規範プロファイル](docs/jlegal-okf-profile-0.1.0-draft.md)を参照してください。既知の制限とfail-closed挙動の一覧は[`docs/known-limitations.md`](docs/known-limitations.md)にまとめています。

## Akoma Ntosoとの関係

v0.1はAkoma Ntoso / LegalDocML準拠・互換を主張しません。AKN XML、FRBR、AKN Naming Convention、`eId`、`wId`を実装していないため、これらはv0.1の対象外です。法令構造や出典を扱うという概念上の類似は、Akoma Ntosoへの準拠を意味しません。

Its current GitHub repository identity is
[`j-legal-okf/J-LEGAL-OKF`](https://github.com/j-legal-okf/J-LEGAL-OKF).
The local checkout directory remains `j-legal-okf`.

This repository is the canonical home for future changes to the audited
J-LEGAL-OKF public core: the `jlegal_okf` package, `jlegal` CLI, public
specifications, synthetic fixtures, and their regression tests. Private
research repositories consume this core as a dependency; they do not carry
the authoritative public-core implementation forward.

The normative v0.1 preservation policy is in
[the public profile](docs/jlegal-okf-profile-0.1.0-draft.md). In brief,
source fidelity, structural preservation, source traceability, deterministic
conversion, and separation of derived knowledge take precedence over generated
readability. v0.1 accepts only e-Gov national-law XML; it keeps source,
canonical, and derived concerns separate and fails closed rather than guessing
or flattening unsupported structure. Current UUID identifiers, stable
diagnostics, and the OKF v0.2-shaped export projection are retained; the
profile does not adopt example IDs, diagnostics, or bundle layouts from
external review material.

This initial slice includes canonical corpus IDs and hashes, deterministic
compilation/manifest/projection processing, validation diagnostics, generic
JSON/XML/XHTML adapters, saved e-Gov XML conversion, an explicit e-Gov fetch
helper, and OKF v0.2-shaped export/validation. It is not a complete release.
Its v0.1 public scope excludes LLM execution and audition, municipal
ordinances, OCR, case law, and legal interpretation.
Generic adapters are implementation utilities; they do not expand the v0.1
profile's accepted source scope beyond e-Gov national-law XML. See
[`docs/known-limitations.md`](docs/known-limitations.md) for the full known
limitations, fail-closed behaviors, and the scope of LLM audition as a
Private overlay responsibility.

The intended transfer boundary and exclusions are recorded in
[the scope inventory](docs/oss-release/scope-inventory.md).

This is an unofficial, non-guaranteed project and must not be treated as an
official service, legal advice, or a warranty of legal accuracy.

For local development, run `python -m pip install -e '.[dev]'`, then
`jlegal --help`.

## Project documents

- [`ARCHITECTURE_BOUNDARY.md`](ARCHITECTURE_BOUNDARY.md) — the public/private
  boundary, by principle.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — scope, fixture rules, and how to
  submit a change.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — community standards and
  reporting.
- [`SECURITY.md`](SECURITY.md) — vulnerability reporting and scope.
- [`GOVERNANCE.md`](GOVERNANCE.md) — decision-making and release authority.
- [`CHANGELOG.md`](CHANGELOG.md) — notable changes, Keep a Changelog format.
- [`docs/licensing-and-attribution.md`](docs/licensing-and-attribution.md) —
  license, dependency licenses, and fixture provenance.
- [`docs/jlegal-okf-profile-0.1.0-draft.md`](docs/jlegal-okf-profile-0.1.0-draft.md)
  — the normative v0.1 profile.
- [`docs/known-limitations.md`](docs/known-limitations.md) — consolidated
  known limitations and fail-closed behavior.
- [`docs/validator-layers.md`](docs/validator-layers.md) — the validator's
  four layers mapped to every diagnostic code.
- [`docs/normalization-rules.md`](docs/normalization-rules.md) —
  identifier/locator normalization rule catalog.
- [`docs/v0.1-review-answers.md`](docs/v0.1-review-answers.md) — answers to
  the v0.1 implementation review's final review questions, with code/spec/test
  citations.
- [`LICENSE`](LICENSE) — the Apache-2.0 license text.
- [`NOTICE`](NOTICE) — the Apache-2.0 notice.

The maintainer is `okf-works`. Security reports go through the process in
[`SECURITY.md`](SECURITY.md) rather than a public issue.

## e-Gov acquisition provenance

Keep live XML, its receipt, and generated outputs outside this repository. The
receipt is the only accepted source of an API URL and retrieval time; saved XML
without a receipt keeps both fields `null` and compilation never reads file
mtime.

```bash
work_dir="$(mktemp -d)"
jlegal fetch 321CONSTITUTION --output "$work_dir/law.xml" --receipt-out "$work_dir/acquisition.json"
jlegal validate-source "$work_dir/law.xml" --acquisition "$work_dir/acquisition.json" --report "$work_dir/admission.json"
jlegal compile "$work_dir/law.xml" --adapter egov_xml --acquisition "$work_dir/acquisition.json" --corpus-id 321CONSTITUTION --out-dir "$work_dir/corpus"
```

The receipt carries `rights: null`; do not infer a rights claim from e-Gov API
delivery. To record licensing facts about a corpus and the bundle exported
from it, assert them explicitly with `jlegal compile --rights <file.json>`
(`source_license`, `bundle_license`, `redistribution_allowed`,
`commercial_use_allowed`) — see
[docs/jlegal-okf-profile-0.1.0-draft.md](docs/jlegal-okf-profile-0.1.0-draft.md#rights-metadata).
Compiling without it records no rights area at all.

## Offline synthetic example

[`examples/synthetic_egov_law.xml`](examples/synthetic_egov_law.xml)
is entirely invented, is not downloaded from e-Gov, and must not be used as a
legal source. It exercises the saved-XML path without a network request. From
the repository root of an installed checkout, run the following; only the
outputs are placed in a new temporary directory:

```bash
work_dir="$(mktemp -d)"
jlegal validate-source examples/synthetic_egov_law.xml --report "$work_dir/admission.json"
jlegal compile examples/synthetic_egov_law.xml --adapter egov_xml --corpus-id synthetic-egov-law --out-dir "$work_dir/corpus"
jlegal validate --corpus "$work_dir/corpus/corpus.jsonl" --manifest "$work_dir/corpus/manifest.json" --verify-inputs --source examples/synthetic_egov_law.xml
jlegal export-okf --corpus "$work_dir/corpus/corpus.jsonl" --manifest "$work_dir/corpus/manifest.json" --out-dir "$work_dir/bundle" --source examples/synthetic_egov_law.xml
jlegal validate-okf "$work_dir/bundle"
```

Each command emits JSON. The generated canonical corpus and bundle retain the
fixture's source hash; remove the temporary directory when finished.

## License

Apache-2.0. Copyright 2026 J-LEGAL-OKF contributors. See
[`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and
[`docs/licensing-and-attribution.md`](docs/licensing-and-attribution.md).
