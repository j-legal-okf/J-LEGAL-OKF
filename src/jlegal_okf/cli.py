"""Command line interface for the included J-LEGAL-OKF public core."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import yaml

from . import __version__
from .egov import admit_egov_xml, egov_xml_adapter, fetch_egov_xml, write_acquisition_receipt
from .errors import AdapterError, JLegalError, ValidationError
from .legal_okf import LegalOKFError, export_okf, validate_okf
from .pipeline import JLEGAL_PROFILE, _egov_acquisition, compile_corpus, read_crosswalk, read_jsonl, verify_manifest
from .validation import validate_corpus

# Two version systems, surfaced together because the moment a user reaches
# for --version is exactly when the distinction between them matters most:
# the Python package version (this distribution's build) and the normative
# profile version (the on-wire contract it implements). See README.md
# "Versioning" for the full set of version systems this project tracks.
_VERSION_TEXT = f"jlegal-okf {__version__} (profile {JLEGAL_PROFILE})"


def _mapping(value: str | None):
    if value is None:
        return None, None
    path = Path(value)
    return (yaml.safe_load(path.read_text(encoding="utf-8")), path) if path.exists() else (yaml.safe_load(value), None)


def _acquisition(value: str | None):
    if value is None:
        return None
    path = Path(value)
    if not path.is_file():
        raise ValidationError("ACQUISITION_FILE_REQUIRED")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("ACQUISITION_JSON") from exc


def _rights(value: str | None):
    if value is None:
        return None
    path = Path(value)
    if not path.is_file():
        raise ValidationError("RIGHTS_FILE_REQUIRED")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("RIGHTS_JSON") from exc


def _write_admission_report(value: str, report: dict) -> None:
    """Create one deterministic report without replacing an existing one."""
    target = Path(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
            temporary_name = handle.name
            handle.write(payload)
        # link(2) creates the final name atomically and refuses to replace it.
        os.link(temporary_name, target)
    except FileExistsError as exc:
        raise JLegalError(f"EGOV_ADMISSION_REPORT_EXISTS_REFUSED: {target}") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _admission_failure(diagnostic: str) -> dict:
    return {
        "accepted": False,
        "diagnostics": [diagnostic],
        "input_kind": None,
        "official_law_id": None,
        "profile": "J-LEGAL-OKF/0.1.0-draft",
        "receipt_verified": False,
        "schema": "jlegal-egov-admission/v1",
        "source_bytes": None,
        "source_sha256": None,
    }


def _validate_source(args) -> int:
    receipt = _acquisition(args.acquisition)
    admission = None
    try:
        admission = admit_egov_xml(args.input, law_id=args.law_id)
        receipt_verified = False
        if receipt is not None:
            mapping = {"law_id": args.law_id} if args.law_id is not None else None
            # Reuse the compilation provenance contract.  The adapter itself
            # invokes the same admission function, so this cannot validate a
            # different interpretation of the XML than compile will use.
            _egov_acquisition(egov_xml_adapter(Path(args.input), mapping), receipt)
            receipt_verified = True
        report = admission.report(accepted=True, receipt_verified=receipt_verified)
    except (AdapterError, ValidationError) as exc:
        if args.report is not None:
            failed = _admission_failure(str(exc)) if admission is None else admission.report(accepted=False, receipt_verified=False, diagnostics=(str(exc),))
            _write_admission_report(args.report, failed)
        raise
    if args.report is not None:
        _write_admission_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _compile(args) -> int:
    if bool(args.input) == bool(args.input_positional):
        raise ValidationError("COMPILE_INPUT_EXACTLY_ONE")
    mapping, mapping_path = _mapping(args.mapping)
    if args.law_id is not None:
        if args.adapter != "egov_xml" or mapping is not None:
            raise ValidationError("COMPILE_LAW_ID_EGOV_ONLY")
        mapping = {"law_id": args.law_id}
    input_path = args.input or args.input_positional
    result = compile_corpus(input_path, adapter=args.adapter, out_dir=args.out_dir, corpus_id=args.corpus_id or args.law_id or Path(input_path).stem, mapping=mapping, mapping_path=mapping_path, acquisition=_acquisition(args.acquisition), rights=_rights(args.rights))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _validate(args) -> int:
    crosswalk = args.crosswalk or str(Path(args.corpus).parent / "crosswalk.jsonl")
    verify_manifest(args.corpus, args.manifest, crosswalk, verify_inputs=args.verify_inputs, source=args.source)
    nodes = read_jsonl(args.corpus)
    if args.diagnostics_json:
        diagnostics = validate_corpus(nodes, read_crosswalk(crosswalk), raise_on_error=False)
        print(json.dumps([d.to_dict() for d in diagnostics], ensure_ascii=False, sort_keys=True))
        return 2 if diagnostics else 0
    validate_corpus(nodes, read_crosswalk(crosswalk))
    print(json.dumps({"valid": True, "nodes": len(nodes)}, sort_keys=True))
    return 0


def _fetch(args) -> int:
    result = fetch_egov_xml(args.law_id, args.output, as_of=args.as_of, timeout=args.timeout, force=args.force)
    if args.receipt_out is not None:
        write_acquisition_receipt(result, args.receipt_out)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _export_okf(args) -> int:
    print(json.dumps(export_okf(args.corpus, args.manifest, args.out_dir, source=args.source), ensure_ascii=False, sort_keys=True))
    return 0


def _validate_okf(args) -> int:
    print(json.dumps(validate_okf(args.bundle, verify_source=args.verify_source), ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jlegal", description="J-LEGAL-OKF public reference core (JORI Engine)")
    parser.add_argument("--version", action="version", version=_VERSION_TEXT)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("validate-source", help="Admit a saved e-Gov XML source before compilation."); item.add_argument("input"); item.add_argument("--law-id"); item.add_argument("--acquisition", help="Optional e-Gov fetch receipt JSON to verify."); item.add_argument("--report", help="Create a deterministic admission report; refuses to overwrite."); item.set_defaults(func=_validate_source)
    item = sub.add_parser("compile"); item.add_argument("input_positional", nargs="?"); item.add_argument("--input"); item.add_argument("--adapter", choices=("json", "xml", "html", "egov_xml")); item.add_argument("--mapping"); item.add_argument("--acquisition", help="Fetch receipt JSON written by jlegal fetch --receipt-out."); item.add_argument("--law-id"); item.add_argument("--out-dir", required=True); item.add_argument("--corpus-id"); item.add_argument("--rights", help="JSON file asserting source_license, bundle_license, redistribution_allowed, and commercial_use_allowed. Recorded verbatim; never inferred. Omit it and the manifest records no rights area at all."); item.set_defaults(func=_compile)
    item = sub.add_parser("validate"); item.add_argument("--corpus", required=True); item.add_argument("--manifest", required=True); item.add_argument("--crosswalk"); item.add_argument("--verify-inputs", action="store_true"); item.add_argument("--source", help="Source file to replay against when --verify-inputs is set; required in that case."); item.add_argument("--diagnostics-json", action="store_true", help="Print the full diagnostic list (code, subject, detail, layer) as a JSON array instead of the default {valid, nodes} summary; exits 2 if any diagnostics were found."); item.set_defaults(func=_validate)
    item = sub.add_parser("fetch"); item.add_argument("law_id"); item.add_argument("--as-of"); item.add_argument("--output", required=True); item.add_argument("--receipt-out", help="Write a separate acquisition receipt JSON for compile --acquisition."); item.add_argument("--timeout", type=float, default=30.0); item.add_argument("--force", action="store_true"); item.set_defaults(func=_fetch)
    item = sub.add_parser("export-okf"); item.add_argument("--corpus", required=True); item.add_argument("--manifest", required=True); item.add_argument("--out-dir", required=True); item.add_argument("--source", help="Local copy of the compiled source file; embedded into the bundle as references/source.xml. Required for a single-source corpus."); item.set_defaults(func=_export_okf)
    item = sub.add_parser("validate-okf"); item.add_argument("bundle"); item.add_argument("--verify-source", action="store_true", help="Re-convert the bundle's embedded references/source.xml and byte-compare it against canonical/corpus.jsonl, crosswalk.jsonl, and projection.jsonl."); item.set_defaults(func=_validate_okf)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (AdapterError, ValidationError, LegalOKFError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (JLegalError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


def _main(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
