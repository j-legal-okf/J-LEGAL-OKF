"""Small, invented inputs exercise inclusive structured-input budgets."""
from __future__ import annotations

from dataclasses import replace
import errno
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from jlegal_okf import cli, input_limits as limits, pipeline
from jlegal_okf.adapters import AdapterRegistry, html_adapter, json_adapter, xml_adapter
from jlegal_okf.egov import egov_xml_adapter
from jlegal_okf.errors import AdapterError, ValidationError


FIXTURE = Path(__file__).resolve().parents[1] / "examples/synthetic_egov_law.xml"


@pytest.mark.parametrize("size", [15, 16, 17])
@pytest.mark.parametrize("parser", [limits.parse_json, limits.parse_options_yaml])
def test_text_byte_boundaries(size, parser):
    raw = "0" + " " * (size - 1)
    if size <= 16:
        assert parser(raw, max_bytes=16) == 0
    else:
        with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
            parser(raw, max_bytes=16)


@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("parser,prefix", [(limits.parse_json, "JSON"), (limits.parse_options_yaml, "YAML")])
@pytest.mark.parametrize("dimension", ["depth", "tokens"])
def test_preconstruction_boundaries(count, parser, prefix, dimension):
    raw = "[" * count + "]" * count if dimension == "depth" else "[" + ",".join("0" for _ in range(count - 1)) + "]"
    if count <= 3:
        parser(raw, **{"max_" + dimension: 3})
    else:
        with pytest.raises(AdapterError, match=f"^INPUT_{prefix}_{dimension.upper()[:-1] if dimension == 'tokens' else 'DEPTH'}_LIMIT$"):
            parser(raw, **{"max_" + dimension: 3})


@pytest.mark.parametrize("dimension", ["depth", "tokens"])
@pytest.mark.parametrize("syntax", ["json", "yaml"])
def test_limit_rejects_before_object_construction(monkeypatch, dimension, syntax):
    spy = Mock(side_effect=AssertionError("construction was reached"))
    if syntax == "json":
        monkeypatch.setattr(limits.json, "loads", spy)
        parse = limits.parse_json
    else:
        monkeypatch.setattr(limits.yaml, "safe_load", spy)
        parse = limits.parse_options_yaml
    with pytest.raises(AdapterError, match=f"^INPUT_{syntax.upper()}_"):
        parse("[[0]]", **{"max_" + dimension: 1})
    spy.assert_not_called()


@pytest.mark.parametrize("parser", [limits.parse_json, limits.parse_options_yaml, limits.validate_options])
@pytest.mark.parametrize("keyword", ["max_bytes", "max_depth", "max_tokens"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2"])
def test_invalid_limits(parser, keyword, value):
    with pytest.raises(AdapterError, match="^INPUT_LIMIT_VALUE$"):
        parser("0", **{keyword: value})


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2"])
def test_integer_and_reader_invalid_limits(tmp_path, value):
    with pytest.raises(AdapterError, match="^INPUT_LIMIT_VALUE$"):
        limits.validate_options(0, max_integer_bits=value)
    with pytest.raises(AdapterError, match="^INPUT_LIMIT_VALUE$"):
        limits.read_bounded_bytes(tmp_path / "never-opened", max_bytes=value)


def test_json_tokens_include_keys_duplicates_and_ignore_quoted_structure():
    raw = '{"a":"[\\\"{}]","a":[0]}'
    assert limits.parse_json(raw, max_tokens=6, max_depth=2) == {"a": [0]}
    with pytest.raises(AdapterError, match="^INPUT_JSON_TOKEN_LIMIT$"):
        limits.parse_json(raw, max_tokens=5)
    assert limits.parse_json("0", max_tokens=1, max_depth=1) == 0
    assert limits.parse_json("[]", max_tokens=1, max_depth=1) == []
    assert limits.parse_json('{"a":0}', max_tokens=3) == {"a": 0}


@pytest.mark.parametrize("raw", ['{"a":}', '[0,]', '"unterminated', '{}{}', 'nul', '{]'])
def test_standard_decoder_owns_invalid_json_grammar(raw):
    with pytest.raises(AdapterError, match="^INPUT_JSON_PARSE$"):
        limits.parse_json(raw)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_nonfinite_json_is_rejected_in_unused_values(token):
    with pytest.raises(AdapterError, match="^INPUT_NONFINITE$"):
        limits.parse_json('{"unused":' + token + '}')


@pytest.mark.parametrize("value", [(1 << 4096) - 1, -((1 << 4096) - 1)])
def test_source_integer_4096_bit_boundary(value):
    assert limits.parse_json(str(value)) == value
    with pytest.raises(AdapterError, match="^INPUT_OPTION_INTEGER_LIMIT$"):
        limits.parse_json(str(1 << 4096))
    with pytest.raises(AdapterError, match="^INPUT_OPTION_INTEGER_LIMIT$"):
        limits.parse_json("9" * 5000)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"])
def test_source_json_encodings_preserve_source_bytes(tmp_path, encoding):
    value = {"jurisdiction": "Example", "authority": "Act", "law_number_key": "1",
             "nodes": [{"locator": "root", "kind": "law", "text": "Invented é\r\n"}]}
    raw = json.dumps(value, ensure_ascii=False).encode(encoding)
    path = tmp_path / "source.json"
    path.write_bytes(raw)
    assert limits.parse_json(raw) == value
    node = json_adapter(path).nodes[0]
    assert node.text == value["nodes"][0]["text"]
    assert node.source.sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("raw", [b'"\xff"', b'"\xed\xa0\x80"', '"\\ud800"', b'\xff\xfe\x00'])
def test_invalid_encoding_has_only_stable_diagnostic(raw):
    with pytest.raises(AdapterError, match="^INPUT_ENCODING$"):
        limits.parse_json(raw)


def test_valid_escaped_surrogate_pair_remains_accepted():
    assert limits.parse_json('"\\ud83d\\ude00"') == "😀"


@pytest.mark.parametrize("raw", ["a: &loop [*loop]", "a: &one [0]\nb: *one", "[*missing]"])
def test_yaml_aliases_rejected_before_safe_load(monkeypatch, raw):
    spy = Mock(side_effect=AssertionError("construction was reached"))
    monkeypatch.setattr(limits.yaml, "safe_load", spy)
    with pytest.raises(AdapterError, match="^INPUT_YAML_ALIAS_FORBIDDEN$"):
        limits.parse_options_yaml(raw)
    spy.assert_not_called()


def test_yaml_anchor_without_alias_and_duplicate_count():
    assert limits.parse_options_yaml("a: &one [0]") == {"a": [0]}
    assert limits.parse_options_yaml("a: 0\na: 1", max_tokens=5) == {"a": 1}
    with pytest.raises(AdapterError, match="^INPUT_YAML_TOKEN_LIMIT$"):
        limits.parse_options_yaml("a: 0\na: 1", max_tokens=4)


@pytest.mark.parametrize("raw", ["[", "a: !invented value", "---\na: 1\n---\nb: 2"])
def test_yaml_parse_errors_are_safe(raw):
    with pytest.raises(AdapterError, match="^INPUT_YAML_PARSE$"):
        limits.parse_options_yaml(raw)


@pytest.mark.parametrize("raw,code", [("a: .nan", "INPUT_NONFINITE"), ("a: -.inf", "INPUT_NONFINITE"),
                                      ("a: 2026-01-01", "INPUT_OPTION_TYPE"), ("1: a", "INPUT_OPTION_TYPE")])
def test_yaml_constructed_graph_is_also_checked(raw, code):
    with pytest.raises(AdapterError, match="^" + code + "$"):
        limits.parse_options_yaml(raw)


@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("dimension", ["depth", "tokens"])
def test_graph_depth_and_token_boundaries(count, dimension):
    value = []
    if dimension == "depth":
        for _ in range(count - 1):
            value = [value]
    else:
        value = [0] * (count - 1)
    if count <= 3:
        limits.validate_options(value, **{"max_" + dimension: 3})
    else:
        code = "DEPTH" if dimension == "depth" else "TOKEN"
        with pytest.raises(AdapterError, match=f"^INPUT_OPTION_{code}_LIMIT$"):
            limits.validate_options(value, **{"max_" + dimension: 3})


@pytest.mark.parametrize("value", [127, 255, 256, -255, -256])
def test_graph_integer_bit_boundaries(value):
    if abs(value) <= 255:
        limits.validate_options(value, max_integer_bits=8)
    else:
        with pytest.raises(AdapterError, match="^INPUT_OPTION_INTEGER_LIMIT$"):
            limits.validate_options(value, max_integer_bits=8)


@pytest.mark.parametrize("budget", [3, 4, 5])
def test_canonical_utf8_byte_boundary(budget):
    if budget >= 4:
        limits.validate_options("é", max_bytes=budget)
    else:
        with pytest.raises(AdapterError, match="^INPUT_OPTION_BYTES_LIMIT$"):
            limits.validate_options("é", max_bytes=budget)


def test_shared_references_charge_every_occurrence():
    leaf = {"x": "a"}
    limits.validate_options([leaf, leaf], max_tokens=7, max_bytes=21)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_TOKEN_LIMIT$"):
        limits.validate_options([leaf, leaf], max_tokens=6)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_BYTES_LIMIT$"):
        limits.validate_options([leaf, leaf], max_bytes=20)
    assert leaf == {"x": "a"}


def test_graph_cycles_are_distinct_from_shared_references():
    value = {"self": []}
    value["self"].append(value)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        limits.validate_options(value)


def test_scalar_and_custom_type_checks_precede_encoder(monkeypatch):
    spy = Mock(side_effect=AssertionError("encoding was reached"))
    monkeypatch.setattr(limits.json.JSONEncoder, "iterencode", spy)
    for value, code in [("x" * 17, "INPUT_OPTION_BYTES_LIMIT"), (1 << 9, "INPUT_OPTION_INTEGER_LIMIT"),
                        (object(), "INPUT_OPTION_TYPE"), ("\ud800", "INPUT_ENCODING")]:
        with pytest.raises(AdapterError, match="^" + code + "$"):
            limits.validate_options(value, max_bytes=16, max_integer_bits=8)
    spy.assert_not_called()


def test_exact_types_do_not_invoke_hooks():
    class HookType(type):
        def __eq__(self, other):
            pytest.fail("custom type comparison hook")
    class HookObject(metaclass=HookType):
        pass
    class Trap(dict):
        def items(self):
            pytest.fail("custom items hook")
        def __str__(self):
            pytest.fail("custom string hook")
    for value in (Trap(), {"x": Trap()}, HookObject(), {1: "value"}, (1,), {1}, b"x"):
        with pytest.raises(AdapterError, match="^INPUT_OPTION_TYPE$"):
            limits.validate_options(value)


@pytest.mark.parametrize("adapter", [json_adapter, xml_adapter, html_adapter, egov_xml_adapter])
def test_all_direct_adapters_reject_cyclic_mapping_before_read(tmp_path, adapter):
    mapping = {}
    mapping["unused"] = mapping
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        adapter(tmp_path / "not-read", mapping)


def test_registry_checks_custom_adapter_mapping_before_dispatch(tmp_path):
    registry = AdapterRegistry()
    adapter = Mock()
    registry.register("custom", adapter, sniff=lambda p: True, priority=1)
    for name in (None, "custom"):
        with pytest.raises(AdapterError, match="^INPUT_NONFINITE$"):
            registry.adapt(tmp_path / "not-read", name=name, mapping={"unused": float("nan")})
    adapter.assert_not_called()


def test_mapping_file_inline_long_inline_and_oserror(tmp_path, monkeypatch):
    path = tmp_path / "mapping.yaml"
    path.write_text("a: 1", encoding="utf-8")
    assert cli._mapping(str(path)) == ({"a": 1}, path)
    assert cli._mapping('{"a":1}') == ({"a": 1}, None)
    assert cli._mapping("key: " + "x" * 300) == ({"key": "x" * 300}, None)
    def fail(*args):
        raise OSError(errno.EACCES, "not echoed")
    monkeypatch.setattr(Path, "exists", fail)
    with pytest.raises(AdapterError, match="^INPUT_UNAVAILABLE$"):
        cli._mapping("a: 1")


@pytest.mark.parametrize("loader,diagnostic", [(cli._acquisition, "ACQUISITION"), (cli._rights, "RIGHTS")])
def test_json_option_error_mapping_and_encoding(tmp_path, loader, diagnostic):
    path = tmp_path / "option.json"
    assert loader(None) is None
    with pytest.raises(ValidationError, match=f"^{diagnostic}_FILE_REQUIRED$"):
        loader(str(path))
    path.write_text("{ invented input", encoding="utf-8")
    with pytest.raises(ValidationError, match=f"^{diagnostic}_JSON$"):
        loader(str(path))
    path.write_bytes('{"a":1}'.encode("utf-16"))
    with pytest.raises(AdapterError, match="^INPUT_ENCODING$"):
        loader(str(path))
    path.write_text('{"a":1e400}', encoding="utf-8")
    with pytest.raises(AdapterError, match="^INPUT_NONFINITE$"):
        loader(str(path))


@pytest.mark.parametrize("option", ["mapping", "acquisition", "rights"])
def test_cli_option_file_limits_are_applied_at_runtime(tmp_path, monkeypatch, capsys, option):
    path = tmp_path / "option.json"
    path.write_text('{"a":1}' + " " * 20, encoding="utf-8")
    monkeypatch.setattr(limits, "MAX_OPTION_BYTES", 16)
    output = tmp_path / "output"
    code = cli.main(["compile", "not-read.json", "--adapter", "json", "--out-dir", str(output),
                     "--" + option, str(path)])
    assert code == 2
    assert capsys.readouterr().err == "error: INPUT_TOO_LARGE\n"
    assert not output.exists()


@pytest.mark.parametrize("field", ["mapping", "acquisition", "rights"])
def test_compile_entrypoints_guard_options_before_work(tmp_path, monkeypatch, field):
    cycle = {}
    cycle["self"] = cycle
    spy = Mock(side_effect=AssertionError("adapter was reached"))
    monkeypatch.setattr(pipeline, "default_registry", spy)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        pipeline.compile_corpus("not-read", adapter="json", out_dir=tmp_path / "out", corpus_id="invented", **{field: cycle})
    spy.assert_not_called()
    adaptation = egov_xml_adapter(FIXTURE)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        pipeline.compile_adaptation(adaptation, out_dir=tmp_path / "out", corpus_id="invented", **{field: cycle})


@pytest.mark.parametrize("target", ["base", "supplied"])
def test_acquisition_graphs_checked_before_comparison(tmp_path, target):
    adaptation = egov_xml_adapter(FIXTURE)
    bad = dict(adaptation.source_metadata)
    bad["law_number"] = bad
    if target == "base":
        adaptation = replace(adaptation, source_metadata=bad)
        supplied = dict(egov_xml_adapter(FIXTURE).source_metadata)
    else:
        supplied = bad
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        pipeline._egov_acquisition(adaptation, supplied)
    with pytest.raises(AdapterError, match="^INPUT_OPTION_CYCLE$"):
        pipeline.compile_adaptation(adaptation, acquisition=supplied, corpus_id="invented", out_dir=tmp_path / "out")


def test_shallow_semantic_diagnostics_are_preserved():
    with pytest.raises(ValidationError, match="^BUILD_RECIPE_MAPPING$"):
        pipeline._canonical_mapping([])
    with pytest.raises(ValidationError, match="^RIGHTS_SHAPE$"):
        pipeline._rights("license")
    with pytest.raises(AdapterError, match="^EGOV_XML_MAPPING$"):
        egov_xml_adapter(FIXTURE, [])


@pytest.mark.parametrize("adapter", [xml_adapter, html_adapter])
@pytest.mark.parametrize("mapping", [[], "fields", 42, False])
def test_generic_shallow_nonmapping_has_semantic_diagnostic(tmp_path, adapter, mapping):
    path = tmp_path / "source.xml"
    path.write_bytes(b"<r/>")
    with pytest.raises(AdapterError, match="^ADAPTER_MAPPING_REQUIRED$"):
        adapter(path, mapping)


@pytest.mark.parametrize("size", [15, 16, 17])
def test_general_reader_and_mapping_file_byte_boundaries(tmp_path, monkeypatch, size):
    path = tmp_path / "options.json"
    raw = b'{"a":0}' + b" " * (size - 7)
    path.write_bytes(raw)
    monkeypatch.setattr(limits, "MAX_OPTION_BYTES", 16)
    if size <= 16:
        assert limits.read_bounded_bytes(path, max_bytes=16) == raw
        assert limits.load_mapping_option(str(path)) == ({"a": 0}, path)
        assert limits.load_json_option(str(path), "RIGHTS") == {"a": 0}
    else:
        for read in (lambda: limits.read_bounded_bytes(path, max_bytes=16),
                     lambda: limits.load_mapping_option(str(path)),
                     lambda: limits.load_json_option(str(path), "RIGHTS")):
            with pytest.raises(AdapterError, match="^INPUT_TOO_LARGE$"):
                read()


def test_character_budget_counts_shared_string_occurrences_before_encoding(monkeypatch):
    spy = Mock(side_effect=AssertionError("encoding was reached"))
    monkeypatch.setattr(limits.json.JSONEncoder, "iterencode", spy)
    value = "invented"
    with pytest.raises(AdapterError, match="^INPUT_OPTION_BYTES_LIMIT$"):
        limits.validate_options([value, value], max_bytes=15)
    spy.assert_not_called()


@pytest.mark.parametrize("value", [True, False, None, 0, 1.25, {"x": "a\\b\n"}])
def test_ordinary_scalars_and_escaped_canonical_bytes(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    limits.validate_options(value, max_bytes=len(raw))
    if len(raw) > 1:
        with pytest.raises(AdapterError, match="^INPUT_OPTION_BYTES_LIMIT$"):
            limits.validate_options(value, max_bytes=len(raw) - 1)
