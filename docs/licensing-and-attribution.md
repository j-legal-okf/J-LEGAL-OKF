# Licensing and Attribution

## Repository license

The repository is licensed under Apache-2.0, covering this project's own
code, documentation, and fixtures. See [`LICENSE`](../LICENSE) and
[`NOTICE`](../NOTICE). Some tracked files are not this project's own
Apache-2.0-licensed material; their terms are discussed below in
"Third-party documents carried in this repository" and in "e-Gov source
data rights".

Copyright 2026 J-LEGAL-OKF contributors.

## Specification documents and CC BY 4.0

CC BY 4.0 is not applied to the specification documents at this time. This is
a current decision, not an oversight: the rights holder, the covered scope,
existing attributions, and any third-party material have not been confirmed.
Applying CC BY 4.0 later would require confirming all of these first.

## Dependency licenses

None of the dependencies listed in this section have their source vendored
into this repository. Each one confirmed installed in the observed
environment below is used as a separately installed package;
`exceptiongroup`, which was not installed there, is addressed separately in
its own row. This repository therefore distributes no third-party code, and
Apache-2.0 remains compatible with all of them.

The resolved *runtime* dependency closure and the license values below were
observed on CPython 3.12.3 on 2026-08-04, against the package versions
listed. This is a point-in-time observation, not a standing guarantee: the
closure or a package's license can change on a future install or on a
different Python version.

### Runtime

| Package | Version | License |
| --- | --- | --- |
| defusedxml | 0.7.1 | Python Software Foundation License (PSFL) |
| httpx | 0.28.1 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |

### Transitive (via httpx)

| Package | Version | License |
| --- | --- | --- |
| httpcore | 1.0.9 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| idna | 3.18 | BSD-3-Clause |
| anyio | 4.14.2 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| typing_extensions | 4.16.0 | PSF-2.0 |

`exceptiongroup` is required by `anyio` only when `python_version < "3.11"`.
This project's `requires-python` is `>=3.10`, so `exceptiongroup` is part of
the supported-version closure, but it was not installed in the observed
CPython 3.12.3 environment above and so was not independently confirmed
there. Its license was read from PyPI package metadata on 2026-08-04
(classifier "License :: OSI Approved :: MIT License"):

| Package | Applies on | License |
| --- | --- | --- |
| exceptiongroup | Python 3.10 only (conditional dependency of anyio) | MIT (per PyPI metadata, not independently confirmed in an installed 3.10 environment) |

### Development-only

| Package | Version | License |
| --- | --- | --- |
| pytest | 9.1.1 | MIT |

This is `pytest`'s own package license only. `pytest`'s transitive
dependency closure (e.g. `iniconfig`, `packaging`, `pluggy`, `pygments`, and
platform- or version-conditional extras) is not enumerated here; only the
runtime closure above was resolved.

`certifi` is MPL-2.0; like the other runtime dependencies actually
installed, it is used as a separately installed package and is not vendored
here.

## Third-party documents carried in this repository

This section covers the tracked files that reproduce or adapt a third-party
document in whole. It is not an exhaustive inventory of every third-party
text this repository touches: [`LICENSE`](../LICENSE) is itself the
verbatim Apache License 2.0 text, and this document's own quotes and close
paraphrases of e-Gov-published material are covered separately in "e-Gov
source data rights" below, not here.

### `CODE_OF_CONDUCT.md`

This file is adapted from the Contributor Covenant, version 2.1, and its own
Attribution section credits the source and links
[contributor-covenant.org](https://www.contributor-covenant.org). What this
project has and has not confirmed about the terms governing that text:

- The version 2.1 source text itself, as published at
  [`EthicalSource/contributor_covenant`](https://github.com/EthicalSource/contributor_covenant)'s
  `release` branch (`content/version/2/1/code_of_conduct.md`), carries no
  license statement of its own; it carries only the attribution paragraph
  reproduced in this file's Attribution section.
- The steward states, in
  [`EthicalSource/contributor_covenant`](https://github.com/EthicalSource/contributor_covenant)'s
  own `CODE_OF_CONDUCT.md` and in that repository's version 3.0 text
  (`content/version/3/0/code_of_conduct.md`), the sentence: "Contributor
  Covenant is stewarded by the Organization for Ethical Source and licensed
  under CC BY-SA 4.0." That sentence does not appear in the version 2.1 text
  this file adapted.
- The `contributor_covenant` repository's own `LICENSE.md` is the Hippocratic
  License, version 3.0 (October 2021), which on its face covers that
  repository.
- The project's FAQ page did not state a license for the Code of Conduct
  text in the rendering this project retrieved. That page renders
  client-side, so this project may have missed a statement made there; this
  is not a claim that no such statement exists. This is a minor point beside
  the steward's own statement above.

This project has not confirmed which terms govern reuse of the version 2.1
text specifically, for the reasons given above. This project does not
resolve whether the steward's CC BY-SA 4.0 statement, or ShareAlike, extends
to or obliges that text, or what that would require of this project's own
licensing of `CODE_OF_CONDUCT.md`; that question is left open, not decided
here. This project therefore does not assert Apache-2.0 over
`CODE_OF_CONDUCT.md`, and does not assert CC BY 4.0 for it either — a
different license from the CC BY-SA 4.0 the steward states.
`CODE_OF_CONDUCT.md` carries the attribution the Contributor Covenant's own
text asks for. This file is not part of the built distribution (see
"Packaging" below).

### `CONTRIBUTING.md`

This file reproduces the Developer Certificate of Origin, version 1.1,
verbatim inside a fenced block. The reproduced text carries its own notice:
"Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
Everyone is permitted to copy and distribute verbatim copies of this license
document, but changing it is not allowed." This project reproduces that text
unmodified, exactly as that notice permits. This file is not part of the
built distribution (see "Packaging" below).

### Packaging

Neither `CODE_OF_CONDUCT.md` nor `CONTRIBUTING.md` is included in the built
sdist or wheel, verified on 2026-08-04 by building both artifacts: the sdist
contains only `LICENSE`, `NOTICE`, `PKG-INFO`, `README.md`, `pyproject.toml`,
`setup.cfg`, `src/`, and `tests/`; the wheel contains only the package
modules plus `dist-info`, including `licenses/LICENSE` and
`licenses/NOTICE`. `NOTICE`'s statement that the distribution contains no
third-party source code remains accurate; this carve-out is about what the
repository carries, not about what the distribution ships.

## Fixture and example provenance

The two tracked XML fixtures —
[`examples/synthetic_egov_law.xml`](../examples/synthetic_egov_law.xml) and
[`examples/fixtures/synthetic_egov_structure_matrix.xml`](../examples/fixtures/synthetic_egov_structure_matrix.xml)
— are authored by this project and entirely invented. Neither is downloaded
from e-Gov, neither may be used as a legal source, and neither carries
third-party rights. The structure-matrix fixture's fixed regression data is in
[`examples/fixtures/synthetic_egov_structure_matrix.golden.json`](../examples/fixtures/synthetic_egov_structure_matrix.golden.json).
The structure-matrix XML is checked against the current official e-Gov
Japanese-law XML Schema v3 during validation; the schema is a temporary
external validation input and is not redistributed here.

## Referenced external specifications

This project references the following as normative external documents:

- the e-Gov XML schema documentation;
- the e-Gov Law API v2; and
- the Open Knowledge Format v0.2 specification.

Referencing them does not incorporate their text into this repository, and
does not imply their endorsement of this project.

## e-Gov source data rights

This section is not legal advice. It separates what the primary sources say,
what this repository does as a conservative operating policy, and what a
downstream user must confirm independently.

### What the primary sources say

The e-Gov Developer terms of use state that copyright in content published on
`e-gov.go.jp` and its subdomains belongs to the Digital Agency unless stated
otherwise, and that absent a separate rights notice, the "Public Data License
(Version 1.0)" (PDL1.0) applies. PDL1.0 itself states it was established on
2024-07-05 (令和6年7月5日) and may change in the future.

Under PDL1.0's own text:

- Commercial use of PDL1.0-covered content is permitted.
- Using the content requires stating its source (出典).
- If the content is edited or processed, the fact that it was
  edited/processed and the identity of the party who did so must be stated
  **separately from** the source attribution. Presenting edited/processed
  content as if it were unmodified government output is stated to be
  prohibited.
- PDL1.0 declares itself compatible with CC BY 4.0 and states that the
  government permits use under CC BY for PDL1.0-covered content.
- PDL1.0 states it does not apply to: content not protected by copyright
  (e.g., numerical data, simple tables/graphs); organizational or
  business-specific symbol marks, logos, and character designs; and content
  for which a different rights notice is explicitly given with concrete,
  reasonable grounds.
- PDL1.0 disclaims responsibility for a user's use of the content (including
  edited/processed use), and states the content may be changed, moved, or
  deleted without notice.

Separately, Copyright Act (Act No. 48 of 1970) Article 13, item 1 places
"the Constitution and other laws and regulations" (憲法その他の法令) outside
the objects of the rights defined by that chapter of the Act — i.e., outside
what that chapter treats as copyrightable subject matter. This project has
not evaluated how this provision applies to any specific law text or e-Gov
XML content; that evaluation is left to whoever approves inclusion of
specific real-law material in this project, on a case-by-case basis, not
assumed here.

### Attribution for material quoted in this document

The "What the primary sources say" section above contains quotes and close
paraphrases of e-Gov-published content — the e-Gov Developer terms of use,
the Public Data License (Version 1.0) text, and the Copyright Act text. This
document states plainly that this material is e-Gov-derived, and attributes
it below.

PDL1.0 §1.1 has two parts, and each carries the same override: where a
重要情報 document supplies its own example, §1.1 directs the reader to that
example instead of §1.1's generic one — for the source attribution
(出典記載例) and, independently, for the processing disclosure
(編集・加工記載例). The e-Gov Developer site publishes such a 重要情報
document with both kinds of example, so both of this project's disclosures
for that source follow e-Gov's forms rather than the generic ones.

Source attribution, in the form prescribed by e-Gov:

> 出典：「利用規約」（e-Gov Developer）
> （https://developer.e-gov.go.jp/contents/terms）（2026年8月4日に利用）

Processing disclosure, in the form prescribed by e-Gov, stated separately
from the attribution above as §1.1 requires:

> 「利用規約」（e-Gov Developer）
> （https://developer.e-gov.go.jp/contents/terms）をもとに
> J-LEGAL-OKF contributors 作成

The PDL1.0 text itself is published on `digital.go.jp`, which is not an
`e-gov.go.jp` subdomain, so e-Gov's 重要情報 forms do not govern it; it is
attributed in PDL1.0's generic §1.1 forms. This project did not separately
review `digital.go.jp`'s own site terms as part of this observation. PDL1.0's
generic 出典 form ends with 、PDL1.0（規約原文ページのURL）; here the cited
page and that URL are the same page, so it appears once:

> 出典：「公共データ利用規約（第1.0版）」（デジタル庁）
> （https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）
> （2026年8月4日に利用）

> 「公共データ利用規約（第1.0版）」（デジタル庁）
> （https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）
> をもとに J-LEGAL-OKF contributors 作成

The Copyright Act text was retrieved from the e-Gov 法令API on
`laws.e-gov.go.jp`. The e-Gov Developer terms define their own scope as
「e-gov.go.jp及びそのサブドメインのWebサイト」, which by that wording includes
this host, and they invoke the 重要情報 for content within that scope. On that
reading the e-Gov form below is the applicable one. That is a reading of the
scope wording, not a separately verified fact: this project observed the
重要情報 only as reproduced inline on the Developer terms page, and did not
retrieve a 重要情報 published for `laws.e-gov.go.jp` itself.

> 出典：「著作権法（昭和四十五年法律第四十八号）」（e-Gov 法令検索）
> （https://laws.e-gov.go.jp/api/1/lawdata/345AC0000000048）
> （2026年8月4日に利用）

In plain terms: this material was quoted, summarized, and paraphrased by
J-LEGAL-OKF contributors for the "What the primary sources say" section and
the guidance that follows it. This project treats summarizing and
paraphrasing as 編集・加工 and as a form of 翻案 (adaptation), which PDL1.0 §1
names among the permitted uses; that classification is this project's own,
adopted because it is the more cautious reading. This processed material is
**not** presented as unmodified e-Gov or Digital Agency output: it is this
project's condensed restatement of the primary sources, and a reader should
consult the primary sources directly (linked above) rather than treat this
document as their authoritative text.

This attribution records the date the sources were observed rather than
reproducing per-line references into them. The URLs above are what a reader
needs to consult the primary sources directly, and those sources — not this
document — are authoritative for their own text.

### This repository's data content

Separately from the attribution above: this repository's tracked files
carry no e-Gov *law data* and no e-Gov-derived *corpus content*. Its two XML
files are the authored synthetic fixtures
[`examples/synthetic_egov_law.xml`](../examples/synthetic_egov_law.xml) and
[`examples/fixtures/synthetic_egov_structure_matrix.xml`](../examples/fixtures/synthetic_egov_structure_matrix.xml)
(see "Fixture and example provenance" above); neither is e-Gov output. This is a fact about what data this repository
distributes — confirmed by enumerating every tracked `.xml` file — not a
basis for withholding the attribution above, which applies regardless of
this fact and is carried in full.

### Guidance for downstream users running this tool against real e-Gov data

`jlegal_okf` can fetch and compile real e-Gov law XML (see the "e-Gov
acquisition provenance" section of the [README](../README.md)); that output
is not part of this repository and is the downstream user's own
responsibility to license correctly. If a user distributes such output, or
material derived from it:

- Carry a source attribution (出典). PDL1.0 §1.1 gives a default form, but
  also provides that where a "重要情報" (important information) document
  supplies its own 出典記載例 for the content, that example replaces the
  default. This is not hypothetical: the e-Gov Developer site publishes such
  a document, and the attribution above for its terms of use follows e-Gov's
  form rather than the default. Check whether one covers the specific content
  you are using; this project has surveyed only the pages it cites above.
  Note that `jlegal fetch` retrieves law data from `laws.e-gov.go.jp`. The
  Developer terms scope themselves to 「e-gov.go.jp及びそのサブドメイン」, which
  on its wording covers that host, so the same 重要情報 examples are read as
  applying. What this project did not verify is whether `laws.e-gov.go.jp`
  publishes a 重要情報 of its own with different examples; its terms page
  renders client-side and its text was not retrieved.
- Treat this project's canonicalisation (`jori-corpus/v1` compilation) and
  its OKF v0.2 projection as "editing/processing" (編集・加工) in PDL1.0's
  sense, and separately state that the content was processed and by which
  party, distinct from the source attribution, per PDL1.0 §1.1. The 重要情報
  override applies here too: §1.1 directs you to a 重要情報 document's
  編集・加工記載例 in place of the generic one on the same terms as for the
  出典記載例, so check for both examples, not only the source one.
- Confirm, for the specific e-Gov page or API response being used, whether a
  separate rights notice (権利表記) overrides PDL1.0 for that content —
  this repository has not surveyed e-Gov pages beyond the terms-of-use and
  PDL1.0 text itself, and cannot confirm this on a user's behalf.
- Do not present processed output as if it were unmodified government
  content; PDL1.0 states this is prohibited.

None of the above is a substitute for the user's own review of PDL1.0, the
e-Gov Developer terms of use, and the Copyright Act as they apply to the
specific content being used.

### Why a receipt's `rights` is null, and where licensing facts go instead

Every e-Gov acquisition receipt carries `rights: null`, and `jlegal compile`
rejects a non-null `rights` value in a receipt (see the "Provenance,
normalization, and validation policy" section of
[the v0.1 profile](jlegal-okf-profile-0.1.0-draft.md)). e-Gov API delivery is
not treated as a rights assertion in either direction. This keeps the
provenance model from asserting a license status this project has not
verified for the specific content fetched.

Licensing facts belong instead in the separate rights area described in the
["Rights metadata" section](jlegal-okf-profile-0.1.0-draft.md#rights-metadata)
of the profile: `source_license`, `bundle_license`,
`redistribution_allowed`, and `commercial_use_allowed`, recorded by
`jlegal compile --rights <file.json>`. That area is written only when a caller
asserts it, and what it records is the caller's claim about the specific
content they compiled — this project neither resolves the licence identifier
nor derives the permissions from it. Compiling without `--rights` records no
rights area, which is what this repository's own examples do; deciding what
to assert for a given corpus is the user's own determination under the
sections above.

### e-Gov content is not permanent

e-Gov content, per its own terms, may be changed, moved, or deleted without
notice, and the Digital Agency disclaims responsibility for a user's use of
it. This project carries no guarantee about the continued availability or
content of any e-Gov URL it fetches from.

## No official status

This is an unofficial project. It is not an official e-Gov, Japanese
Government, or Open Knowledge Format endorsement, and it does not carry any
warranty of legal accuracy or fitness for legal use.
