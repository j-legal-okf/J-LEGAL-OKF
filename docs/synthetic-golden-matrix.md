# Synthetic structure-matrix golden

[`examples/fixtures/synthetic_egov_structure_matrix.xml`](../examples/fixtures/synthetic_egov_structure_matrix.xml)
is a completely invented, offline-only e-Gov-shaped XML document. It conforms
to the current official e-Gov Japanese-law XML Schema v3 when validated
against the schema downloaded from the official documentation page. It is a
regression fixture, not a law, a government publication, or a source for legal
use. Because the XSD does not define a `LawId` attribute, the regression passes
the synthetic admission ID explicitly as the reviewed adapter mapping. The companion
[`synthetic_egov_structure_matrix.golden.json`](../examples/fixtures/synthetic_egov_structure_matrix.golden.json)
is test-only data under the `jlegal-synthetic-golden/v1` schema.

## Contract

The fixture maps one-to-one to these coverage IDs:

1. `missing_article_numbers`
2. `deleted_article`
3. `branch_article`
4. `implicit_first_paragraph`
5. `iroha_subitems`
6. `supplementary_provision`
7. `appendix_table`
8. `table_structure`
9. `appendix_style`
10. `multiple_effective_dates`
11. `transitional_measure`
12. `reference_sentence`
13. `incorporation_sentence`
14. `read_as_sentence`
15. `delegation_sentence`
16. `amendment_supplementary_provision`

The test checks the XML shape, canonical node IDs and locators, parent/child
relations, node kinds, attributes, exact source text, projection text, source
concept text, acquisition values, and temporal values. It also verifies the
complete offline path:

```text
XML → corpus.jsonl → manifest.json → projection.jsonl
    → OKF bundle → embedded source.xml → source re-conversion
```

The fixed timestamp in the golden data makes the canonical artifact and bundle
bytes reproducible. The golden file is deliberately read-only from the test:
the test never regenerates or updates it. To change the fixture or golden
values, review the complete diff, recalculate the values in an isolated
temporary directory, and update the JSON explicitly.

The current public adapter retains multiple effective dates, references,
incorporation, read-as clauses, and delegation clauses as source text only. It
does not resolve them, infer legal meaning, populate validity windows from
them, or create relation edges. See
[`docs/known-limitations.md`](known-limitations.md).

The fixture also asserts that an explicit `<Paragraph Num="1"><ParagraphNum/>...`
keeps internal ordinal `1` while preserving an empty display number, and
that the three `Subitem1` labels イ・ロ・ハ remain distinct children. `AppdxTable`
and `AppdxStyle` intentionally share `Num="1"` under `LawBody`; their
canonical appendix locator segments include the source XML tag, so node and
version IDs remain distinct without changing the schema or UUID namespace.

## Offline check

From this repository root, run the focused regression:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_synthetic_golden_matrix.py
```

The test writes all conversion outputs below pytest's temporary directory and
does not place XML, canonical artifacts, bundles, or acquisition receipts in
the repository.

## Official XSD check

The XSD is not tracked. For an independent check, download the schema linked
by the [official e-Gov XML Schema documentation](https://laws.e-gov.go.jp/docs/law-data-basic/419a603-xml-schema-for-japanese-law/)
to a temporary directory and run `lxml.etree.XMLSchema` over this fixture. The
validation source must be the complete official `XMLSchemaForJapaneseLaw_v3.xsd`
file; remove the temporary schema and any validation outputs after the check.
