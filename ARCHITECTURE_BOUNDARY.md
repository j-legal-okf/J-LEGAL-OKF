# Architecture Boundary

## Why the boundary exists

The public core must be independently verifiable without access to anything
private, and private material must not be reconstructible from what is
published. Everything else in this project's structure follows from those two
requirements.

## Principles that place something in the public core

Something belongs in the public core when it satisfies all of the following:

- **Deterministic and reproducible from published inputs alone.** Given the
  same input, it produces the same output, and that input is itself public or
  reproducible without private access.
- **Verifiable by a third party with no privileged access.** Anyone can check
  its correctness using only what is published: the code, the specification,
  and the fixtures.
- **A stability contract others can build on.** Canonical IDs, hashes,
  manifest schemas, and diagnostic codes are contracts; changing them changes
  the verification result of bundles that already exist, so they are held to
  the same discipline as a public interface.
- **Demonstrable with authored synthetic fixtures.** Its correctness can be
  shown end to end using fixtures that are entirely invented by the project,
  with no dependence on acquired or licensed material.

## Principles that keep something private

Something stays private when any of the following applies:

- **It depends on acquired or licensed data whose redistribution is not
  established.** If the right to publish a piece of data has not been
  confirmed, it does not move to the public core.
- **It encodes a specific consumer's configuration or vocabulary.** Mappings,
  overlays, or terms tailored to one downstream consumer are not part of a
  general-purpose public core.
- **It is non-deterministic or model-dependent output that cannot serve as
  evidence.** Generated or model-derived content does not have the
  reproducibility a stability contract requires.
- **It is operational, or contains material the project has no right to
  publish.** Internal reports, logs, evaluation data drawn from acquired or
  customer corpora, scored model output, and anything of unconfirmed
  provenance stay out.

An evaluation is not private by virtue of being an evaluation. What keeps an
evaluation private is its inputs: real or licensed corpora, customer material,
or model output that cannot be reproduced. An evaluation built from authored
synthetic fixtures with fixed expected results is deterministic and verifiable
by a third party, so it is judged by the public-core principles above like any
other artifact.

## What follows from these principles

Generated or model-derived knowledge is never source or canonical evidence,
in the public core or anywhere that consumes it. A private downstream
repository consumes this core as a dependency; it never becomes an
alternative source of truth for the public core itself.

## Direction of flow

Audited content moves from private to public only as newly authored public
commits. The public core never depends on private code, private paths, or
private history. No private repository's git history or objects are
transferred into this repository.

## Naming

`J-LEGAL-OKF`, `j-legal-okf`, `jlegal`, and `jlegal_okf` are the project's
specification, repository, CLI, and package identifiers. `JORI Engine` is an
implementation and manifest identifier, retained for determinism of the
`conversion` record recorded in generated manifests. It is not a brand or
trademark claim.

## Applying this boundary

This document is a rule for judging new material, not a list to check off
against existing feature names. Anything that does not clearly satisfy the
public-core principles above stays out until it is reviewed against them.
