"""Entry points for offline inventory, measurement and independent checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .contracts import AssuranceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m jlegal_okf.assurance")
    sub = result.add_subparsers(dest="command", required=True)
    item = sub.add_parser("inventory")
    item.add_argument("--input-dir", type=Path, required=True)
    item.add_argument("--law-id-map", type=Path)
    item.add_argument("--out-dir", type=Path, required=True)
    item = sub.add_parser("survey")
    item.add_argument("--inventory", type=Path, required=True)
    item.add_argument("--input-root", type=Path, required=True)
    item.add_argument("--implementation-lock", type=Path, required=True)
    item.add_argument("--converted-at", required=True)
    item.add_argument("--out-dir", type=Path, required=True)
    item.add_argument("--timeout-seconds", type=float, default=120)
    item = sub.add_parser("external")
    for name in ("tool-root", "tool-lock", "bundle", "out-dir"):
        item.add_argument("--" + name, type=Path, required=True)
    item.add_argument("--timeout-seconds", type=float, default=120)
    item = sub.add_parser("check")
    for name in ("catalog", "submission", "out-dir"):
        item.add_argument("--" + name, type=Path, required=True)
    item = sub.add_parser("_worker", help=argparse.SUPPRESS)
    for name in ("source", "work-dir", "result-file"):
        item.add_argument("--" + name, type=Path, required=True)
    for name in ("converted-at", "corpus-id", "expected-tree-sha256"):
        item.add_argument("--" + name, required=True)
    item.add_argument("--law-id")
    return result


def main(argv: list[str] | None = None) -> int:
    args = vars(parser().parse_args(argv))
    command = args.pop("command")
    try:
        if command == "inventory":
            from .inventory import inventory
            report = inventory(**args)
        elif command == "survey":
            from .survey import survey
            report = survey(**args)
        elif command == "external":
            from .external import external
            report = external(**args)
        elif command == "check":
            from .conformance import check_submission
            report = check_submission(**args)
        else:
            from .survey import run_worker
            run_worker(**args)
            return 0
    except AssuranceError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except ValueError:
        print('{"error":"INVALID_REQUEST"}', file=sys.stderr)
        return 2
    except Exception:
        print('{"error":"RUNTIME_FAILURE"}', file=sys.stderr)
        return 3
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
