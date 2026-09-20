"""Deterministic reports with explicit all-input and reached-step denominators."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .contracts import write_json

STEPS = ("admission", "compile", "canonical_verify", "export", "bundle_verify", "reproducibility")
STATES = ("pass", "fail", "blocked", "error")


def metrics(cases: list[dict]) -> dict:
    result = {}
    for step in STEPS:
        count = Counter(row["steps"][step]["state"] for row in cases)
        reached = len(cases) - count["blocked"]
        reasons = {state: dict(sorted(Counter(
            row["steps"][step]["code"] for row in cases
            if row["steps"][step]["state"] == state
        ).items())) for state in STATES}
        result[step] = {**{key: count[key] for key in STATES}, "all_units": len(cases),
                        "reached_units": reached,
                        "reason_counts": reasons,
                        "pass_rate_all": count["pass"] / len(cases) if cases else None,
                        "pass_rate_reached": count["pass"] / reached if reached else None}
    return result


def write_report(out_dir: Path, report: dict) -> None:
    write_json(out_dir / "measurement.json", report)
    lines = ["# Offline conversion measurement", "", "This is a measured sample, not a population or official-conformance claim.", "",
             "| Step | All | Reached | Pass | Fail | Blocked | Error |", "|---|---:|---:|---:|---:|---:|---:|"]
    for step, row in report["metrics"].items():
        lines.append(f"| {step} | " + " | ".join(str(row[key]) for key in ("all_units", "reached_units", *STATES)) + " |")
    lines += ["", "## Diagnostic counts", "",
              "| Step | State | Code | Units |", "|---|---|---|---:|"]
    for step, row in report["metrics"].items():
        for state, reasons in row["reason_counts"].items():
            for code, count in reasons.items():
                lines.append(f"| {step} | {state} | {code} | {count} |")
    lines += ["", "## Non-passing units", ""]
    for case in report["cases"]:
        for step, result in case["steps"].items():
            if result["state"] != "pass":
                lines.append(f"- `{case['unit_id']}` / {step}: {result['state']} ({result['code']})")
    (out_dir / "measurement.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
