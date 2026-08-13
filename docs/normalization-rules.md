# J-LEGAL-OKF Normalization Rule Catalog

## Status and scope

This catalog documents identifier and comparison-field normalization
behaviors that the reference implementation already applies on every
compile. Each rule has a stable ID in the `JLEGAL-NORM-*` series so future
changes to these behaviors are traceable and reviewable.

This catalog does **not** duplicate two things already documented
elsewhere in this profile:

- **Byte/text/display preservation** (`JLEGAL-BYTE-PRESERVE-1`,
  `JLEGAL-TEXT-PRESERVE-1`, `JLEGAL-DISPLAY-TRIM-1`) is normative in
  [`jlegal-okf-profile-0.1.0-draft.md`, "Preservation levels"](jlegal-okf-profile-0.1.0-draft.md#preservation-levels).
  Those rules govern how source bytes and `LegalNode.text` are preserved or
  trimmed; the rules below govern identifier and locator normalization, a
  distinct concern (identity/addressing, not content preservation), so they
  are catalogued separately and draw their IDs from a different series, as
  the "Preservation levels" section's closing paragraph requires.
- **Era/date derivation** (`_bare_promulgated`, `_envelope_promulgated` in
  `egov.py`) is out of scope here: it derives `Temporal.promulgated` from
  schema-defined Era/Year/Month/Day XML attributes rather than normalizing a
  designated comparison field, and it is already covered by the profile's
  ["Provenance, normalization, and validation policy"](jlegal-okf-profile-0.1.0-draft.md#provenance-normalization-and-validation-policy)
  section.

## Backward compatibility (applies to every rule below)

An existing `JLEGAL-NORM-*` rule ID's definition is never changed. A
behavior change to identifier or locator normalization requires a new rule
ID and a profile revision, mirroring the policy already stated for the
`JLEGAL-BYTE-PRESERVE-1` / `JLEGAL-TEXT-PRESERVE-1` / `JLEGAL-DISPLAY-TRIM-1`
series.

---

## `JLEGAL-NORM-1`: Identifier normalization

**Description**: canonical identifiers are Unicode-normalized (NFKC),
ASCII-whitespace-collapsed, and stripped before being hashed into a
`law_`/`node_`/`ver_` UUID; jurisdiction and authority are additionally
lowercased.

**Function**: `normalize_identifier()`, `src/jlegal_okf/model.py:21-24`.

```python
def normalize_identifier(value: str, *, authority_or_jurisdiction: bool = False) -> str:
    result = _WS.sub(" ", unicodedata.normalize("NFKC", value).strip())
    return result.lower() if authority_or_jurisdiction else result
```

`_WS` (`model.py:17`) is `re.compile(r"[\t\n\r\f\v ]+")` — tab, newline, CR,
FF, VT, and ASCII space only. The regex itself does not match U+3000
IDEOGRAPHIC SPACE. However, `unicodedata.normalize("NFKC", ...)` runs
*first* and NFKC's decomposition maps U+3000 to U+0020 (ASCII space) before
`_WS` and `.strip()` ever see it, so a full-width space at a normalized
identifier's edges is stripped, and interior full-width space runs are
collapsed, as an effect of NFKC rather than of `_WS` matching U+3000
directly. This is a real behavioral difference from `LegalNode.text`
(`JLEGAL-TEXT-PRESERVE-1`), where U+3000 is always source character data and
is never elided.

**Applies to** (all via `src/jlegal_okf/model.py`), with lowercasing noted
per call site — this is the complete set of `normalize_identifier()` call
sites in the package, including the three inside `semantic_locator()`
(`JLEGAL-NORM-4`):

| Field / call site | Function | `authority_or_jurisdiction` (lowercased?) |
| --- | --- | --- |
| `jurisdiction` | `law_identifier()` (`model.py:35`) | Yes |
| `authority` | `law_identifier()` (`model.py:36`) | Yes |
| `law_number_key` | `law_identifier()` (`model.py:39`) | No |
| `source_law_key` | `law_identifier()` (`model.py:43`) | No |
| `law_id` | `node_identifier()` (`model.py:50`) | No |
| `locator` | `node_identifier()` (`model.py:50`) | No |
| `node_id` | `version_identifier()` (`model.py:81`) | No |
| `segment` (locator slug) | `semantic_locator()` (`model.py:295`, `JLEGAL-NORM-4`) | Yes |
| `source_key` (locator hash fallback) | `semantic_locator()` (`model.py:300`, `JLEGAL-NORM-4`) | No |
| `segment` (locator hash prefix) | `semantic_locator()` (`model.py:302`, `JLEGAL-NORM-4`) | No |

`jurisdiction`, `authority`, and the locator `segment` sanitized at
`model.py:295` are the only call sites that pass
`authority_or_jurisdiction=True` and are therefore lowercased.
`law_number_key`, `source_law_key`, `law_id`, `locator`, `node_id`, and the
two other `normalize_identifier()` calls inside `semantic_locator()`
(`source_key` at `model.py:300`, `segment` again at `model.py:302`) are
NFKC-normalized and whitespace-collapsed but keep their original case.
`LegalNode.__post_init__` (`model.py:191`) applies the same function to
`jurisdiction`, `authority`, and `locator` again, but only to check they are
nonempty after normalization — it does not itself feed a hashed identifier.

**Never applied to** `LegalNode.text` or the source XML bytes. `text` is
produced by `_render_text` (`JLEGAL-TEXT-PRESERVE-1`) in
`src/jlegal_okf/egov.py`, falling back to `_element_xml(child)` only when
`_render_text` returns an empty string (`egov.py:634-635`) — `text` is never
passed to `normalize_identifier()` in either case.

**Verified examples** (run against this checkout, `.venv/bin/python`):

```
>>> normalize_identifier("Ａ  \t\nＢ")
'A B'
>>> normalize_identifier(" A ", authority_or_jurisdiction=True)
'a'
>>> normalize_identifier("　full-width　", authority_or_jurisdiction=True)
'full-width'
>>> normalize_identifier("ＬＡＷ-Ｎｏ．１２")          # law_number_key/source_law_key path: case preserved
'LAW-No.12'
```

---

## `JLEGAL-NORM-2`: Kanji-numeral conversion

**Description**: converts a Japanese kanji numeral string (e.g. `"十二"`,
`"二百三"`) into a nonnegative integer, for use only inside the ordinal/branch
fallback parsing described in `JLEGAL-NORM-3`.

**Function**: `_number_part()`, `src/jlegal_okf/egov.py:204-217`, using the
digit and unit tables at `egov.py:36-37`:

- `_KANJI_DIGITS` (`egov.py:36`): `〇一二三四五六七八九` → `0`-`9`.
- `_KANJI_UNITS` (`egov.py:37`): `十百千` → `10`/`100`/`1000`.

**Applies to**: only the kanji-text branch inside `_ordinal_branch()`
(`JLEGAL-NORM-3`), reached whenever `_ordinal_branch()` receives a value
that is not the plain-ASCII-digit or ASCII/full-width digit-hyphen form.
That value can come from either of `_node_number()`'s two sources
(`egov.py:242-253`): the structural element's own `Num` XML attribute,
when that attribute's *value itself* is kanji (e.g. `Num="第十二条の二"`,
verified: `_node_number()` applies `_ordinal_branch()` directly to the
attribute value at `egov.py:245`, with no dependence on whether `Num` is
present); or, only when no `Num` attribute is present or none of its
values parse to a non-`None` ordinal, the `{tag}Num`/`{tag}Title`/
`{tag}Label` child-element text fallback. There is no `{tag}Caption`
fallback — `_node_number()`'s suffix loop is exactly
`("Num", "Title", "Label")` (`egov.py:248`); `Caption` elements feed only
`_heading()`, a separate, unrelated function.

**Never applied to** `LegalNode.text` or the source XML bytes.

**Verified examples**:

```
>>> from jlegal_okf.egov import _number_part
>>> _number_part("十二")
12
>>> _number_part("二百三")
203
```

---

## `JLEGAL-NORM-3`: Ordinal/branch decomposition

**Description**: parses a raw article/paragraph/item number designation
into an `(ordinal: int, branch: tuple[int, ...])` pair. Branch numbers are
always kept as a tuple of integers, never collapsed into a decimal — `"12-2"`
is never treated as `"12.2"`.

**Function**: `_ordinal_branch()`, `src/jlegal_okf/egov.py:220-239`, using
`_NUMERIC_BRANCH` and `_JAPANESE_BRANCH` (`egov.py:38-39`).

**Applies to**: the `Num` attribute's own value, or (when `Num` is absent or
unparseable) the `{tag}Num`/`{tag}Title`/`{tag}Label` child-element text, of
any structural element — via `_node_number()` (`egov.py:242-253`), which
feeds `LegalNode.ordinal` and `LegalNode.branch` in `egov_xml_adapter()`.

Three input shapes:

1. ASCII digit-hyphen form, e.g. `"3-2"`, `"3_2"`, or `"3の2"` → `(3, (2,))`.
2. Plain ASCII digits, e.g. `"12"` → `(12, ())`.
3. Kanji form, e.g. `"第十二条の二"` → uses `JLEGAL-NORM-2` internally →
   `(12, (2,))`.

**Never applied to** `LegalNode.text` or the source XML bytes.

**Verified examples**:

```
>>> from jlegal_okf.egov import _ordinal_branch
>>> _ordinal_branch("3-2")
(3, (2,))
>>> _ordinal_branch("3_2")
(3, (2,))
>>> _ordinal_branch("3の2")
(3, (2,))
>>> _ordinal_branch("12")
(12, ())
>>> _ordinal_branch("第十二条の二")
(12, (2,))
```

Case (a) — ASCII digit-hyphen form — already has coverage in
`tests/test_regression_contracts.py`
(`test_egov_hierarchy_temporal_and_fail_closed_contracts`, `Num="3-2"` →
`article.branch == (2,)`). Case (c) — the kanji fallback — had zero test
coverage until `test_egov_kanji_numeral_ordinal_and_branch_fallback` was
added alongside this catalog (see the "Test coverage" section below).

---

## `JLEGAL-NORM-4`: Locator-segment sanitization

**Description**: builds a URL/path-safe locator path segment from a raw
child-element path key. There are three output forms, in this order of
precedence:

1. Ordinal known: `{kind.value}-{ordinal}[-{branch...}]` — the sanitized
   segment is computed but discarded.
2. Ordinal unknown, sanitized segment nonempty: `u-<hash16>-<safe[:32]>` —
   a 16-hex-character (64-bit) truncated SHA-256 digest of the
   *unsanitized* segment, followed by the sanitized segment itself
   truncated to 32 characters.
3. Ordinal unknown, sanitized segment empty: `u-<hash16>` — the same
   16-hex-character digest, but of a caller-supplied `source_key` instead
   (raises `LOCATOR_STABLE_SOURCE_KEY_REQUIRED` if no `source_key` is
   given).

The hash prefix in forms 2 and 3 makes same-input-same-locator stable and
makes two different unstable inputs collision-*resistant* — a 64-bit
truncated digest is not collision-*proof*.

**Function**: `semantic_locator()`, `src/jlegal_okf/model.py:293-304`. It
first applies `JLEGAL-NORM-1` (`normalize_identifier(segment,
authority_or_jurisdiction=True)` — NFKC + lowercase + whitespace-collapse),
then strips every character outside `[a-z0-9_-]` via
`re.sub(r"[^a-z0-9_-]+", "-", ...)` and trims leading/trailing `-`.

**Applies to**: locator path segments only, i.e. the `<segment>` component
of `/law/.../<kind>/<segment>` produced during `egov_xml_adapter()`'s tree
walk (`egov.py:636-644`).

**Never applied to** `LegalNode.text` or the source XML bytes.

**Verified examples**:

```
>>> semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "ignored", ordinal=3, branch=(2,))
'/law/root/article/article-3-2'
>>> semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "Ａ　条見出し！", ordinal=None)
'/law/root/article/u-94f04ddb5a629c5d-a'
>>> semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "", ordinal=None, source_key="fallback-key")
'/law/root/article/u-6823e438f494077c'
>>> semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "a" * 60, ordinal=None)
'/law/root/article/u-11ee391211c62564-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
```

The first example is the common case (ordinal known: no sanitization of the
raw segment is needed at all). The second sanitizes a segment that is mostly
non-ASCII to a single surviving character (`"a"`, from the NFKC-folded and
lowercased `"Ａ"`) and prefixes a content hash of the *unsanitized* segment
so the locator stays stable and collision-resistant even when the visible
slug is nearly empty. The third shows the pure content-hash fallback
(`"u-" + sha256(normalize_identifier(source_key))[:16]`) used when the
sanitized segment is empty and no ordinal is available. The fourth shows the
`safe[:32]` truncation in form 2 above: a 60-character sanitized segment
(`"a" * 60`) is cut to exactly 32 characters in the output, even though the
hash prefix alone would already make the locator unique.

---

## `JLEGAL-NORM-5`: Source-tagged appendix locator identity

**Description**: for every node whose canonical `NodeKind` is `APPENDIX`,
the locator's ordinal-known form (form 1 of `JLEGAL-NORM-4`) is extended
from `{kind.value}-{ordinal}[-{branch...}]` to
`{kind.value}-{normalized_tag}-{ordinal}[-{branch...}]`, where
`normalized_tag` is the sanitized form of the appendix's own source XML
local tag name. This is an unconditional rule keyed on node kind, applied on
every compile to every appendix node — **not** a conditional branch that
only changes the identifier when a sibling number collision is detected.
`AppdxTable Num="1"` and `AppdxStyle Num="1"` under the same parent get
distinct, source-tag-qualified locators regardless of whether a sibling with
the same `Num` happens to exist; a lone `AppdxStyle Num="1"` with no
`AppdxTable` sibling still gets `appendix-appdxstyle-1`, not the bare
`appendix-1` that `JLEGAL-NORM-4` alone would produce.

**Function**: `semantic_locator()`, `src/jlegal_okf/model.py:293-304`,
called with the additional `source_tag` keyword-only argument (already part
of the function's signature and covered by `JLEGAL-NORM-4`'s function
citation):

```python
def semantic_locator(law_id: str, parent_locator: str | None, kind: NodeKind, segment: str, *, ordinal: int | None = None, branch: tuple[int, ...] = (), source_key: str | None = None, title: str | None = None, source_tag: str | None = None) -> str:
    """Canonical AST path; adapters never preserve uncontrolled external locators."""
    safe = re.sub(r"[^a-z0-9_-]+", "-", normalize_identifier(segment, authority_or_jurisdiction=True)).strip("-")
    if ordinal is not None:
        if source_tag is not None:
            normalized_tag = re.sub(r"[^a-z0-9_-]+", "-", normalize_identifier(source_tag, authority_or_jurisdiction=True)).strip("-")
            if not normalized_tag:
                raise ValueError("LOCATOR_SOURCE_TAG_REQUIRED")
            safe = f"{kind.value}-{normalized_tag}-{ordinal}"
        else:
            safe = f"{kind.value}-{ordinal}"
        safe += ("-" + "-".join(str(x) for x in branch) if branch else "")
```

When `ordinal is not None` and `source_tag is not None`, `normalized_tag` is
computed by reusing `JLEGAL-NORM-1`'s `normalize_identifier(source_tag,
authority_or_jurisdiction=True)` (NFKC + lowercase + whitespace-collapse,
`model.py:295`'s own normalization call, applied here to `source_tag`
instead of `segment`), then applying the exact same sanitize step
`JLEGAL-NORM-4` uses for its own `segment` — `re.sub(r"[^a-z0-9_-]+", "-",
...)` followed by `.strip("-")`. If `normalized_tag` is empty after this
pipeline, `semantic_locator()` raises `ValueError("LOCATOR_SOURCE_TAG_REQUIRED")`
and no locator is produced (fail-closed). When `ordinal is not None` and
`source_tag is None`, behavior is unchanged from `JLEGAL-NORM-4`:
`safe = f"{kind.value}-{ordinal}"`, with no tag segment.

**Call site**: `egov_xml_adapter()`'s `visit_children()`,
`src/jlegal_okf/egov.py:636-645`:

```python
            locator = semantic_locator(
                root.law_id,
                parent.locator,
                kind,
                child_path,
                ordinal=ordinal,
                branch=branch,
                source_key=child_path,
                source_tag=tag if kind is NodeKind.APPENDIX else None,
            )
```

`tag` (`egov.py:622`) is `_local(child.tag)` — the source XML element's own
local tag name (namespace stripped), read directly off the child being
visited, before any kind-specific interpretation. The conditional
expression `tag if kind is NodeKind.APPENDIX else None` selects *whether*
`source_tag` is supplied at all, based solely on the node's classified
`NodeKind`; it does not inspect siblings, numbering, or collisions. Every
other `NodeKind` — `ARTICLE`, `PARAGRAPH`, `ITEM`, `TABLE`, `ROW`, `CELL`,
and so on — always receives `source_tag=None` at this call site and is
therefore untouched by this rule.

**Applies to**: every source XML element that `_NODE_TAGS`
(`src/jlegal_okf/egov.py:348-376`) classifies as `NodeKind.APPENDIX`. As of
this catalog entry that set is `Appdx`, `AppdxTable`, `AppdxStyle`,
`AppdxNote`, `AppdxFig`, `AppdxFormat`, `SupplProvisionAppdx`,
`SupplProvisionAppdxTable`, and `SupplProvisionAppdxStyle`. This rule is
defined on the `NodeKind.APPENDIX` kind, not on that enumerated tag list: if
a future revision adds another source tag to `_NODE_TAGS` mapped to
`NodeKind.APPENDIX`, that tag is automatically in scope for this rule with
no catalog update required, because the call site keys on `kind is
NodeKind.APPENDIX`, not on a tag name. The input domain fed to this rule is
always the raw, un-normalized local tag string `_local(child.tag)` — never a
display title, `Num` attribute, or any other derived value.

**Never applied to** `LegalNode.text` or the source XML bytes, exactly as
`JLEGAL-NORM-4`. This rule only changes the `<segment>` component of an
appendix node's own locator path.

**Effect on identity beyond the appendix node itself**: `node_identifier()`
(`model.py:50`) hashes `locator` directly, and `version_identifier()`
(`model.py:81`) hashes `node_id`, so a changed appendix locator changes both
that appendix's `node_id` and `version_id`. Every descendant of an appendix
node is located via `parent.locator` (`egov.py:638`, the `parent_locator`
argument threaded through `visit_children()`'s recursive walk), so an
appendix's descendant nodes — every row, cell, and nested structural node
under a numbered `AppdxTable`/`AppdxStyle`/etc. — also gets a changed
locator, and therefore a changed `node_id` and `version_id`, purely because
an ancestor's locator changed. This rule's effect is therefore not confined
to the appendix node itself; it propagates to the identity of every
numbered appendix's full subtree.

**Backward compatibility**: this behavior is already the production
implementation as of the current `main` branch of this repository; nothing
has been tagged or released, so there is no prior public identifier scheme
this entry migrates from or must remain compatible with. Consistent with
this catalog's "Backward compatibility" section above, `JLEGAL-NORM-5`'s own
definition — this locator form, this input domain, this fail-closed
behavior — is never changed once relied upon; a future change to
source-tagged appendix identity requires a new rule ID and a profile
revision, not an edit to this entry.

**Verified examples** (run against this checkout, `.venv/bin/python`):

```
>>> semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="AppdxTable")
'/law/root/appendix/appendix-appdxtable-1'
>>> semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="AppdxStyle")
'/law/root/appendix/appendix-appdxstyle-1'
>>> semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="Ａｐｐｄｘ Ｔａｂｌｅ")   # NFKC-folded, lowercased, sanitized
'/law/root/appendix/appendix-appdx-table-1'
>>> semantic_locator("law_x", "/law/root", NodeKind.APPENDIX, "ignored", ordinal=1, source_tag="　")   # normalizes to empty
Traceback (most recent call last):
    ...
ValueError: LOCATOR_SOURCE_TAG_REQUIRED
>>> semantic_locator("law_x", "/law/root", NodeKind.ARTICLE, "article", ordinal=3, branch=(2,))   # non-appendix kind: source_tag never passed, unaffected
'/law/root/article/article-3-2'
```

The compiled reference implementation exercises this rule through
`egov_xml_adapter()` rather than by calling `semantic_locator()` directly:
`tests/test_synthetic_golden_matrix.py::test_appendix_same_number_same_parent_uses_source_tag_identity`
compiles `AppdxTable Num="1"` and `AppdxStyle Num="1"` siblings under one
`LawBody` and asserts they receive locators
`/law/root/appendix/appendix-appdxtable-1` and
`/law/root/appendix/appendix-appdxstyle-1` with two distinct `node_id`s and
`version_id`s. `tests/test_regression_contracts.py` additionally covers
`semantic_locator()`'s `source_tag` argument directly (exact locator with a
tag, the unchanged non-tagged/non-appendix form, the fail-closed empty-tag
case, NFKC/lowercase/sanitize behavior, and sibling-order independence of
the resulting IDs) in the six `JLEGAL-NORM-5` tests listed in the "Test
coverage" section below.

---

## Test coverage

`JLEGAL-NORM-2` and `JLEGAL-NORM-3`'s kanji-numeral fallback path (case (c)
above) had no automated test anywhere in the suite before this catalog. A
new test, `test_egov_kanji_numeral_ordinal_and_branch_fallback`, was added
to `tests/test_regression_contracts.py` next to the existing
`test_egov_hierarchy_temporal_and_fail_closed_contracts` (which already
covers case (a)). It compiles a minimal e-Gov `<Article>` with no `Num`
attribute but with an `<ArticleTitle>第十二条の二</ArticleTitle>` child
through the public `egov_xml_adapter()` API and asserts the resulting
article node's `ordinal == 12` and `branch == (2,)`. The test fails if the
kanji-numeral branch of `_number_part`/`_ordinal_branch` is reverted to
ASCII-digits-only, since the article would then have `ordinal is None`.

`JLEGAL-NORM-5` is covered by six tests added to
`tests/test_regression_contracts.py` alongside the kanji-numeral test above:

- `test_semantic_locator_source_tag_produces_exact_appendix_locator` — calls
  `semantic_locator()` directly with `source_tag="AppdxTable"` /
  `"AppdxStyle"` and asserts the exact tag-qualified locator strings.
- `test_semantic_locator_without_source_tag_keeps_legacy_ordinal_form` —
  asserts the unchanged `{kind.value}-{ordinal}` form when `source_tag` is
  omitted, on both `NodeKind.ARTICLE` and `NodeKind.APPENDIX`.
- `test_semantic_locator_source_tag_fail_closed_on_empty_or_blank`
  (parametrized over `""`, `"   "`, and `"　"`) — asserts
  `ValueError("LOCATOR_SOURCE_TAG_REQUIRED")` for every source tag that
  normalizes to empty.
- `test_semantic_locator_source_tag_is_nfkc_lowercased_and_sanitized` —
  asserts the NFKC-fold/lowercase/sanitize pipeline on a full-width,
  space-separated tag.
- `test_source_tag_does_not_affect_non_appendix_compiled_locators` —
  compiles a minimal `Article`/`Paragraph` through `egov_xml_adapter()` and
  asserts their locators are unaffected and contain no `appendix` segment.
- `test_appendix_sibling_order_does_not_change_locators_or_node_ids` —
  compiles an `AppdxTable`-then-`AppdxStyle` document and an
  `AppdxStyle`-then-`AppdxTable` document and asserts both appendices'
  `{locator, node_id}` pairs are identical regardless of sibling order.
