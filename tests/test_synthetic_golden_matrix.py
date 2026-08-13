"""Offline golden coverage for the entirely invented e-Gov structure matrix."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from jlegal_okf.egov import admit_egov_xml, egov_xml_adapter
from jlegal_okf.legal_okf import export_okf, validate_okf
from jlegal_okf.model import canonical_json
from jlegal_okf.pipeline import compile_corpus, read_crosswalk, read_jsonl, verify_manifest
from jlegal_okf.validation import collect_diagnostics


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/fixtures/synthetic_egov_structure_matrix.xml"
GOLDEN = ROOT / "examples/fixtures/synthetic_egov_structure_matrix.golden.json"
FIXTURE_LAW_ID = "SyntheticStructureMatrix001"
FIXED_CONVERTED_AT = "2026-08-09T00:00:00Z"
EXPECTED_COVERAGE = {
    "missing_article_numbers",
    "deleted_article",
    "branch_article",
    "implicit_first_paragraph",
    "iroha_subitems",
    "supplementary_provision",
    "appendix_table",
    "table_structure",
    "appendix_style",
    "multiple_effective_dates",
    "transitional_measure",
    "reference_sentence",
    "incorporation_sentence",
    "read_as_sentence",
    "delegation_sentence",
    "amendment_supplementary_provision",
}
REFERENCE_TEXT = "第三条の二の規定を参照する。"
INCORPORATION_TEXT = "第三条の二の規定を準用する。"
READ_AS_TEXT = "この法律中「甲」とあるのは「乙」と読み替える。"
DELEGATION_TEXT = "必要な事項は、架空規則で定める。"
EFFECTIVE_DATES_TEXT = "この法律は、令和二年四月一日及び令和二年五月一日に施行する。"


def _golden() -> dict[str, object]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _attributes(node: dict[str, object]) -> dict[str, str]:
    return node["attributes"]  # type: ignore[return-value]


def _children(nodes: list[dict[str, object]], parent: dict[str, object]) -> list[dict[str, object]]:
    return [node for node in nodes if node["parent_id"] == parent["node_id"]]


def _first(nodes: list[dict[str, object]], **fields: object) -> dict[str, object]:
    matches = [node for node in nodes if all(node[key] == value for key, value in fields.items())]
    assert len(matches) == 1, (fields, len(matches))
    return matches[0]


def _identity_sha256(nodes: list[dict[str, object]]) -> str:
    identity = [
        {key: node[key] for key in ("node_id", "version_id", "kind", "locator", "parent_id")}
        for node in nodes
    ]
    return hashlib.sha256(canonical_json(identity)).hexdigest()


def test_structure_matrix_matches_fixed_golden_and_replays_from_bundle(tmp_path: Path) -> None:
    golden = _golden()
    assert set(golden) == {
        "schema",
        "fixture",
        "authorship",
        "corpus_id",
        "converted_at",
        "coverage_ids",
        "source_bytes",
        "source_sha256",
        "expected_node_count",
        "projection_count",
        "kind_counts",
        "node_identity_sha256",
        "artifact_sha256",
        "bundle_manifest_sha256",
        "bundle_file_entry_count",
    }
    assert golden["schema"] == "jlegal-synthetic-golden/v1"
    assert golden["fixture"] == "examples/fixtures/synthetic_egov_structure_matrix.xml"
    assert golden["authorship"] == "entirely-invented"
    assert golden["corpus_id"] == "synthetic-egov-structure-matrix"
    assert golden["converted_at"] == FIXED_CONVERTED_AT
    coverage_ids = golden["coverage_ids"]
    assert isinstance(coverage_ids, list)
    assert len(coverage_ids) == 16
    assert len(set(coverage_ids)) == 16
    assert set(coverage_ids) == EXPECTED_COVERAGE

    source_bytes = FIXTURE.read_bytes()
    assert golden["source_bytes"] == len(source_bytes)
    assert golden["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    admission = admit_egov_xml(FIXTURE, law_id=FIXTURE_LAW_ID)
    admission_report = admission.report(accepted=True, receipt_verified=False)
    assert admission_report["accepted"] is True
    assert admission_report["official_law_id"] == "SyntheticStructureMatrix001"
    assert admission_report["diagnostics"] == []

    first_dir = tmp_path / "corpus-one"
    second_dir = tmp_path / "corpus-two"
    first = compile_corpus(
        FIXTURE,
        adapter="egov_xml",
        corpus_id=str(golden["corpus_id"]),
        mapping={"law_id": FIXTURE_LAW_ID},
        out_dir=first_dir,
        converted_at=FIXED_CONVERTED_AT,
    )
    second = compile_corpus(
        FIXTURE,
        adapter="egov_xml",
        corpus_id=str(golden["corpus_id"]),
        mapping={"law_id": FIXTURE_LAW_ID},
        out_dir=second_dir,
        converted_at=FIXED_CONVERTED_AT,
    )
    artifact_names = ("corpus.jsonl", "crosswalk.jsonl", "projection.jsonl", "manifest.json")
    for name in artifact_names:
        first_bytes = (first_dir / name).read_bytes()
        assert first_bytes == (second_dir / name).read_bytes(), name
        assert hashlib.sha256(first_bytes).hexdigest() == golden["artifact_sha256"][name]

    nodes = _records(first_dir / "corpus.jsonl")
    projections = _records(first_dir / "projection.jsonl")
    assert len(nodes) == golden["expected_node_count"]
    assert len(projections) == golden["projection_count"]
    assert Counter(node["kind"] for node in nodes) == golden["kind_counts"]
    assert _identity_sha256(nodes) == golden["node_identity_sha256"]
    assert len({node["node_id"] for node in nodes}) == len(nodes)
    assert len({node["version_id"] for node in nodes}) == len(nodes)
    assert len({node["locator"] for node in nodes}) == len(nodes)
    assert all(node["parent_id"] is None or any(parent["node_id"] == node["parent_id"] for parent in nodes) for node in nodes)
    assert all(
        node["source"]["sha256"] == golden["source_sha256"]
        and node["source"]["uri"] == f"jlegal:source:sha256:{golden['source_sha256']}"
        and len(node["attributes"]["build_provenance_sha256"]) == 64
        for node in nodes
    )

    manifest = verify_manifest(
        first_dir / "corpus.jsonl",
        first_dir / "manifest.json",
        first_dir / "crosswalk.jsonl",
        first_dir / "projection.jsonl",
        verify_inputs=True,
        source=FIXTURE,
    )
    assert manifest["schema"] == "jori-manifest/v5"
    assert manifest["adapter"] == "egov_xml"
    assert manifest["adapter_version"] == "1"
    assert manifest["conversion"] == {
        "name": "JORI Engine",
        "profile": "J-LEGAL-OKF/0.1.0-draft",
        "version": "0.1.0-draft",
    }
    assert manifest["acquisition"]["schema"] == "jlegal-egov-acquisition/v1"
    assert manifest["converted_at"] == FIXED_CONVERTED_AT
    assert manifest["acquisition"]["rights"] is None
    assert manifest["acquisition"]["source_url"] is None
    assert manifest["acquisition"]["retrieved_at"] is None
    assert manifest["node_count"] == len(nodes)
    assert manifest["projection_count"] == len(projections)
    assert manifest["inputs"] == [
        {
            "role": "mapping",
            "sha256": hashlib.sha256(canonical_json({"law_id": FIXTURE_LAW_ID})).hexdigest(),
            "uri": "inline:canonical-json-v1",
        },
        {
            "role": "source",
            "sha256": golden["source_sha256"],
            "uri": f"jlegal:source:sha256:{golden['source_sha256']}",
        },
    ]
    assert collect_diagnostics(read_jsonl(first_dir / "corpus.jsonl"), read_crosswalk(first_dir / "crosswalk.jsonl")) == ()

    bundle_one = Path(export_okf(first_dir / "corpus.jsonl", first_dir / "manifest.json", tmp_path / "bundle-one", source=FIXTURE)["bundle"])
    bundle_two = Path(export_okf(second_dir / "corpus.jsonl", second_dir / "manifest.json", tmp_path / "bundle-two", source=FIXTURE)["bundle"])
    assert validate_okf(bundle_one)["valid"] is True
    assert validate_okf(bundle_one, verify_source=True)["source_reverified"] is True
    assert (bundle_one / "references/source.xml").read_bytes() == source_bytes
    bundle_manifest = json.loads((bundle_one / "manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((bundle_one / "manifest.json").read_bytes()).hexdigest() == golden["bundle_manifest_sha256"]
    assert len(bundle_manifest["files"]) == golden["bundle_file_entry_count"]
    assert not any(path.name.lower().startswith("edge") for path in bundle_one.rglob("*"))
    first_files = sorted(path.relative_to(bundle_one) for path in bundle_one.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(bundle_two) for path in bundle_two.rglob("*") if path.is_file())
    assert first_files == second_files
    for relative in first_files:
        assert (bundle_one / relative).read_bytes() == (bundle_two / relative).read_bytes(), relative

    by_projection_version = {node["version_id"]: node for node in projections}
    source_concepts = {
        node["version_id"]: (bundle_one / "source" / f"{node['version_id']}.md").read_text(encoding="utf-8")
        for node in nodes
    }

    def text_is_preserved(value: str) -> None:
        matches = [node for node in nodes if node["text"] == value]
        assert len(matches) == 1
        node = matches[0]
        assert by_projection_version[node["version_id"]]["text"] == value
        assert value in source_concepts[node["version_id"]]

    law = _first(nodes, kind="law")
    main = _first(nodes, kind="main_provision")
    main_articles = [node for node in _children(nodes, main) if node["kind"] == "article"]
    suppl = [node for node in nodes if node["kind"] == "supplementary_provision"]
    assert len(suppl) == 2

    checks = {
        "missing_article_numbers": lambda: assert_article_numbers(main_articles),
        "deleted_article": lambda: assert_deleted_article(main_articles, by_projection_version, source_concepts),
        "branch_article": lambda: assert_branch_article(main_articles),
        "implicit_first_paragraph": lambda: assert_implicit_paragraph(nodes, main_articles),
        "iroha_subitems": lambda: assert_iroha(nodes),
        "supplementary_provision": lambda: assert_supplementary_provision(suppl, law),
        "appendix_table": lambda: assert_appendix_table(nodes, law),
        "table_structure": lambda: assert_table_structure(nodes),
        "appendix_style": lambda: assert_appendix_style(nodes, law),
        "multiple_effective_dates": lambda: assert_effective_dates(nodes),
        "transitional_measure": lambda: assert_transition(nodes),
        "reference_sentence": lambda: text_is_preserved(REFERENCE_TEXT),
        "incorporation_sentence": lambda: text_is_preserved(INCORPORATION_TEXT),
        "read_as_sentence": lambda: text_is_preserved(READ_AS_TEXT),
        "delegation_sentence": lambda: text_is_preserved(DELEGATION_TEXT),
        "amendment_supplementary_provision": lambda: assert_amendment(suppl, nodes, by_projection_version, source_concepts),
    }
    assert set(checks) == EXPECTED_COVERAGE
    for coverage_id in coverage_ids:
        checks[coverage_id]()


def assert_article_numbers(articles: list[dict[str, object]]) -> None:
    assert sorted((article["ordinal"], article["branch"]) for article in articles) == [(1, []), (3, [2]), (5, [])]
    assert {article["ordinal"] for article in articles}.isdisjoint({2, 4})


def assert_deleted_article(articles: list[dict[str, object]], projections: dict[str, dict[str, object]], concepts: dict[str, str]) -> None:
    article = _first(articles, ordinal=5)
    assert _attributes(article)["Delete"] == "true"
    assert article["text"] == "（削除）"
    assert projections[article["version_id"]]["text"] == "（削除）"
    assert "（削除）" in concepts[article["version_id"]]


def assert_branch_article(articles: list[dict[str, object]]) -> None:
    article = _first(articles, ordinal=3)
    assert article["branch"] == [2]
    assert article["locator"].endswith("/article/article-3-2")
    assert article["node_id"] != _first(articles, ordinal=1)["node_id"]


def assert_implicit_paragraph(nodes: list[dict[str, object]], articles: list[dict[str, object]]) -> None:
    article_one = _first(articles, ordinal=1)
    paragraphs = [node for node in _children(nodes, article_one) if node["kind"] == "paragraph"]
    assert len(paragraphs) == 1
    assert paragraphs[0]["ordinal"] == 1
    assert "第1項" not in paragraphs[0]["text"]
    article_xml = ET.parse(FIXTURE).getroot().find("./LawBody/MainProvision/Article[@Num='1']")
    assert article_xml is not None
    paragraph_xml = article_xml.find("Paragraph")
    assert paragraph_xml is not None and paragraph_xml.attrib["Num"] == "1"
    paragraph_num_xml = paragraph_xml.find("ParagraphNum")
    assert paragraph_num_xml is not None and paragraph_num_xml.text in (None, "")
    branch_article = _first(articles, ordinal=3)
    assert _first([node for node in _children(nodes, branch_article) if node["kind"] == "paragraph"], ordinal=1)


def assert_iroha(nodes: list[dict[str, object]]) -> None:
    item = _first(nodes, kind="item", ordinal=1)
    subitems = [node for node in _children(nodes, item) if node["kind"] == "subitem"]
    assert {(node["ordinal"], node["label"], node["parent_id"]) for node in subitems} == {
        (1, "イ", item["node_id"]),
        (2, "ロ", item["node_id"]),
        (3, "ハ", item["node_id"]),
    }
    assert len({node["node_id"] for node in subitems}) == 3


def assert_supplementary_provision(supplementary: list[dict[str, object]], law: dict[str, object]) -> None:
    first = _first(supplementary, heading="附則")
    assert first["parent_id"] == law["node_id"]
    assert first["heading"] == "附則"
    assert first["ordinal"] is None
    assert not any(key.lower().startswith("amend") for key in _attributes(first))


def assert_appendix_table(nodes: list[dict[str, object]], law: dict[str, object]) -> None:
    appendix = _first(nodes, kind="appendix", ordinal=1, heading="別表第一")
    assert appendix["parent_id"] == law["node_id"]
    assert appendix["heading"] == "別表第一"
    assert _attributes(appendix)["egov_tag"] == "AppdxTable"


def assert_table_structure(nodes: list[dict[str, object]]) -> None:
    tables = [node for node in nodes if node["kind"] == "table"]
    assert len(tables) == 2
    for table in tables:
        rows = [node for node in _children(nodes, table) if node["kind"] == "row"]
        assert len(rows) == 2
        assert all([node for node in _children(nodes, row) if node["kind"] == "cell"] for row in rows)
        assert all(node["text"] for row in rows for node in _children(nodes, row))
        assert any("本文" in node["text"] for row in rows for node in _children(nodes, row)) or any(
            "合成" in node["text"] for row in rows for node in _children(nodes, row)
        )


def assert_appendix_style(nodes: list[dict[str, object]], law: dict[str, object]) -> None:
    styles = [node for node in _children(nodes, law) if node["kind"] == "appendix" and _attributes(node)["egov_tag"] == "AppdxStyle"]
    assert len(styles) == 1
    assert styles[0]["ordinal"] == 1
    assert styles[0]["heading"] == "様式第一"
    assert "様式の本文を原文どおり保持する。" in styles[0]["text"]
    assert "form" not in {node["kind"] for node in nodes}


def assert_effective_dates(nodes: list[dict[str, object]]) -> None:
    text_is_exact = [node for node in nodes if node["text"] == EFFECTIVE_DATES_TEXT]
    assert len(text_is_exact) == 1
    assert text_is_exact[0]["temporal"] == {
        "valid_from": None,
        "valid_to": None,
        "promulgated": "2020-01-02",
        "repealed": None,
    }


def assert_transition(nodes: list[dict[str, object]]) -> None:
    article = _first(nodes, kind="article", ordinal=2, heading="（経過措置）")
    supplementary = _first(nodes, kind="supplementary_provision", heading="附則")
    assert article["parent_id"] == supplementary["node_id"]
    assert "この法律の施行前にした行為については、なお従前の例による。" in article["text"]


def assert_amendment(
    supplementary: list[dict[str, object]],
    nodes: list[dict[str, object]],
    projections: dict[str, dict[str, object]],
    concepts: dict[str, str],
) -> None:
    amended = next(node for node in supplementary if node["heading"] == "改正附則")
    attrs = _attributes(amended)
    assert attrs["AmendLawNum"] == "架空改正法（令和二年法律第一号）"
    assert "AmendLawId" not in attrs
    assert "AmendRevisionId" not in attrs
    provision = _first(nodes, kind="amendment_provision")
    assert provision["parent_id"] is not None
    assert provision["node_id"] != amended["node_id"]
    assert provision["version_id"] in projections
    assert projections[provision["version_id"]]["text"] == "この改正附則は、架空の改正を定める。"
    assert "この改正附則は、架空の改正を定める。" in concepts[provision["version_id"]]


def test_appendix_same_number_same_parent_uses_source_tag_identity() -> None:
    law_body = ET.parse(FIXTURE).getroot().find("LawBody")
    assert law_body is not None
    raw_appendices = [child for child in law_body if child.tag in {"AppdxTable", "AppdxStyle"}]
    assert [(child.tag, child.attrib.get("Num")) for child in raw_appendices] == [("AppdxTable", "1"), ("AppdxStyle", "1")]

    adaptation = egov_xml_adapter(FIXTURE, mapping={"law_id": FIXTURE_LAW_ID})
    appendices = [node for node in adaptation.nodes if node.kind.value == "appendix"]
    assert len(appendices) == 2
    assert {dict(node.attributes)["egov_tag"] for node in appendices} == {"AppdxTable", "AppdxStyle"}
    assert {node.ordinal for node in appendices} == {1}
    assert len({node.parent_id for node in appendices}) == 1
    assert {node.locator for node in appendices} == {
        "/law/root/appendix/appendix-appdxtable-1",
        "/law/root/appendix/appendix-appdxstyle-1",
    }
    assert len({node.node_id for node in appendices}) == 2
    assert len({node.version_id for node in appendices}) == 2
