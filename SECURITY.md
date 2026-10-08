# Security Policy

## Supported versions

The supported target is the current `main` branch, at profile version
`0.3.0-draft`. Whether any tag or release exists is recorded in
[`CHANGELOG.md`](CHANGELOG.md); a tagged release does not, by itself,
narrow this scope away from `main`.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on
[`j-legal-okf/J-LEGAL-OKF`](https://github.com/j-legal-okf/J-LEGAL-OKF)
(Security tab → Report a vulnerability). This reporting channel is enabled.

Please do not open a public issue for a suspected vulnerability.

No email address is published for security reports.

Please do not include secrets, personal data, or real non-public documents in
a report. A synthetic reproduction is preferred, and is usually sufficient
given this project's scope.

## Scope

In scope: the `jlegal_okf` package and the `jlegal` CLI, including anything
that lets crafted input:

- escape the intended output directory;
- cause unbounded resource use;
- execute code during parsing; or
- cause the validator to report a corrupted or tampered bundle as valid.

Out of scope:

- the accuracy or legal meaning of any law text;
- the availability or behavior of the e-Gov service; and
- issues in downstream private systems that consume this core.

### Known parser posture

See [`docs/known-limitations.md`, "Input parsing
posture"](docs/known-limitations.md#2-input-parsing-posture) for this same
material consolidated alongside the project's other known limitations.

The e-Gov admission, adapter, sniffing, inventory identity and fetch parsing
paths and the generic `xml`/`html` adapters share `input_limits.py`. Its
`DefusedXMLParser` sets `forbid_dtd=True`, `forbid_entities=True`, and
`forbid_external=True`. DTDs, entity declarations and external references are
forbidden. The `html` adapter still requires well-formed XHTML. Only the
e-Gov national-law XML path is profile-accepted; generic adapters remain
implementation utilities.

Local XML/XHTML readers accept only regular files, including symlinks whose
targets are regular files. They inspect the opened descriptor with `fstat`
and read at most 64 MiB + 1 byte from that same descriptor, rejecting input
over 64 MiB. POSIX opens are nonblocking so a FIFO can be rejected without
waiting for a writer. The parser also checks the byte cap, limits depth to
128 (root depth 1) and total elements to 250,000, and checks both tree limits
before constructing each next element. Exact limits are accepted; excess
depth/elements fail with `INPUT_XML_DEPTH_LIMIT` / `INPUT_XML_ELEMENT_LIMIT`.
These are implementation resource boundaries, not official XML conformance
judgments. No CLI option disables them.

`jlegal fetch` already streams the HTTP response and rejects accumulated
decoded bytes over 64 MiB with `EGOV_FETCH_TOO_LARGE`, before XML parsing or
output writing. A declared `Content-Length` above the cap permits early
rejection but is not required for enforcement. Fetch then applies the shared
parser; rejected successful-response XML retains `EGOV_FETCH_XML`.
HTTP decompression and chunk allocation occur before the accumulated-byte
check, so this is not a decompression-bomb or hard memory guarantee.

Structured compile inputs share the same regular-file reader. Source JSON is
limited to 64 MiB, container depth 128 and 250,000 structural tokens. Mapping
YAML/JSON and acquisition/rights JSON options have a 1 MiB input cap, depth 32
and 10,000 tokens. A container start, object key or scalar value counts once;
the root container has depth 1 and a root scalar depth 0. Limits are inclusive
and apply to unused fields too. JSON is scanned before `json.loads`; YAML
SafeLoader events are scanned before `safe_load`. Every YAML alias is refused
as `INPUT_YAML_ALIAS_FORBIDDEN`, including acyclic aliases; anchors without
references remain usable. Source JSON retains UTF-8/16/32 and BOM detection;
CLI option files remain UTF-8.

API mapping/acquisition/rights and e-Gov adaptation metadata are checked before
comparison or canonical serialization. They accept exact dict/list and JSON
scalar types, string keys, finite floats and integers of at most 4096 bits.
Source JSON uses the same integer limit; decimal strings above 1234 digits
(excluding the sign) are refused before integer conversion, then bit length is
checked. `NaN`, infinities and JSON float overflow are `INPUT_NONFINITE`.
Cycles, custom types and lone Unicode surrogates are refused. Shared references
are counted at every occurrence. Options also have a 1 MiB canonical UTF-8
byte cap, checked incrementally after a nonrecursive graph walk, character
budget and integer checks. Mapping-file hash rereads use the input byte cap;
their provenance meaning is unchanged.

Resource and type failures expose stable `INPUT_*` diagnostics, without input
values or parser exception text. In particular, depth/token failures use
`INPUT_JSON_*_LIMIT`, `INPUT_YAML_*_LIMIT` or `INPUT_OPTION_*_LIMIT`; graph
cycles/types/integers/bytes use `INPUT_OPTION_CYCLE`, `INPUT_OPTION_TYPE`,
`INPUT_OPTION_INTEGER_LIMIT`, `INPUT_OPTION_BYTES_LIMIT`. Syntax failures use
`INPUT_JSON_PARSE` / `INPUT_YAML_PARSE`, and invalid Unicode uses
`INPUT_ENCODING`. Missing acquisition/rights files and ordinary JSON syntax
errors retain their existing `*_FILE_REQUIRED` / `*_JSON` diagnostics.

These implementation boundaries do not provide process isolation, hard CPU,
address-space or wall-clock limits, or a transaction covering every generated
output. Parser/encoder internals can allocate temporary objects; caller-owned
API graphs already occupy memory. Artifact readers in general are outside
these compile-input limits. Process resource isolation and output completion
on failure remain separate work.

Reports of concrete exploitable behavior are in scope.

## Response expectations

This is a single-maintainer draft project. Acknowledgement is on a
best-effort basis, and no response-time guarantee is offered.
