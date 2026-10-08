"""Freeze every local XML input before any admission filtering."""

from __future__ import annotations

from pathlib import Path

from defusedxml.common import DefusedXmlException
from defusedxml import ElementTree as ET

from ..egov import _law_and_identifier, _read_admissible_xml, _safe_fromstring
from ..errors import AdapterError
from .contracts import (AssuranceError, canonical_bytes, digest, file_digest, files_under,
                        new_output, read_json, relative_path, valid_law_id, write_json)


def _identity(path: Path, supplied: str | None) -> tuple[str | None, str]:
    try:
        root = _safe_fromstring(_read_admissible_xml(path))
        _, law_id = _law_and_identifier(root, supplied)
    except (DefusedXmlException, ET.ParseError):
        return supplied, "INVALID_XML"
    except AdapterError as exc:
        codes = {"EGOV_XML_LAW_ID_REQUIRED": "MISSING_ID", "EGOV_XML_LAW_ID_MISMATCH": "CONFLICTING_ID",
                 "EGOV_XML_INPUT_EMPTY": "INVALID_XML", "EGOV_XML_INPUT_TOO_LARGE": "INPUT_TOO_LARGE",
                 "INPUT_TOO_LARGE": "INPUT_TOO_LARGE",
                 "INPUT_XML_DEPTH_LIMIT": "INPUT_XML_DEPTH_LIMIT",
                 "INPUT_XML_ELEMENT_LIMIT": "INPUT_XML_ELEMENT_LIMIT"}
        return supplied, codes.get(str(exc), "INVALID_ENVELOPE")
    if not valid_law_id(law_id):
        return None, "INVALID_ID"
    return law_id, "IDENTIFIED"


def build_inventory(input_dir: Path, mapping: dict | None = None) -> tuple[dict, dict]:
    mapping = {} if mapping is None else mapping
    if type(mapping) is not dict:
        raise AssuranceError("LAW_ID_MAP_SHAPE")
    for name, law_id in mapping.items():
        relative_path(name)
        if not valid_law_id(law_id):
            raise AssuranceError("LAW_ID_MAP_ID")
    paths = [p for p in files_under(input_dir) if p.suffix.lower() == ".xml"]
    names = {p.relative_to(input_dir).as_posix() for p in paths}
    if set(mapping) - names:
        raise AssuranceError("LAW_ID_MAP_UNKNOWN_FILE")
    records, units = [], {}
    for path in paths:
        name = path.relative_to(input_dir).as_posix()
        sha, size = file_digest(path), path.stat().st_size
        law_id, status = _identity(path, mapping.get(name))
        if file_digest(path) != sha or path.stat().st_size != size:
            raise AssuranceError("INPUT_CHANGED")
        unit_id = digest(canonical_bytes([law_id, sha]))
        row = {"unit_id": unit_id, "law_id": law_id, "source_sha256": sha,
               "source_bytes": size, "identity_status": status}
        records.append({**row, "path": name})
        if unit_id in units:
            if units[unit_id]["identity_status"] != status:
                raise AssuranceError("DUPLICATE_IDENTITY_CONFLICT")
            units[unit_id]["occurrences"] += 1
        else:
            units[unit_id] = {**row, "occurrences": 1}
    dataset = {"schema": "jlegal-survey-dataset/v1", "files": len(records),
               "unique_units": len(units), "duplicates": len(records) - len(units),
               "units": sorted(units.values(), key=lambda row: row["unit_id"])}
    local = {"schema": "jlegal-survey-input/v1", "law_id_map": mapping,
             "dataset_sha256": digest(canonical_bytes(dataset)), "files": records}
    return local, dataset


def inventory(input_dir: Path, out_dir: Path, law_id_map: Path | None = None) -> dict:
    local, dataset = build_inventory(input_dir, read_json(law_id_map) if law_id_map else None)
    new_output(out_dir)
    write_json(out_dir / "inventory.local.json", local)
    write_json(out_dir / "dataset.json", dataset)
    return dataset


def verify_inventory(path: Path, root: Path) -> tuple[dict, dict]:
    frozen = read_json(path)
    if frozen.get("schema") != "jlegal-survey-input/v1" or type(frozen.get("law_id_map")) is not dict:
        raise AssuranceError("INVENTORY_SHAPE")
    current, dataset = build_inventory(root, frozen["law_id_map"])
    if current != frozen:
        raise AssuranceError("INVENTORY_CHANGED")
    return current, dataset
