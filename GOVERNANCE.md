# Governance

## Current stage: Stage 0

The maintainer, `okf-works`, runs the project and holds specification, merge,
and release authority.

## Later stages

- **Stage 1**: Routine pull requests are reviewed and merged by maintainers,
  with the specification still decided by the project lead.
- **Stage 2**: Specification decisions are separated from any single
  implementer or downstream consumer, with a documented decision process.

Stage 1 and Stage 2 are not in effect. Advancing between stages is a recorded
decision, noted in CHANGELOG.md and in this file, not an automatic
consequence of activity.

## Decision-making

Profile changes are normative and require a documented revision of
[`docs/jlegal-okf-profile-0.1.0-draft.md`](docs/jlegal-okf-profile-0.1.0-draft.md).
Stability contracts — canonical IDs, hashes, the manifest schema, and
diagnostic codes — cannot be changed silently.

## Release authority

Only the maintainer creates tags and releases. Whether anything has been
tagged or released is recorded in [`CHANGELOG.md`](CHANGELOG.md), which is
the single place that assertion is made; it is not restated here.

## Contribution licensing

Contributions have been accepted under the Developer Certificate of Origin
(DCO), rather than a contributor license agreement, since the project began.
Contributors keep their copyright and license their contribution under
Apache-2.0.

Every commit must carry a `Signed-off-by` line, including a commit a
maintainer pushes to `main` directly. `tools/check_dco.py` enforces this on
the commits a pull request proposes, so a direct push rests on this rule
rather than on the check. This repository's own first two commits predate the
check and carry no sign-off; rewriting them would mean discarding the audited
single-commit history, so they sit outside the enforced range by design
rather than by exemption.

A CLA is not used now. It would only be reconsidered at a specific trigger:
relicensing, a need to consolidate rights under an agreement, or a case where
DCO alone cannot establish provenance. Reconsideration would pause acceptance
of new contributions rather than apply retroactively.
