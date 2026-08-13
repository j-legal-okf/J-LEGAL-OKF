"""Contract tests for the optional rights area of a compiled corpus and bundle.

The area is the one place this profile records licensing facts, and it records
only what a caller asserts. These tests pin both halves of that: what the
manifest looks like when nothing is asserted (unchanged, v5, no key at all),
and what it must look like when something is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jlegal_okf.cli import main
from jlegal_okf.errors import JLegalError, ValidationError
from jlegal_okf.legal_okf import LegalOKFError, export_okf, validate_okf
from jlegal_okf.model import canonical_json
from jlegal_okf.pipeline import compile_corpus, verify_manifest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/fixtures/synthetic_egov_structure_matrix.xml"
FIXTURE_LAW_ID = "SyntheticStructureMatrix001"
FIXED_CONVERTED_AT = "2026-08-09T00:00:00Z"
RIGHTS: dict[str, Any] = {
    "source_license": "Public Data License 1.0",
    "bundle_license": "Apache-2.0",
    "redistribution_allowed": True,
    "commercial_use_allowed": None,
}
OTHER_RIGHTS: dict[str, Any] = dict(RIGHTS, commercial_use_allowed=True)


def _compile(out_dir: Path, rights: Any = None) -> dict[str, Any]:
    return compile_corpus(
        FIXTURE,
        adapter="egov_xml",
        corpus_id="synthetic-egov-structure-matrix",
        mapping={"law_id": FIXTURE_LAW_ID},
        out_dir=out_dir,
        converted_at=FIXED_CONVERTED_AT,
        rights=rights,
    )


def _manifest(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))


def _rewrite(path: Path, manifest: dict[str, Any]) -> None:
    path.write_bytes(canonical_json(manifest) + b"\n")


def test_no_rights_assertion_leaves_the_manifest_shape_unchanged(tmp_path: Path) -> None:
    """Absence is the one representation of "no rights recorded"."""
    default = _compile(tmp_path / "default")
    explicit = _compile(tmp_path / "explicit-none", rights=None)
    assert Path(default["manifest"]).read_bytes() == Path(explicit["manifest"]).read_bytes()
    manifest = _manifest(default)
    assert manifest["schema"] == "jori-manifest/v5"
    assert "rights" not in manifest


def test_asserted_rights_is_recorded_verbatim_and_verifies(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus", rights=RIGHTS)
    manifest = _manifest(result)
    assert manifest["schema"] == "jori-manifest/v6"
    assert manifest["rights"] == RIGHTS
    # The receipt's own rights slot is a different question and stays null:
    # e-Gov delivery is not a rights assertion, an explicit caller is.
    assert manifest["acquisition"]["rights"] is None
    verified = verify_manifest(
        result["corpus"],
        result["manifest"],
        Path(result["corpus"]).parent / "crosswalk.jsonl",
        Path(result["corpus"]).parent / "projection.jsonl",
        verify_inputs=True,
        source=FIXTURE,
    )
    assert verified["rights"] == RIGHTS


def test_rights_binds_into_build_options_but_not_into_the_corpus(tmp_path: Path) -> None:
    none = _manifest(_compile(tmp_path / "none"))
    first = _manifest(_compile(tmp_path / "first", rights=RIGHTS))
    second = _manifest(_compile(tmp_path / "second", rights=OTHER_RIGHTS))
    digests = {none["build_options_sha256"], first["build_options_sha256"], second["build_options_sha256"]}
    assert len(digests) == 3
    assert none["corpus_sha256"] == first["corpus_sha256"] == second["corpus_sha256"]
    assert none["projection_sha256"] == first["projection_sha256"] == second["projection_sha256"]


def test_the_same_assertion_compiles_byte_identically(tmp_path: Path) -> None:
    first = _compile(tmp_path / "first", rights=RIGHTS)
    # Key order in the caller's dict must not reach the artifact.
    reordered = {key: RIGHTS[key] for key in reversed(list(RIGHTS))}
    second = _compile(tmp_path / "second", rights=reordered)
    assert Path(first["manifest"]).read_bytes() == Path(second["manifest"]).read_bytes()


def test_tampering_with_a_recorded_assertion_is_detected(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus", rights=RIGHTS)
    manifest_path = Path(result["manifest"])
    manifest = _manifest(result)
    manifest["rights"]["commercial_use_allowed"] = True
    _rewrite(manifest_path, manifest)
    with pytest.raises(JLegalError, match="MANIFEST_OPTIONS_TAMPERED"):
        verify_manifest(result["corpus"], manifest_path)


def test_schema_and_rights_key_must_agree(tmp_path: Path) -> None:
    with_rights = _compile(tmp_path / "with-rights", rights=RIGHTS)
    without = _compile(tmp_path / "without-rights")
    dropped = _manifest(with_rights)
    del dropped["rights"]
    _rewrite(Path(with_rights["manifest"]), dropped)
    with pytest.raises(ValidationError, match="MANIFEST_KEYS"):
        verify_manifest(with_rights["corpus"], with_rights["manifest"])
    smuggled = _manifest(without)
    smuggled["rights"] = RIGHTS
    _rewrite(Path(without["manifest"]), smuggled)
    with pytest.raises(ValidationError, match="MANIFEST_KEYS"):
        verify_manifest(without["corpus"], without["manifest"])


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("Apache-2.0", "RIGHTS_SHAPE"),
        ({key: RIGHTS[key] for key in RIGHTS if key != "bundle_license"}, "RIGHTS_SHAPE"),
        (dict(RIGHTS, access_control="none"), "RIGHTS_SHAPE"),
        (dict(RIGHTS, source_license=""), "RIGHTS_VALUES"),
        (dict(RIGHTS, source_license="with\0nul"), "RIGHTS_VALUES"),
        (dict(RIGHTS, bundle_license=["Apache-2.0"]), "RIGHTS_VALUES"),
        (dict(RIGHTS, redistribution_allowed=1), "RIGHTS_VALUES"),
        (dict(RIGHTS, redistribution_allowed="true"), "RIGHTS_VALUES"),
        ({key: None for key in RIGHTS}, "RIGHTS_EMPTY"),
    ],
)
def test_a_malformed_assertion_is_refused_before_anything_is_written(tmp_path: Path, value: Any, code: str) -> None:
    out_dir = tmp_path / "corpus"
    with pytest.raises(ValidationError, match=code):
        _compile(out_dir, rights=value)
    assert not out_dir.exists()


def test_a_manifest_declaring_v6_is_revalidated_not_trusted(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus", rights=RIGHTS)
    manifest_path = Path(result["manifest"])
    manifest = _manifest(result)
    manifest["rights"]["redistribution_allowed"] = "true"
    _rewrite(manifest_path, manifest)
    with pytest.raises(ValidationError, match="RIGHTS_VALUES"):
        verify_manifest(result["corpus"], manifest_path)


def test_a_manifest_declaring_v6_with_a_null_rights_area_is_refused(tmp_path: Path) -> None:
    """A recorded null is a malformed area, not a second spelling of silence.

    Starts from a manifest that never asserted rights (v5), then promotes it
    to v6 with rights: null -- the same promotion a v5-to-v6 digest collision
    would let through, since build_options_sha256 does not bind rights when
    the value is None either way.
    """
    result = _compile(tmp_path / "corpus")
    manifest_path = Path(result["manifest"])
    manifest = _manifest(result)
    assert manifest["schema"] == "jori-manifest/v5"
    manifest["schema"] = "jori-manifest/v6"
    manifest["rights"] = None
    _rewrite(manifest_path, manifest)
    with pytest.raises(ValidationError, match="RIGHTS_SHAPE"):
        verify_manifest(result["corpus"], manifest_path)


def test_rights_requires_this_profiles_manifest(tmp_path: Path) -> None:
    source = tmp_path / "generic.json"
    source.write_text(
        json.dumps(
            {
                "jurisdiction": "Example",
                "authority": "Test",
                "source_law_key": "synthetic-001",
                "nodes": [{"locator": "root", "kind": "law", "text": "Synthetic statute"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "corpus"
    with pytest.raises(ValidationError, match="RIGHTS_PROFILE_REQUIRED"):
        compile_corpus(source, adapter="json", corpus_id="generic", out_dir=out_dir, rights=RIGHTS)
    assert not out_dir.exists()


def test_bundle_carries_the_assertion_over_and_validates(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus", rights=RIGHTS)
    bundle = Path(export_okf(result["corpus"], result["manifest"], tmp_path / "bundle", source=FIXTURE)["bundle"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "jlegal-okf-bundle/v2"
    assert manifest["rights"] == RIGHTS
    assert validate_okf(bundle)["valid"] is True
    assert validate_okf(bundle, verify_source=True)["source_reverified"] is True


def test_a_bundle_without_an_assertion_keeps_the_v1_shape(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus")
    bundle = Path(export_okf(result["corpus"], result["manifest"], tmp_path / "bundle", source=FIXTURE)["bundle"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "jlegal-okf-bundle/v1"
    assert "rights" not in manifest
    assert validate_okf(bundle)["valid"] is True


def test_a_bundle_may_neither_invent_nor_drop_an_assertion(tmp_path: Path) -> None:
    asserted = _compile(tmp_path / "corpus-rights", rights=RIGHTS)
    silent = _compile(tmp_path / "corpus-silent")
    with_rights = Path(export_okf(asserted["corpus"], asserted["manifest"], tmp_path / "bundle-rights", source=FIXTURE)["bundle"])
    without = Path(export_okf(silent["corpus"], silent["manifest"], tmp_path / "bundle-silent", source=FIXTURE)["bundle"])

    changed = json.loads((with_rights / "manifest.json").read_text(encoding="utf-8"))
    changed["rights"] = OTHER_RIGHTS
    _rewrite(with_rights / "manifest.json", changed)
    with pytest.raises(LegalOKFError, match="JLEGAL_OKF_RIGHTS_MISMATCH"):
        validate_okf(with_rights)

    invented = json.loads((without / "manifest.json").read_text(encoding="utf-8"))
    invented["schema"] = "jlegal-okf-bundle/v2"
    invented["rights"] = RIGHTS
    _rewrite(without / "manifest.json", invented)
    with pytest.raises(LegalOKFError, match="JLEGAL_OKF_RIGHTS_MISMATCH"):
        validate_okf(without)


def test_a_bundle_manifest_declaring_v2_must_carry_a_well_formed_area(tmp_path: Path) -> None:
    result = _compile(tmp_path / "corpus", rights=RIGHTS)
    bundle = Path(export_okf(result["corpus"], result["manifest"], tmp_path / "bundle", source=FIXTURE)["bundle"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["rights"] = {"source_license": "Public Data License 1.0"}
    _rewrite(bundle / "manifest.json", manifest)
    with pytest.raises(LegalOKFError, match="JLEGAL_OKF_MANIFEST_SHAPE"):
        validate_okf(bundle)


def test_a_bundle_declaring_v2_with_a_null_rights_area_is_refused(tmp_path: Path) -> None:
    """Rewriting a silent v1 bundle to v2 with rights: null must not pass as v1's absence."""
    result = _compile(tmp_path / "corpus")
    bundle = Path(export_okf(result["corpus"], result["manifest"], tmp_path / "bundle", source=FIXTURE)["bundle"])
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "jlegal-okf-bundle/v2"
    manifest["rights"] = None
    _rewrite(manifest_path, manifest)
    with pytest.raises(LegalOKFError, match="JLEGAL_OKF_MANIFEST_SHAPE"):
        validate_okf(bundle)


def test_cli_compile_records_an_asserted_area(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rights_file = tmp_path / "rights.json"
    rights_file.write_text(json.dumps(RIGHTS), encoding="utf-8")
    assert main(["compile", str(FIXTURE), "--adapter", "egov_xml", "--law-id", FIXTURE_LAW_ID, "--out-dir", str(tmp_path / "corpus"), "--rights", str(rights_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))["rights"] == RIGHTS


@pytest.mark.parametrize(("content", "code"), [(None, "RIGHTS_FILE_REQUIRED"), ("{not json", "RIGHTS_JSON")])
def test_cli_compile_refuses_an_unusable_rights_file(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None, code: str) -> None:
    rights_file = tmp_path / "rights.json"
    if content is not None:
        rights_file.write_text(content, encoding="utf-8")
    out_dir = tmp_path / "corpus"
    assert main(["compile", str(FIXTURE), "--adapter", "egov_xml", "--law-id", FIXTURE_LAW_ID, "--out-dir", str(out_dir), "--rights", str(rights_file)]) == 2
    assert code in capsys.readouterr().err
    assert not out_dir.exists()
