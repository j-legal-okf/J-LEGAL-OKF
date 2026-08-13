from __future__ import annotations

import json
from pathlib import Path

import pytest

from jlegal_okf.adapters import AdapterRegistry, default_registry
from jlegal_okf.errors import AdapterError


def _raw_tree(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "jurisdiction": "Example",
                "authority": "Act",
                "law_number_key": "1",
                "nodes": [
                    {
                        "locator": "law",
                        "kind": "law",
                        "text": "Invented root",
                        "children": [
                            {
                                "locator": "article-1",
                                "kind": "article",
                                "text": "Invented article",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _xml_mapping() -> dict[str, object]:
    return {
        "row": "x",
        "fields": {
            "jurisdiction": "j",
            "authority": "a",
            "law_number_key": "n",
            "locator": "l",
            "kind": "k",
            "depth": {"path": "d", "type": "int"},
            "parent_locator": "p",
            "ordinal": {"path": "o", "type": "int"},
            "text": "t",
        },
    }


def test_raw_json_tree_expands_parent_ids(tmp_path: Path) -> None:
    nodes = default_registry().adapt(_raw_tree(tmp_path / "raw.json"), name="json").nodes

    assert len(nodes) == 2
    assert nodes[1].parent_id == nodes[0].node_id


def test_json_and_xml_reject_whitespace_identity_keys(tmp_path: Path) -> None:
    raw_json = {
        "jurisdiction": "Example",
        "authority": "Act",
        "law_number_key": "  ",
        "source_law_key": "invented",
        "nodes": [{"locator": "law", "kind": "law", "text": "Invented"}],
    }
    json_path = tmp_path / "bad.json"
    json_path.write_text(json.dumps(raw_json), encoding="utf-8")

    with pytest.raises(ValueError):
        default_registry().adapt(json_path, name="json")

    xml_path = tmp_path / "bad.xml"
    xml_path.write_text(
        "<r><x><j>Example</j><a>Act</a><n> </n><l>law</l>"
        "<k>law</k><d>0</d><t>Invented</t></x></r>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        default_registry().adapt(xml_path, name="xml", mapping=_xml_mapping())


def test_json_suffix_is_sniffed(tmp_path: Path) -> None:
    assert default_registry().adapt(_raw_tree(tmp_path / "source.json")).adapter == "json"


def test_unknown_adapter_and_unrecognized_input_fail_closed(tmp_path: Path) -> None:
    registry = default_registry()

    with pytest.raises(AdapterError, match="ADAPTER_UNKNOWN"):
        registry.adapt(tmp_path / "unknown", name="not-an-adapter")

    text_path = tmp_path / "input.txt"
    text_path.write_text("invented", encoding="utf-8")
    with pytest.raises(AdapterError, match="ADAPTER_UNRECOGNIZED"):
        registry.adapt(text_path)


def test_xml_mapping_preserves_typed_ordinal_and_hierarchy(tmp_path: Path) -> None:
    xml_path = tmp_path / "source.xml"
    xml_path.write_text(
        "<r>"
        "<x><j>Example</j><a>Act</a><n>1</n><l>law</l><k>law</k><d>0</d><t>Root</t></x>"
        "<x><j>Example</j><a>Act</a><n>1</n><l>article-1</l><k>article</k><d>1</d>"
        "<p>law</p><o>2</o><t>Invented article</t></x>"
        "</r>",
        encoding="utf-8",
    )

    nodes = default_registry().adapt(xml_path, name="xml", mapping=_xml_mapping()).nodes

    assert nodes[1].parent_id == nodes[0].node_id
    assert nodes[1].ordinal == 2


def test_html_adapter_requires_well_formed_xhtml(tmp_path: Path) -> None:
    html_path = tmp_path / "invalid.html"
    html_path.write_text("<p>", encoding="utf-8")

    with pytest.raises(AdapterError, match="ADAPTER_HTML_XHTML_REQUIRED"):
        default_registry().adapt(html_path, name="html", mapping=_xml_mapping())


def test_adapter_registry_rejects_duplicate_name_registration() -> None:
    """AdapterRegistry.register's `if name in self._adapters` guard is exactly
    ADAPTER_DUPLICATE; registering the same name twice on a fresh registry
    fires it directly, no bypass needed.
    """
    registry = AdapterRegistry()
    registry.register(
        "duplicate-name",
        lambda path, mapping: None,
        sniff=lambda path: False,
        priority=1,
    )
    with pytest.raises(AdapterError, match="ADAPTER_DUPLICATE: duplicate-name"):
        registry.register(
            "duplicate-name",
            lambda path, mapping: None,
            sniff=lambda path: False,
            priority=1,
        )
