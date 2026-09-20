# Offline conversion measurement

The shipped `python -m jlegal_okf.assurance` module inventories saved XML,
measures the reference implementation, and optionally records a separately
pinned third-party validator's judgment. It downloads nothing. It does not
establish a population acceptance rate or certify official OKF compliance.
The independent, artifact-only common suite is documented in
[conformance-suite.md](conformance-suite.md).

## Freeze the sample before admission

Keep source files, local inventories and transient artifacts outside this
repository. Select and record the sample before inventorying. The tools do
not supply a population frame or make convenience samples representative.

```bash
python -m jlegal_okf.assurance inventory --input-dir /data/saved-xml --out-dir /data/inventory
```

Every regular `.xml` file (case insensitive) is included recursively. Symlink
files, symlink directories, traversal and special filesystem entries are
refused. Byte lengths and SHA-256 are recorded before admission; malformed
XML, missing IDs and unsupported structures remain in the denominator.
IDs come from XML or an explicit `--law-id-map` JSON object mapping relative
filenames to IDs. Filenames are never used as IDs. The public ID field accepts
1–128 ASCII letters, numbers, dots, underscores and hyphens, starting with a
letter or number; other values become `INVALID_ID` without echoing them.
The map is a local assertion, not proof of an official ID assignment.

The output contains:

- `inventory.local.json` (`jlegal-survey-input/v1`): relative paths and the
  explicit mapping for local replay. Do not publish this file.
- `dataset.json` (`jlegal-survey-dataset/v1`): IDs, source digests, lengths,
  identity observations, occurrence counts and digest-based unit IDs.
  It contains neither source text nor input paths.

The unit is `(explicit law ID or null, source SHA-256)`. Repeated copies count
as occurrences; each deduplicated unit is measured once. Different bytes
under one ID remain different units. Before and after measurement the entire
inventory is recomputed: added, removed, modified or newly symlinked files
reject replay. Source locations may move with the same relative tree.

## Bind the actual implementation

Survey requires a `jlegal-implementation-lock/v1` JSON object:

```json
{
  "schema": "jlegal-implementation-lock/v1",
  "artifact_kind": "candidate-source",
  "package_version": "0.1.0.dev1",
  "package_tree_sha256": "<measured SHA-256>",
  "source_revision": null
}
```

`jlegal_okf.assurance.contracts.implementation_identity()` returns the actual
imported package version, package-tree digest, Python version and installed
`defusedxml`, `httpx`, and `PyYAML` versions. Prepare a candidate lock by
combining those fields with the schema, kind and revision above, outside the
repository. The digest is SHA-256 of the sorted compact UTF-8 JSON object
mapping every package-relative `.py` filename to its SHA-256, followed by one
newline. Bytecode is excluded. Optional `python_version` and `dependencies`
lock fields are checked against the runtime; actual versions are always
reported. Real locks must contain measured hashes, never placeholders.

For `artifact_kind: "installed-wheel"`, also provide `wheel_file` (a safe
relative path under the lock directory) and `wheel_sha256`. The runner checks
wheel bytes, every imported source file against the wheel, the installed
distribution version and import origin. A wheel alongside an unrelated source
import is refused. No wheel path is published. `source_revision` is null for
an uncommitted candidate or a claimed 40-digit commit ID. Reports mark revision
verification `unverified`: matching code bytes does not prove a claimed commit.
Retain separate verified source/build evidence for that claim. A measurement
lock is neither a release nor automatic pin promotion.

## Measure every stage and repeat all bytes

```bash
python -m jlegal_okf.assurance survey --inventory /data/inventory/inventory.local.json --input-root /data/saved-xml --implementation-lock /data/implementation.json --converted-at 2026-08-09T00:00:00Z --out-dir /data/measurement --timeout-seconds 120
```

Each unit runs sequentially in its own subprocess with a timeout covering
the whole unit. Stages are admission, compile, canonical manifest verification
with `verify_inputs=True`, export, bundle verification with
`verify_source=True`, and repetition. Repetition compiles and verifies again
and compares every canonical and bundle file, including manifests and
timestamp-bearing concepts. The fixed corpus ID is `survey-<unit_id>`;
the recipe uses the explicit unit ID mapping, requested UTC conversion time,
no acquisition receipt and no rights assertion. Retrieval URL/time and rights
remain unknown. The core CLI accepts `compile --converted-at` too; omitting
it preserves current conversion wall-clock behavior.

| State | Meaning |
|---|---|
| `pass` | The stage completed its check. |
| `fail` | A known input or contract check rejected the unit. |
| `blocked` | A failed prerequisite prevented reaching this stage. |
| `error` | Timeout, process/protocol failure or unexpected exception. |

Unexpected exceptions never count as unsupported structures. Only allowlisted
diagnostic codes are published; arbitrary tag names, exception messages and
paths are removed. Other expected core rejections use `CONTRACT_REJECTED`.
Temporary source-derived artifacts are removed after success, rejection and
timeout. A killed parent or power loss can still leave temporary files; keep
the temporary filesystem private and inspect it after interrupted runs.

`measurement.json` (`jlegal-measurement/v1`) and `measurement.md` retain all
non-passing units. Every stage reports all units and reached units, state
counts and both pass fractions; zero denominators yield JSON `null`.
Per-stage `reason_counts` groups deduplicated units by state and diagnostic
code, including blocked prerequisites and runtime errors. The Markdown report
includes the same diagnostic-count table; duplicate file occurrences do not
inflate these counts. Malformed child records become `WORKER_PROTOCOL` errors
on a known stage and do not remove a unit from the denominator.
An empty dataset has `passed: false`. Canonical JSON contains the safe
dataset, recipe, lock digest, verified code identity, actual runtime and
per-file output digests. Timing is isolated in `run.local.json`, permitting
byte-identical canonical reports for the same inputs, recipe and runtime.
Source hashes alone do not lock the whole OS or prove reproducibility across
arbitrary environments.

## Optional pinned external judgment

```bash
python -m jlegal_okf.assurance external --tool-root /tools/okf-conformance --tool-lock examples/conformance/external-tools.lock.json --bundle /data/bundle --out-dir /data/external
```

Prepare the external checkout and Node runtime separately; this command does
not clone, install or fetch. The checked-in lock pins
[`Sudhakaran88/okf-conformance`](https://github.com/Sudhakaran88/okf-conformance/tree/3e958ae965bf9673fc291859a44feb05a60a9748)
at `3e958ae965bf9673fc291859a44feb05a60a9748` and records SHA-256 of the validator
and companion graph source. This validator uses only Node built-ins and does
not load the companion file at this revision. The adapter checks checkout HEAD
and both code hashes, executes the fixed entrypoint with an argument vector,
`--json` and a timeout, and records Node's version. Malformed JSON and
inconsistent return codes are errors. Bundle tree hashes are compared before
and after every invocation, including failures. No fixes are applied.

The official specification is identified separately at
[`GoogleCloudPlatform/open-knowledge-format`, commit ad30107c31c06aec8a7d5636e0d1058118604e6f](https://github.com/GoogleCloudPlatform/open-knowledge-format/tree/ad30107c31c06aec8a7d5636e0d1058118604e6f).
This is an attribution reference, not executed code or proof that the
third-party tool fully implements the spec. `external.json` always reports
`official_compliance: "not-established"`, even when the tool passes. Counts
are grouped by fixed rule IDs; raw messages and filenames are omitted to
avoid exposing source text or paths. CI uses stubs only.

## Exit codes and evidence limits

All commands refuse existing output directories. Exit `0` means completed
success; `1` means a completed report with non-passing measurements/checks;
`2` means invalid request or mismatched evidence; `3` means a command-level
runtime failure. A per-unit runtime error retained in a completed survey
returns `1`. Parser usage errors also return `2`.

These tools and synthetic regressions establish no real-law coverage
percentage. Population measurement remains open until its selection frame,
fixed recipe, actual implementation identities and measured results have
reviewable evidence. See [known-limitations.md](known-limitations.md).
