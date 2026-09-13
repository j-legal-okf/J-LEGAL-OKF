#!/usr/bin/env python3
"""Decide whether every job the `ci-passed` aggregate depends on allows a merge.

`ci-passed` depends on every other job so that branch protection can
require one name that does not change when a job is renamed or the
matrix changes.  A job whose dependency fails is skipped, and GitHub
counts a skipped required check as passing, so `ci-passed` carries
`if: always()` and this script decides the result.

`dco` is the one job this script allows to be `skipped`: it only runs on a
pull_request (see the `dco` job's `if` in `.github/workflows/ci.yml`), so a
push or workflow_dispatch run reports it `skipped` by design, not by
failure.  Every other job, and `dco` on any other event, must report
`success`.

The workflow step passes the `needs` context and the event name
through the environment (`NEEDS` as JSON, `EVENT_NAME` as plain
text) instead of interpolating them into the shell script, so their
contents reach this script as data and are never parsed by the
shell.
"""

from __future__ import annotations

import json
import os
import sys

# `dco` runs only on `pull_request` (see ci.yml), so it is reported
# `skipped` on every other trigger this workflow listens for. Those are the
# only events on which a `skipped` dco is accepted rather than treated as a
# missing result.
ALLOWED_DCO_SKIP_EVENTS: frozenset[str] = frozenset({"push", "workflow_dispatch"})


def evaluate(needs: object, event_name: str) -> tuple[list[str], list[str]]:
    """Check one decoded `needs` context against the merge rule.

    Returns `(issues, notes)`. `notes` records what was accepted, so the
    step's own log is the evidence of what actually ran -- not just that
    this script exited zero.
    """

    if not isinstance(needs, dict) or not needs:
        return ["NEEDS must decode to a non-empty JSON object"], []

    issues: list[str] = []
    notes: list[str] = []
    for name, value in sorted(needs.items()):
        if not isinstance(value, dict):
            issues.append(f"{name}: needs entry is not a JSON object")
            continue
        result = value.get("result")
        if not isinstance(result, str):
            issues.append(f"{name}: needs entry has no string 'result'")
            continue
        if result == "success":
            notes.append(f"{name}: {result}")
            continue
        if name == "dco" and result == "skipped" and event_name in ALLOWED_DCO_SKIP_EVENTS:
            notes.append(f"{name}: {result} (accepted on {event_name})")
            continue
        issues.append(f"{name}: result is {result!r}")

    return issues, notes


def main(argv: list[str] | None = None) -> int:
    raw_needs = os.environ.get("NEEDS", "")
    event_name = os.environ.get("EVENT_NAME", "")

    issues: list[str] = []
    if not raw_needs:
        issues.append(
            "NEEDS is not set (or empty); the step must set env.NEEDS to ${{ toJSON(needs) }}"
        )
    if not event_name:
        issues.append(
            "EVENT_NAME is not set (or empty); the step must set env.EVENT_NAME to "
            "${{ github.event_name }}"
        )

    notes: list[str] = []
    if not issues:
        try:
            needs = json.loads(raw_needs)
        except json.JSONDecodeError as exc:
            issues.append(f"NEEDS is not valid JSON: {exc}")
        else:
            issues, notes = evaluate(needs, event_name)

    for note in notes:
        print(f"[ci-needs] {note}")
    if issues:
        print("ci-needs check failed", file=sys.stderr)
        for issue in sorted(dict.fromkeys(issues)):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("ci-needs check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
