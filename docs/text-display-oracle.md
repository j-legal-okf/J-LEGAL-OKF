# Fixed character-data and display oracle

[text-display-oracle.json](../examples/conformance/text-display-oracle.json)
contains entirely invented XML fragments and display-field examples. Its
`jlegal-text-display-oracle/v1` schema names this fixture format, not a new
canonical wire format. These are fixed expectations authored in D04-A, the
oracle preparation step. Their fixture-only tests remain unchanged. The separate
D04-B acceptance tests now connect these literals to the producer and checker
under [profile 0.3.0-draft](jlegal-okf-profile-0.3.0-draft.md); fixture acceptance
alone does not establish producer conformance.

## Authority and scope

The character-data rule is
[`JLEGAL-TEXT-PRESERVE-1`](jlegal-okf-profile-0.2.0-draft.md#preservation-levels),
clarified by `DB-TEXT-1` in the
[deterministic contract](deterministic-bundle-contract.md#character-data-and-display-grammar).
That contract also defines the `DB-DISPLAY-1` grammar and `DB-ORACLE-1`'s
separation between source-authored expectations and producer observations.
Every `expected_text` and `expected_body` is a fixed literal. The test reads
the authored XML character-data slots and checks the published display grammar;
it neither imports a producer/checker nor generates or rewrites expectations.
Converter output, regenerated goldens, and a model's answer are not authorities
for these expected values. The authority is the stated rule applied to the
visible, fixed source characters and canonical-field inputs.

The fragments are not complete laws and are not claimed to conform to an e-Gov
XML Schema. They exercise only the listed character-data operations. The display
inputs contain only the fields needed by the grammar, not complete canonical
records; their well-formed example `version_id` is a marker binding, not a
computed node identity. Neither set measures real-law coverage, legal meaning,
source authenticity, or arbitrary-input conformance. The seven existing
conformance cases, their expected records, and historical goldens are unchanged.
Unsupported nontrivial structures and `NewProvision` remain outside the reviewed
acceptance scope.

## Character-data slots

The root has path `0`; its zero-based child `n` has path `0/n`. Each element has
two slots: `:text` before its children and `:tail` after its closing tag. The test
enumerates every slot, including absent slots as empty strings, in document
order. A `:text` slot is owned by that element. A `:tail` slot is owned by its
parent, not by the element named in the slot path. The root's tail has no owner.

`formatting_slots` explicitly lists the only omitted slots. Every listed path
must exist once, its value must be nonempty and contain only XML `S` characters
(U+0020, U+0009, U+000D, U+000A), and its owner must have children and be one of
`Article`, `Paragraph`, `ParagraphSentence`, `Table`, `TableRow`, `TableColumn`,
or `StyleStruct`. This fixture deliberately uses that bounded subset of the
profile's structural tags. The test also checks that every eligible formatting
slot in these examples is listed. All other slots are concatenated unchanged.

`Sentence`, `Ruby`, and mixed-content `TableHeaderColumn` are not formatting
owners. A leaf `TableColumn` keeps its whitespace even though a non-leaf
`TableColumn` may omit its own formatting. A parent never omits character data
already contributed by descendants. No stripping, Unicode normalization, case
folding, inferred punctuation, or insertion of XML markup is involved.

The following table explains each expectation; backslash sequences denote code
points, as in JSON, and do not mean literal backslashes in the expected value.
The fixture retains each complete authored XML fragment, including attributes.

| Case | Fixed expected text | Source basis |
| --- | --- | --- |
| `style` | `abc` | The `Style` text contributes characters, not its tags. |
| `ruby` | `ABCD` | Sentence text, Ruby text, Rt text, then Ruby tail. |
| `sup-sub` | `A2B3C` | Sup/Sub text and following tails stay in source order. |
| `empty-cell` | `""` | A self-closing element contributes no characters. |
| `leaf-whitespace` | `" \n  "` | A leaf owns all of its whitespace. |
| `structural-whitespace` | `x` | Only four explicitly listed formatting slots are omitted. |
| `unicode-whitespace` | `"\u3000a\u00a0  b\u3000"` | U+3000, NBSP, and both interior spaces remain. |
| `character-references` | `A&B C` | The XML parser expands `&amp;` and `&#x20;`. |
| `mixed-tails` | `ABC D2 E` | The Ruby and Sup tails retain their leading spaces. |
| `table-leaf-whitespace` | `" x"` | The first cell's leaf space survives every ancestor; five parent formatting slots are omitted. |
| `header-mixed-whitespace` | `" BC "` | Both header spaces are mixed character data. |
| `unicode-not-normalized` | `"e\u0301 \uff21"` | Combining acute and full-width A are not normalized. |
| `xml-newlines` | `"A\nB\rC"` | Literal XML CRLF becomes LF; `&#xD;` contributes CR. |
| `line-attribute` | `ABC` | Line text followed by its tail; `Style="solid"` remains in XML. |

For `structural-whitespace`, `0:text` and `0/0:tail` belong to `Article`;
`0/0:text` and `0/0/0:tail` belong to `Paragraph`. For
`table-leaf-whitespace`, `0:text` and `0/0:tail` belong to `Table`, while
`0/0:text`, `0/0/0:tail`, and `0/0/1:tail` belong to `TableRow`. The retained
leaf space is `0/0/0:text`, owned by the first `TableColumn`.

XML parser newline handling and character-reference expansion define parsed
character data, not the original bytes. `A\r\nB&#xD;C` and `A\nB\rC` are not
the same source byte sequence. `JLEGAL-BYTE-PRESERVE-1` must be checked separately
against the retained original XML bytes, never by reserializing a parsed tree.

## Complete display bodies

The seven display cases cover a heading that takes precedence over label and
locator, empty text, whitespace-only text, empty-heading label fallback,
absent-heading/empty-label locator fallback, preserved CRLF and CR in canonical
text, and literal same-version begin/end marker strings in the payload.
Canonical display text is already parsed character data: its CRLF and CR must
survive unchanged; XML input newline processing must not be applied to it again.

The first nonempty `heading`, `label`, or `locator` is the title, without further
trimming. `DB-DISPLAY-1` defines the complete decoded body as:

```text
begin = "<!-- jlegal-source:" + version_id + ":begin -->"
end   = "<!-- jlegal-source:" + version_id + ":end -->"
body  = "# " + title + "\n\n## Source text\n\n" + begin + text + end + "\n"
```

Each `expected_body` is written out in full in JSON. The test compares it with
this grammar and locates payload boundaries by their constructed positions and
the known text length. It does not split at the first marker occurrence. A
payload may contain the identical begin/end strings; those characters are data.
The test changes framing versions separately, removes either or both framing
markers, changes title or payload, adds prose before/after, and removes the final
newline. Every changed body must differ from the fixed complete body. The CR
case additionally rejects newline normalization of the expected body.

This is a stored-character contract, not a guarantee about a Markdown renderer's
visual output. Consumers must display the source as text without executing or
reinterpreting it as HTML or instructions.

## D04-B validation boundary

The original XML retains hierarchy, order, Ruby/Rt boundaries, and attributes
such as `Line Style="solid"`. Text alone cannot recover those distinctions: the
same `ABC` could arise with or without Line markup. D04-B independently
compares original source bytes and the reviewed canonical structure/attributes;
passing these string comparisons cannot substitute for either check. Any claim
about full-law schema validity needs separately validated full-law inputs.

D04-B's `tests/test_text_display_contract.py` exercises the corrected producer
against these fixed values and both display validators against independently
authored complete-body mutations. It checks storage/read/validation at the
grammar boundary, including CRLF, CR, empty/whitespace payloads and literal
markers. A full compile/export/source-replay check additionally uses a
schema-validated variant of the existing matrix with `&#xD;` appended to the
first Sentence. The variant is generated temporarily, not added as a new source
file. Two further schema-validated variants put CR or CRLF inside LawTitle and
check preservation through the generated index and source-reverified validation.
Resealing an index after changing those characters to LF must still fail the
exact-index check. Literal same-version markers remain grammar-boundary examples, not a
claim of a self-referential complete-law artifact.

The profile 0.2.0-draft renderer's Style/Ruby/Sup/Sub markup emission and
source-body builder's literal-marker rejection were observed discrepancies,
not exceptions to this oracle. D04-A left those implementations unchanged.
D04-B corrects them and preserves CR/CRLF during concept decoding under the
[coordinated version transition](deterministic-bundle-contract.md#version-transition).
The old normative document, old golden, and this oracle's JSON and fixture-only
test remain byte-identical. Producer observations remain separate evidence.

## Run the fixture check

From a development checkout with its existing test environment:

```bash
python -B -m pytest -q -p no:cacheprovider tests/test_text_display_oracle.py
```

This single command checks the JSON's exact shape and case coverage, fixed
source inputs, character-data slots and omission boundaries, and literal display
grammar. It is not a CLI or library API for validating arbitrary submissions.
