# Contributing to J-LEGAL-OKF

## Scope

This repository holds the audited public core of J-LEGAL-OKF: the
`jlegal_okf` package, the `jlegal` CLI, the public specification, the
synthetic fixtures, and their regression tests. Changes to the public-core
contract are made here first.

## How to submit a change

1. Open an issue first for anything that touches a stability contract (see
   below) or the profile. Small fixes can go straight to a pull request.
2. Fork the repository and branch from `main`.
3. Make the change, add or update a regression test, and run the verification
   commands below.
4. Commit with `-s` so every commit carries a `Signed-off-by` line.
5. Open a pull request describing what changed and how you verified it.

## What must never be contributed

- Real-law snapshots, or any real acquired data used as a fixture.
- Secrets, credentials, tokens, or keys.
- Personal data.
- Non-public material of any kind, from this project or any other.
- Absolute local filesystem paths.
- Anything you do not have the right to submit.

## Fixtures must be authored and entirely invented

A test fixture must be written from scratch and entirely invented, not copied
or derived from a real or external source. A fixture that reproduces an
external source carries that source's rights and provenance questions into
this repository, which this project is not positioned to resolve. See
`examples/synthetic_egov_law.xml` for the existing pattern.

## Contract-sensitive changes

Canonical IDs, hashes, the manifest schema, the `conversion` record, and
diagnostic codes are stability contracts. Changing them changes the
verification result of bundles that already exist, so such changes need
explicit review and a profile revision rather than a routine pull request.

Determinism must be preserved: the same input must produce byte-identical
canonical output.

## Development setup and verification

```bash
python -m pip install -e '.[dev]'
python -m pytest
python tools/check_boundary.py
jlegal --help
```

CI runs `tools/check_boundary.py` on every push and pull request; it scans the
tracked tree for private path markers, local absolute paths, credential
patterns, and e-mail addresses other than the project's own. CI also runs
`tools/check_dco.py` over a pull request's own commits, so a missing
`Signed-off-by` line fails the check rather than being noticed by hand. Run
both locally before opening a pull request.

The CLI currently exposes these subcommands: `validate-source`, `compile`,
`validate`, `fetch`, `export-okf`, and `validate-okf`. Run
`jlegal <subcommand> --help` for their arguments.

## Developer Certificate of Origin

Every contribution must be signed off under the Developer Certificate of
Origin (DCO) 1.1. Add a `Signed-off-by` line to each commit by committing
with `-s`:

```bash
git commit -s
```

By signing off, you certify the text below.

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

The sign-off is required on every commit, not only on commits that arrive
through a pull request: a maintainer pushing to `main` directly signs off the
same way. `tools/check_dco.py` runs over a pull request's own commits, so a
direct push is held to this rule rather than to the check.

No CLA is required at this time.

## AI-assisted contributions

Using an AI tool to help prepare a contribution is allowed, but it does not
transfer or reduce your responsibility for it. Before submitting, you must:

- understand the change you are submitting;
- test it;
- confirm you have the right to submit it;
- ensure it contains no unattributed copying; and
- ensure it contains no secrets or non-public material.

Do not paste non-public material into external AI services while preparing a
contribution.

## Further reading

- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- [`SECURITY.md`](SECURITY.md)
- [`GOVERNANCE.md`](GOVERNANCE.md)
- [`ARCHITECTURE_BOUNDARY.md`](ARCHITECTURE_BOUNDARY.md)
