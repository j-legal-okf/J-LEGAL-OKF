"""Publication checks and interruption cleanup using synthetic sources only."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from jlegal_okf import legal_okf, pipeline
from jlegal_okf.adapters import default_registry
from jlegal_okf.errors import JLegalError


SOURCE = Path(__file__).parents[1] / "examples" / "synthetic_egov_law.xml"
NAMES = {"corpus.jsonl", "crosswalk.jsonl", "projection.jsonl", "manifest.json"}


@pytest.fixture
def adaptation(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "jurisdiction": "Example", "authority": "Test", "source_law_key": "invented",
        "nodes": [{"locator": "root", "kind": "law", "text": "Invented law", "children": [
            {"locator": "article", "kind": "article", "ordinal": 1, "text": "Invented provision"},
        ]}],
    }), encoding="utf-8")
    return default_registry().adapt(source, name="json")


def _compile(adaptation, destination):
    return pipeline.compile_adaptation(adaptation, corpus_id="invented", out_dir=destination)


def _bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _no_stage(destination):
    assert not destination.exists()
    assert list(destination.parent.glob(destination.name + ".stage.*")) == []


def test_compile_publishes_exact_generated_bytes(tmp_path, adaptation, monkeypatch):
    written = {}
    original = pipeline._atomic_bytes

    def record(path, raw):
        written[path.name] = raw
        original(path, raw)

    monkeypatch.setattr(pipeline, "_atomic_bytes", record)
    destination = tmp_path / "out"
    result = _compile(adaptation, destination)
    assert set(written) == NAMES
    assert _bytes(destination) == written
    assert result["nodes"] == 2
    pipeline.verify_manifest(destination / "corpus.jsonl", destination / "manifest.json")


@pytest.mark.parametrize("mutation,code", [
    ("missing", "STAGED_OUTPUT_FILE_SET"), ("extra", "STAGED_OUTPUT_FILE_SET"),
    ("symlink", "STAGED_OUTPUT_FILE_SET"), ("directory", "STAGED_OUTPUT_FILE_SET"),
    ("modified", "STAGED_OUTPUT_MISMATCH"),
])
def test_compile_rejects_written_stage_mutations(tmp_path, adaptation, monkeypatch, mutation, code):
    original = pipeline._atomic_bytes
    unrelated = tmp_path / "other.stage.kept"
    unrelated.mkdir()
    (unrelated / "keep").write_bytes(b"keep")
    target = tmp_path / "symlink-target"
    target.write_bytes(b"outside")

    def corrupt(path, raw):
        original(path, raw)
        if path.name != "manifest.json":
            return
        corpus = path.parent / "corpus.jsonl"
        if mutation == "missing":
            corpus.unlink()
        elif mutation == "extra":
            (path.parent / "extra").write_bytes(b"extra")
        elif mutation == "symlink":
            corpus.unlink()
            corpus.symlink_to(target)
        elif mutation == "directory":
            corpus.unlink()
            corpus.mkdir()
        else:
            corpus.write_bytes(corpus.read_bytes() + b" ")

    monkeypatch.setattr(pipeline, "_atomic_bytes", corrupt)
    destination = tmp_path / "out"
    with pytest.raises(JLegalError, match="^" + code + "$"):
        _compile(adaptation, destination)
    _no_stage(destination)
    assert target.read_bytes() == b"outside"
    assert (unrelated / "keep").read_bytes() == b"keep"


@pytest.mark.parametrize("custom", [False, True])
def test_stage_checks_disk_artifacts_and_trusted_adapter(tmp_path, adaptation, monkeypatch, custom):
    if custom:
        adaptation = replace(adaptation, adapter="custom", version="7")
    calls = []
    original_artifacts = pipeline.verify_canonical_artifacts
    original_validate = pipeline.validate_corpus
    original_manifest = pipeline.verify_manifest

    def artifacts(*args):
        value = original_artifacts(*args)
        calls.append(("artifacts", value))
        return value

    def validate(nodes, crosswalk):
        if calls:
            assert tuple(nodes) == calls[0][1].nodes
            assert tuple(crosswalk) == calls[0][1].crosswalk
            calls.append(("structure", None))
        return original_validate(nodes, crosswalk)

    def manifest(*args, **kwargs):
        calls.append(("manifest", None))
        return original_manifest(*args, **kwargs)

    monkeypatch.setattr(pipeline, "verify_canonical_artifacts", artifacts)
    monkeypatch.setattr(pipeline, "validate_corpus", validate)
    monkeypatch.setattr(pipeline, "verify_manifest", manifest)
    destination = tmp_path / "out"
    _compile(adaptation, destination)
    assert [name for name, _ in calls] == ["artifacts", "structure"] + ([] if custom else ["manifest", "artifacts"])
    if custom:
        with pytest.raises(JLegalError, match="MANIFEST_OPTIONS"):
            original_manifest(destination / "corpus.jsonl", destination / "manifest.json")


def test_written_manifest_cannot_disable_public_validation(tmp_path, adaptation, monkeypatch):
    original = pipeline.manifest_for

    def disguised(*args, **kwargs):
        value = original(*args, **kwargs)
        value["adapter"] = "custom"
        return value

    monkeypatch.setattr(pipeline, "manifest_for", disguised)
    destination = tmp_path / "out"
    with pytest.raises(JLegalError, match="MANIFEST_OPTIONS"):
        _compile(adaptation, destination)
    _no_stage(destination)


def test_stage_byte_match_does_not_bypass_canonical_validation(tmp_path, adaptation):
    destination = tmp_path / "out"
    _compile(adaptation, destination)
    expected = _bytes(destination)
    expected["corpus.jsonl"] += b"\n"
    (destination / "corpus.jsonl").write_bytes(expected["corpus.jsonl"])
    with pytest.raises(JLegalError, match="ARTIFACT_NOT_CANONICAL"):
        pipeline._verify_staged_compilation(destination, expected, "custom")


def test_stage_canonical_byte_match_does_not_bypass_structure_validation(tmp_path, adaptation):
    destination = tmp_path / "out"
    _compile(adaptation, destination)
    nodes = pipeline.read_jsonl(destination / "corpus.jsonl")
    nodes[1] = replace(nodes[1], parent_id="missing-parent")
    expected = _bytes(destination)
    expected["corpus.jsonl"] = pipeline.canonical_jsonl(nodes)
    expected["projection.jsonl"] = pipeline.canonical_projection_jsonl(pipeline.make_projection(nodes))
    for name, raw in expected.items():
        (destination / name).write_bytes(raw)
    with pytest.raises(JLegalError, match="PARENT_MISSING"):
        pipeline._verify_staged_compilation(destination, expected, "custom")


@pytest.mark.parametrize("phase", ["write", "pending_write", "validation", "rename"])
@pytest.mark.parametrize("exception_type", [OSError, KeyboardInterrupt, SystemExit])
def test_compile_cleans_precommit_failures_and_reraises_original(tmp_path, adaptation, monkeypatch, phase, exception_type):
    failure = exception_type("injected")
    destination = tmp_path / "out"
    original_write = pipeline._atomic_bytes
    original_replace = pipeline.os.replace

    def write(path, raw):
        original_write(path, raw)
        raise failure

    def validate(*args, **kwargs):
        raise failure

    def rename(source, target):
        if Path(target) == destination or (phase == "pending_write" and Path(target).name == "corpus.jsonl"):
            raise failure
        return original_replace(source, target)

    if phase == "write":
        monkeypatch.setattr(pipeline, "_atomic_bytes", write)
    elif phase == "validation":
        monkeypatch.setattr(pipeline, "_verify_staged_compilation", validate)
    else:
        monkeypatch.setattr(pipeline.os, "replace", rename)
    with pytest.raises(exception_type) as caught:
        _compile(adaptation, destination)
    assert caught.value is failure
    _no_stage(destination)


@pytest.mark.parametrize("existing", ["file", "directory"])
def test_compile_refuses_existing_output_before_stage(tmp_path, adaptation, monkeypatch, existing):
    destination = tmp_path / "out"
    if existing == "file":
        destination.write_bytes(b"existing")
    else:
        destination.mkdir()
        (destination / "keep").write_bytes(b"existing")

    def forbidden(*args, **kwargs):
        pytest.fail("stage must not be created for existing output")

    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", forbidden)
    with pytest.raises(JLegalError, match="OUTPUT_EXISTS_REFUSED"):
        _compile(adaptation, destination)
    assert (destination if existing == "file" else destination / "keep").read_bytes() == b"existing"


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_compile_keeps_complete_final_after_commit_interruption(tmp_path, adaptation, monkeypatch, exception_type):
    destination = tmp_path / "out"
    expected_dir = tmp_path / "expected"
    _compile(adaptation, expected_dir)
    original = pipeline.os.replace
    failure = exception_type("after commit")

    def rename(source, target):
        original(source, target)
        if Path(target) == destination:
            raise failure

    monkeypatch.setattr(pipeline.os, "replace", rename)
    with pytest.raises(exception_type) as caught:
        _compile(adaptation, destination)
    assert caught.value is failure
    assert _bytes(destination) == _bytes(expected_dir)
    pipeline.verify_manifest(destination / "corpus.jsonl", destination / "manifest.json")
    assert list(tmp_path.glob("out.stage.*")) == []


@pytest.fixture
def compiled_egov(tmp_path):
    corpus = tmp_path / "corpus"
    pipeline.compile_corpus(SOURCE, adapter="egov_xml", out_dir=corpus,
                            corpus_id="synthetic-law", converted_at="2024-01-01T00:00:00Z")
    return corpus


def _export(corpus, destination):
    return legal_okf.export_okf(corpus / "corpus.jsonl", corpus / "manifest.json", destination, source=SOURCE)


def test_export_validates_written_stage_without_source_replay(tmp_path, compiled_egov, monkeypatch):
    destination = tmp_path / "out"
    calls = []
    original = legal_okf.validate_okf

    def validate(stage, *, verify_source):
        assert stage.is_dir()
        assert not destination.exists()
        assert verify_source is False
        value = original(stage, verify_source=verify_source)
        calls.append(value)
        return value

    def forbidden(*args, **kwargs):
        pytest.fail("ordinary stage validation must not replay the source")

    monkeypatch.setattr(legal_okf, "validate_okf", validate)
    monkeypatch.setattr(pipeline, "_rebuild_from_manifest", forbidden)
    result = _export(compiled_egov, destination)
    assert result["bundle"] == str(destination)
    assert len(calls) == 1
    assert calls[0]["source_reverified"] is False
    assert _bytes(destination / "canonical") == _bytes(compiled_egov)
    assert (destination / "references" / "source.xml").read_bytes() == SOURCE.read_bytes()


def test_export_rejects_corrupt_index_with_existing_diagnostic(tmp_path, compiled_egov, monkeypatch):
    original = legal_okf._atomic_bytes

    def corrupt(path, raw):
        original(path, raw + b"corrupt\n" if path.name == "index.md" else raw)

    monkeypatch.setattr(legal_okf, "_atomic_bytes", corrupt)
    destination = tmp_path / "out"
    with pytest.raises(legal_okf.LegalOKFError, match="^JLEGAL_OKF_INDEX$"):
        _export(compiled_egov, destination)
    _no_stage(destination)


@pytest.mark.parametrize("phase", ["write", "pending_write", "validation", "rename"])
@pytest.mark.parametrize("exception_type", [OSError, KeyboardInterrupt, SystemExit])
def test_export_cleans_precommit_failures_and_reraises_original(tmp_path, compiled_egov, monkeypatch, phase, exception_type):
    failure = exception_type("injected")
    destination = tmp_path / "out"
    unrelated = tmp_path / "other.stage.kept"
    unrelated.mkdir()
    (unrelated / "keep").write_bytes(b"keep")
    original_write = legal_okf._atomic_bytes
    original_replace = legal_okf.os.replace

    def write(path, raw):
        original_write(path, raw)
        raise failure

    def validate(*args, **kwargs):
        raise failure

    def rename(source, target):
        if Path(target) == destination or (phase == "pending_write" and Path(target).name == "corpus.jsonl"):
            raise failure
        return original_replace(source, target)

    if phase == "write":
        monkeypatch.setattr(legal_okf, "_atomic_bytes", write)
    elif phase == "validation":
        monkeypatch.setattr(legal_okf, "validate_okf", validate)
    else:
        monkeypatch.setattr(legal_okf.os, "replace", rename)
    with pytest.raises(exception_type) as caught:
        _export(compiled_egov, destination)
    assert caught.value is failure
    _no_stage(destination)
    assert (unrelated / "keep").read_bytes() == b"keep"


@pytest.mark.parametrize("existing", ["file", "directory"])
def test_export_refuses_existing_output_before_stage(tmp_path, compiled_egov, monkeypatch, existing):
    destination = tmp_path / "out"
    if existing == "file":
        destination.write_bytes(b"existing")
    else:
        destination.mkdir()
        (destination / "keep").write_bytes(b"existing")

    def forbidden(*args, **kwargs):
        pytest.fail("stage must not be created for existing output")

    monkeypatch.setattr(legal_okf.tempfile, "mkdtemp", forbidden)
    with pytest.raises(legal_okf.LegalOKFError, match="JLEGAL_OKF_OUTPUT_EXISTS_REFUSED"):
        _export(compiled_egov, destination)
    assert (destination if existing == "file" else destination / "keep").read_bytes() == b"existing"


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_export_keeps_complete_final_after_commit_interruption(tmp_path, compiled_egov, monkeypatch, exception_type):
    destination = tmp_path / "out"
    expected_dir = tmp_path / "expected"
    _export(compiled_egov, expected_dir)
    original = legal_okf.os.replace
    failure = exception_type("after commit")

    def rename(source, target):
        original(source, target)
        if Path(target) == destination:
            raise failure

    monkeypatch.setattr(legal_okf.os, "replace", rename)
    with pytest.raises(exception_type) as caught:
        _export(compiled_egov, destination)
    assert caught.value is failure
    assert _bytes(destination) == _bytes(expected_dir)
    assert legal_okf.validate_okf(destination)["valid"] is True
    assert list(tmp_path.glob("out.stage.*")) == []


@pytest.mark.parametrize("producer", ["compile", "export"])
@pytest.mark.parametrize("existing", ["file", "directory"])
def test_final_rename_failure_preserves_new_existing_output(tmp_path, adaptation, compiled_egov, monkeypatch, producer, existing):
    destination = tmp_path / "out"
    original = pipeline.os.replace

    def rename(source, target):
        if Path(target) == destination:
            if existing == "file":
                destination.write_bytes(b"existing")
            else:
                destination.mkdir()
                (destination / "keep").write_bytes(b"existing")
        return original(source, target)

    monkeypatch.setattr(pipeline.os, "replace", rename)
    with pytest.raises(OSError):
        if producer == "compile":
            _compile(adaptation, destination)
        else:
            _export(compiled_egov, destination)
    assert (destination if existing == "file" else destination / "keep").read_bytes() == b"existing"
    assert list(tmp_path.glob("out.stage.*")) == []
