# Security Policy

## Supported versions

The supported target is the current `main` branch, at profile version
`0.1.0-draft`. Whether any tag or release exists is recorded in
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

XML parsing takes two different paths, with two different postures.

The e-Gov path — the `egov_xml` adapter (`egov.py`), `jlegal validate-source`,
`jlegal compile --adapter egov_xml`, and `jlegal fetch` — parses with
`defusedxml` (`defusedxml.ElementTree`). It calls `ET.fromstring` with
`forbid_dtd=True`, `forbid_entities=True`, and `forbid_external=True`, which
reject DTDs, entity declarations, and external references, blocking the
entity-expansion bomb family (e.g. billion laughs, quadratic blowup) and
XXE. These flags do not bound memory or CPU consumption from a large but
otherwise well-formed document, and provide no decompression-bomb
protection. This is the project's primary and only profile-accepted input
path.

A 64 MiB admission cap on the input file applies only to the saved-file
path (`_read_admissible_xml`); `jlegal fetch` parses the API response body
before any such cap applies, since httpx has already decompressed and
returned the full body by the time parsing starts.

The generic `xml` and `html` adapters (`adapters.py`) parse with the Python
standard library's `xml.etree.ElementTree`, which is not hardened against
entity-expansion or quadratic-blowup denial-of-service input. Treat XML from
an untrusted source accordingly when using these adapters.

Reports of concrete exploitable behavior are in scope.

## Response expectations

This is a single-maintainer draft project. Acknowledgement is on a
best-effort basis, and no response-time guarantee is offered.
