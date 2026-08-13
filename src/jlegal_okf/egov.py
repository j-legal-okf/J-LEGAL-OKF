"""Official e-Gov Law API v2 acquisition and XML-to-canonical adaptation.

This module deliberately separates the only network boundary (``fetch_egov_xml``)
from the adapter.  ``egov_xml_adapter`` consumes an already-saved XML snapshot
only, so compilation, validation, export, and tests remain offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
import re
import stat
from typing import Any, Callable, Iterable
from urllib.parse import quote

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from .adapters import Adaptation, BuildInput
from .errors import AdapterError, JLegalError
from .model import LegalNode, NodeKind, SourceRef, Temporal, canonical_json, content_addressed_uri, semantic_locator
from .pipeline import _atomic_bytes


EGOV_API_V2 = "https://laws.e-gov.go.jp/api/2"
EGOV_SOURCE_AUTHORITY = "e-Gov 法令API Version 2"
EGOV_XML_FULL_TEXT_FORMAT = "e-Gov Law API v2 XML full-text response"
EGOV_ACQUISITION_SCHEMA = "jlegal-egov-acquisition/v1"
EGOV_ADMISSION_SCHEMA = "jlegal-egov-admission/v1"
EGOV_ADMISSION_PROFILE = "J-LEGAL-OKF/0.1.0-draft"
MAX_EGOV_XML_BYTES = 64 * 1024 * 1024

_KANJI_DIGITS = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUMERIC_BRANCH = re.compile(r"^(\d+)(?:[_\-‐－の](\d+))+$")
_JAPANESE_BRANCH = re.compile(r"(?:第)?([〇一二三四五六七八九十百千]+)(?:条|項|号|編|章|節|款|目)?(?:の([〇一二三四五六七八九十百千]+))?")
_ERA_YEAR_BASE = {"Meiji": 1867, "Taisho": 1911, "Showa": 1925, "Heisei": 1988, "Reiwa": 2018}
# e-Gov supplies an authoritative Gregorian date in API envelopes.  For bare
# XML, only dates unambiguous in the modern Gregorian era ranges are derived.
# Early Meiji dates stay unknown because Japan had not yet adopted Gregorian
# dating, so a simple offset would make an unsupported historical assertion.
_ERA_DATE_RANGES = {
    "Meiji": (date(1873, 1, 1), date(1912, 7, 30)),
    "Taisho": (date(1912, 7, 30), date(1926, 12, 25)),
    "Showa": (date(1926, 12, 25), date(1989, 1, 8)),
    "Heisei": (date(1989, 1, 8), date(2019, 5, 1)),
    "Reiwa": (date(2019, 5, 1), None),
}


@dataclass(frozen=True)
class EgovAdmission:
    """A checked saved e-Gov XML source, safe to pass to the adapter."""

    raw: bytes
    document: ET.Element
    law: ET.Element
    official_law_id: str
    input_kind: str
    source_sha256: str

    def report(self, *, accepted: bool, receipt_verified: bool, diagnostics: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            "accepted": accepted,
            "diagnostics": list(diagnostics),
            "input_kind": self.input_kind,
            "official_law_id": self.official_law_id,
            "profile": EGOV_ADMISSION_PROFILE,
            "receipt_verified": receipt_verified,
            "schema": EGOV_ADMISSION_SCHEMA,
            "source_bytes": len(self.raw),
            "source_sha256": self.source_sha256,
        }


def _local(value: str) -> str:
    """Return an XML local name without requiring one namespace convention."""
    return value.rsplit("}", 1)[-1].split(":")[-1]


def _iter_named(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (item for item in element.iter() if _local(item.tag) == name)


def _first_named(element: ET.Element, name: str) -> ET.Element | None:
    return next(_iter_named(element, name), None)


def _direct_named(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element if _local(item.tag) == name), None)


def _attribute(element: ET.Element, name: str) -> str | None:
    return next((value for key, value in element.attrib.items() if _local(key) == name), None)


def _plain_text(element: ET.Element | None) -> str:
    """Display/comparison-field text: trimmed character data, rule ``JLEGAL-DISPLAY-TRIM-1``.

    See the profile's "Preservation levels" section. It feeds ``heading``,
    ``label``, titles, the envelope ``law_id``, ``LawNum`` (which becomes
    ``source_metadata["law_number"]``), the envelope promulgation date, the
    API error code, and branch/ordinal number parsing -- never
    ``LegalNode.text`` itself, which ``_render_text`` alone defines without
    any trimming. Unlike ``_render_text``, this renders character data only:
    an inline element such as Ruby contributes its own text, never an XML
    snippet, matching what ``element.itertext()`` produced before this
    function was made content-model aware.
    """
    if element is None:
        return ""
    return _character_data(element).strip()


def _element_xml(element: ET.Element) -> str:
    """Serialize an inline element without serializing its parent-owned tail."""
    tail = element.tail
    try:
        element.tail = None
        return ET.tostring(element, encoding="unicode", short_empty_elements=False)
    finally:
        element.tail = tail


# XML 1.0's S (whitespace) production is exactly space, tab, CR, LF.
# Deliberately not str.strip() with no arguments: that is Unicode-aware and
# also strips U+3000 IDEOGRAPHIC SPACE, U+00A0, and other Unicode spaces that
# are source character data, not XML formatting.
_XML_WHITESPACE = " \t\r\n"


def _is_xml_formatting(value: str) -> bool:
    """True when value is nonempty and consists solely of XML S-production whitespace."""
    return value != "" and value.strip(_XML_WHITESPACE) == ""


def _walk_text(element: ET.Element, render_child: Callable[[ET.Element], str]) -> str:
    """Shared content-model-aware walk behind ``_render_text`` and ``_character_data``.

    When ``element``'s local tag is in ``_STRUCTURAL_TAGS`` (an element-only
    content model) and it has at least one child element, a text node
    directly inside it (``element.text``, or a child's ``tail``) that is
    entirely XML S-production whitespace (see ``_is_xml_formatting``) is XML
    formatting and is not emitted. A text node with any non-whitespace
    character -- including a full-width or other Unicode space that is not in
    the XML S production -- is always emitted verbatim, character for
    character, regardless of ``_STRUCTURAL_TAGS`` membership. A leaf element,
    or an element not in ``_STRUCTURAL_TAGS``, has every one of its text
    nodes emitted verbatim. This never rewrites source character data; it
    only omits the XML S-production whitespace that the content model
    guarantees is layout, not source text. ``render_child`` decides how each
    child element itself contributes: verbatim XML markup for an inline/
    unknown leaf (``_render_text``), or character data only (``_character_data``).
    """
    tag = _local(element.tag)
    drop_formatting = tag in _STRUCTURAL_TAGS and len(element) > 0
    pieces: list[str] = []
    own_text = element.text or ""
    if not (drop_formatting and _is_xml_formatting(own_text)):
        pieces.append(own_text)
    for child in element:
        pieces.append(render_child(child))
        tail = child.tail or ""
        if not (drop_formatting and _is_xml_formatting(tail)):
            pieces.append(tail)
    return "".join(pieces)


def _render_text(element: ET.Element) -> str:
    """Render character-level preserved source text: rule ``JLEGAL-TEXT-PRESERVE-1``.

    Ruby, Sup, and other inline/unknown leaf elements are kept as XML snippets
    (unchanged). Structural wrappers are intentionally not emitted as markup
    because every structural element is represented by its own canonical
    node. See ``_walk_text`` for the content-model-aware formatting-whitespace
    rule shared with ``_character_data``.
    """
    def render_child(child: ET.Element) -> str:
        child_tag = _local(child.tag)
        if child_tag in _INLINE_TAGS or child_tag not in _KNOWN_TAGS:
            return _element_xml(child)
        return _render_text(child)

    return _walk_text(element, render_child)


def _character_data(element: ET.Element) -> str:
    """Character data only, content-model aware: never inline XML markup.

    Used only by ``_plain_text`` (``JLEGAL-DISPLAY-TRIM-1``). Every
    descendant -- including an inline element such as Ruby/Sup and an unknown
    leaf -- contributes its own character data only, matching
    ``element.itertext()``'s recursive text-only concatenation, plus the same
    content-model-aware formatting-whitespace elision as ``_render_text``
    (see ``_walk_text``). ``LegalNode.text`` is always built by
    ``_render_text``, never this function.
    """
    return _walk_text(element, _character_data)


def _number_part(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    total = part = digit = 0
    for char in value:
        if char in _KANJI_DIGITS:
            digit = _KANJI_DIGITS[char]
        elif char in _KANJI_UNITS:
            part += (digit or 1) * _KANJI_UNITS[char]
            digit = 0
        else:
            raise ValueError(value)
    return total + part + digit


def _ordinal_branch(value: str | None) -> tuple[int | None, tuple[int, ...]]:
    if value is None:
        return None, ()
    compact = re.sub(r"[\s\u3000]", "", value)
    if not compact:
        return None, ()
    numeric = _NUMERIC_BRANCH.fullmatch(compact)
    if numeric:
        values = tuple(int(part) for part in re.split(r"[_\-‐－の]", compact))
        return values[0], values[1:]
    if compact.isdigit():
        return int(compact), ()
    japanese = _JAPANESE_BRANCH.search(compact)
    if japanese:
        try:
            first = _number_part(japanese.group(1))
            return first, ((_number_part(japanese.group(2)),) if japanese.group(2) else ())
        except ValueError:
            return None, ()
    return None, ()


def _node_number(element: ET.Element, tag: str) -> tuple[int | None, tuple[int, ...]]:
    for name, value in element.attrib.items():
        if _local(name) == "Num":
            ordinal, branch = _ordinal_branch(value)
            if ordinal is not None:
                return ordinal, branch
    for suffix in ("Num", "Title", "Label"):
        candidate = _direct_named(element, f"{tag}{suffix}")
        ordinal, branch = _ordinal_branch(_plain_text(candidate))
        if ordinal is not None:
            return ordinal, branch
    return None, ()


def _heading(element: ET.Element, tag: str) -> str | None:
    names = (f"{tag}Caption", f"{tag}Title", f"{tag}Label", "ArticleCaption", "ArticleTitle")
    for name in names:
        value = _plain_text(_direct_named(element, name))
        if value:
            return value
    return None


def _bare_promulgated(law: ET.Element) -> str | None:
    """Derive a publication date only from the complete, schema-defined fields.

    Law XML's era/year/month/day attributes are legal-number metadata, so this
    conversion intentionally accepts only the five public e-Gov eras and ASCII
    positive integers.  Any incomplete, unknown, or impossible tuple stays
    unknown rather than being guessed from a title or law number.
    """
    era = _attribute(law, "Era")
    components = [_attribute(law, name) for name in ("Year", "PromulgateMonth", "PromulgateDay")]
    if era is None or any(value is None for value in components):
        return None
    era = era.strip()
    if era not in _ERA_YEAR_BASE:
        return None
    raw_year, raw_month, raw_day = (value.strip() for value in components if value is not None)
    if any(not value.isascii() or not value.isdigit() or int(value) <= 0 for value in (raw_year, raw_month, raw_day)):
        return None
    try:
        candidate = date(_ERA_YEAR_BASE[era] + int(raw_year), int(raw_month), int(raw_day))
    except ValueError:
        return None
    lower, upper = _ERA_DATE_RANGES[era]
    if candidate < lower or (upper is not None and candidate >= upper):
        return None
    return candidate.isoformat()


def _envelope_promulgated(document: ET.Element) -> str | None:
    if _local(document.tag) != "law_data_response":
        return None
    law_info = _direct_named(document, "law_info")
    raw = _plain_text(_direct_named(law_info, "promulgation_date")) if law_info is not None else ""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise AdapterError("EGOV_XML_PROMULGATION_DATE") from exc


def _promulgated(document: ET.Element, law: ET.Element) -> str | None:
    envelope_date = _envelope_promulgated(document)
    law_date = _bare_promulgated(law)
    if envelope_date is not None and law_date is not None and envelope_date != law_date:
        raise AdapterError("EGOV_XML_PROMULGATION_CONFLICT")
    return envelope_date or law_date


_MEANINGFUL_ATTRIBUTES = {"delete", "hide", "extract", "amendlawnum", "amendlawid", "amendrevisionid"}


def _meaningful_attribute(name: str) -> bool:
    normalized = _local(name).lower()
    return normalized in _MEANINGFUL_ATTRIBUTES or normalized.startswith("amend")


def _attributes(element: ET.Element) -> tuple[tuple[str, str], ...]:
    values: dict[str, str] = {"egov_tag": _local(element.tag)}
    for name, value in element.attrib.items():
        key = _local(name)
        if key in values:
            key = f"xml_{key}"
        values[key] = str(value)
    # e-Gov places amendment/extraction flags on both structural and sentence
    # elements.  Preserve descendant flags on the nearest structural node too;
    # otherwise a flattened content wrapper would erase meaningful source state.
    for descendant in element.iter():
        if descendant is element:
            continue
        for name, value in descendant.attrib.items():
            if not _meaningful_attribute(name):
                continue
            base = _local(name)
            key = base if base not in values else f"{_local(descendant.tag)}_{base}"
            number = 2
            while key in values:
                key = f"{_local(descendant.tag)}_{base}_{number}"
                number += 1
            values[key] = str(value)
    return tuple(sorted(values.items()))


_NODE_TAGS: dict[str, NodeKind] = {
    "Preamble": NodeKind.PREAMBLE,
    "MainProvision": NodeKind.MAIN_PROVISION,
    "Part": NodeKind.PART,
    "Chapter": NodeKind.CHAPTER,
    "Section": NodeKind.SECTION,
    "Subsection": NodeKind.SUBSECTION,
    "Division": NodeKind.DIVISION,
    "Article": NodeKind.ARTICLE,
    "Paragraph": NodeKind.PARAGRAPH,
    "Item": NodeKind.ITEM,
    "Subitem": NodeKind.SUBITEM,
    "SupplProvision": NodeKind.SUPPLEMENTARY_PROVISION,
    "AmendProvision": NodeKind.AMENDMENT_PROVISION,
    "Appdx": NodeKind.APPENDIX,
    "AppdxTable": NodeKind.APPENDIX,
    "SupplProvisionAppdxTable": NodeKind.APPENDIX,
    "SupplProvisionAppdxStyle": NodeKind.APPENDIX,
    "SupplProvisionAppdx": NodeKind.APPENDIX,
    "AppdxNote": NodeKind.APPENDIX,
    "AppdxStyle": NodeKind.APPENDIX,
    "AppdxFig": NodeKind.APPENDIX,
    "AppdxFormat": NodeKind.APPENDIX,
    "Table": NodeKind.TABLE,
    "TableRow": NodeKind.ROW,
    "TableHeaderRow": NodeKind.ROW,
    "TableColumn": NodeKind.CELL,
    "TableHeaderColumn": NodeKind.CELL,
}
for _subitem in range(1, 11):
    _NODE_TAGS[f"Subitem{_subitem}"] = NodeKind.SUBITEM

# Structural (element-only content model) tags for _walk_text's content-model
# awareness (rule JLEGAL-TEXT-PRESERVE-1). Every canonical node tag is
# structural, plus the transparent containers and sentence/list-wrapper
# elements listed below that may themselves group child elements. The
# unnumbered SubitemSentence and List/Sublist{n}/Sublist{n}Sentence wrapper
# tags are included alongside their numbered Subitem{n}Sentence counterparts
# so that identical content produces identical text regardless of which
# recognised spelling of the same element-only wrapper shape the source uses.
# Deliberately does NOT include text-bearing leaf tags -- Sentence, LawTitle,
# LawNum, EnactStatement, every *Title/*Caption/*Label, ParagraphNum, and
# other *Num tags -- whose own content must always be emitted verbatim.
# TableHeaderColumn is deliberately excluded even though it is a canonical
# node tag: unlike TableColumn, it is mixed content in the e-Gov schema (it
# may carry text directly, e.g. mixed with inline Ruby), so eliding its own
# whitespace-only text/tail would lose source formatting that is meaningful
# there; the conservative default is to leave a tag out of this set when its
# content model is not confidently element-only.
_STRUCTURAL_TAGS = (set(_NODE_TAGS) | {"Law"} | {
    "LawBody", "TOC", "TOCPart", "TOCChapter", "TOCSection", "TOCSubsection",
    "TOCDivision", "TOCArticle", "TOCSupplProvision",
    "ParagraphSentence", "ItemSentence", "AmendProvisionSentence",
    "TableStruct", "FigStruct", "StyleStruct", "NoteStruct",
    "SentenceList", "Column", "Remarks",
    "SubitemSentence", "List",
} | {f"Subitem{n}Sentence" for n in range(1, 11)}
  | {f"Sublist{n}" for n in range(1, 11)}
  | {f"Sublist{n}Sentence" for n in range(1, 11)}
) - {"TableHeaderColumn"}

# These tags can carry source text or transparently group recognised nodes.  They
# are deliberately enumerated so a novel non-trivial XML structure fails closed.
_INLINE_TAGS = {
    "Ruby", "Rt", "Rp", "Sup", "Sub", "UnderLine", "Line", "Bold", "Italic",
    "ArithFormula", "Formula", "Quote", "Bracket", "Point",
}
_CONTENT_TAGS = {
    "LawNum", "LawTitle", "LawBody", "EnactStatement", "TOC", "TOCLabel",
    "TOCPart", "TOCChapter", "TOCSection", "TOCSubsection", "TOCDivision",
    "TOCArticle", "TOCSupplProvision", "PartTitle", "ChapterTitle", "SectionTitle",
    "SubsectionTitle", "DivisionTitle", "ArticleCaption", "ArticleTitle",
    "ParagraphCaption", "ParagraphNum", "ParagraphSentence", "ItemTitle", "ItemSentence",
    "SubitemTitle", "SubitemSentence",
    "SupplProvisionLabel", "AppdxTitle", "AppdxTableTitle", "AppdxNoteTitle",
    "AppdxStyleTitle", "AppdxFigTitle", "AppdxFormatTitle", "TableStruct",
    "SupplProvisionAppdxTableTitle", "SupplProvisionAppdxStyleTitle",
    "RelatedArticleNum", "ArithFormulaNum",
    "Fig", "FigStruct", "FigTitle", "StyleStruct", "Note", "NoteStruct", "Remarks",
    "RemarksLabel", "Column", "List", "Sentence", "SentenceList", "QuoteStruct",
    "AmendProvisionSentence",
}
for _subitem in range(1, 11):
    _CONTENT_TAGS.update({f"Subitem{_subitem}Title", f"Subitem{_subitem}Sentence"})
for _sublist in range(1, 11):
    _CONTENT_TAGS.update({f"Sublist{_sublist}", f"Sublist{_sublist}Sentence"})
_KNOWN_TAGS = set(_NODE_TAGS) | _INLINE_TAGS | _CONTENT_TAGS | {"Law"}
_FAIL_CLOSED_TAGS = {"NewProvision"}


def _ensure_supported_tree(element: ET.Element) -> None:
    tag = _local(element.tag)
    # A NewProvision contains a second legal hierarchy.  Until it has a
    # dedicated source/parent/identity contract, accepting it would flatten a
    # material amendment into text. Reject all forms, including empty wrappers.
    if tag in _FAIL_CLOSED_TAGS:
        raise AdapterError(f"EGOV_XML_UNSUPPORTED_STRUCTURE:{tag}")
    if tag not in _KNOWN_TAGS and len(element):
        raise AdapterError(f"EGOV_XML_UNSUPPORTED_STRUCTURE:{tag}")
    for child in element:
        _ensure_supported_tree(child)


def _read_admissible_xml(path: Path) -> bytes:
    """Read one bounded regular XML file before safe, fail-closed parsing."""
    try:
        metadata = path.stat()
    except OSError as exc:
        raise AdapterError("EGOV_XML_INPUT_UNAVAILABLE") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise AdapterError("EGOV_XML_INPUT_NOT_REGULAR")
    if metadata.st_size == 0:
        raise AdapterError("EGOV_XML_INPUT_EMPTY")
    if metadata.st_size > MAX_EGOV_XML_BYTES:
        raise AdapterError("EGOV_XML_INPUT_TOO_LARGE")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AdapterError("EGOV_XML_INPUT_UNAVAILABLE") from exc
    # Recheck after the read so a concurrent replacement cannot bypass the
    # documented admission limit.
    if not raw:
        raise AdapterError("EGOV_XML_INPUT_EMPTY")
    if len(raw) > MAX_EGOV_XML_BYTES:
        raise AdapterError("EGOV_XML_INPUT_TOO_LARGE")
    return raw


def _safe_fromstring(raw: bytes) -> ET.Element:
    """Parse XML with every DTD/entity/external-reference feature disabled."""
    return ET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def _direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element if _local(item.tag) == name]


def _law_and_identifier(root: ET.Element, supplied: str | None) -> tuple[ET.Element, str]:
    envelope_id: str | None = None
    if _local(root.tag) == "Law":
        law = root
    elif _local(root.tag) == "law_data_response":
        full_texts = _direct_children(root, "law_full_text")
        if len(full_texts) != 1:
            raise AdapterError("EGOV_XML_LAW_FULL_TEXT")
        laws = _direct_children(full_texts[0], "Law")
        if len(laws) != 1:
            raise AdapterError("EGOV_XML_LAW_MISSING")
        law = laws[0]
        law_infos = _direct_children(root, "law_info")
        if len(law_infos) > 1:
            raise AdapterError("EGOV_XML_LAW_INFO")
        envelope_id = _plain_text(_direct_named(law_infos[0], "law_id")) if law_infos else None
    else:
        raise AdapterError("EGOV_XML_ROOT")
    law_attr_id = next((value for name, value in law.attrib.items() if _local(name) in {"LawId", "law_id"}), None)
    candidates = [value.strip() for value in (supplied, envelope_id, law_attr_id) if isinstance(value, str) and value.strip()]
    if not candidates:
        raise AdapterError("EGOV_XML_LAW_ID_REQUIRED")
    if len(set(candidates)) != 1:
        raise AdapterError("EGOV_XML_LAW_ID_MISMATCH")
    return law, candidates[0]


def admit_egov_xml(path: str | Path, *, law_id: str | None = None) -> EgovAdmission:
    """Fail closed unless a saved XML file is in the reviewed e-Gov v0.1 slice.

    This is intentionally the single structural admission path used by both
    ``jlegal validate-source`` and ``egov_xml_adapter``.  It does not infer an
    identifier from a file name, title, or local filesystem metadata.
    """
    source_path = Path(path)
    raw = _read_admissible_xml(source_path)
    try:
        document = _safe_fromstring(raw)
    except DefusedXmlException as exc:
        raise AdapterError("EGOV_XML_DTD_OR_ENTITY_FORBIDDEN") from exc
    except ET.ParseError as exc:
        raise AdapterError("EGOV_XML_PARSE") from exc
    root_tag = _local(document.tag)
    if root_tag == "error_info":
        raise AdapterError("EGOV_XML_API_ERROR")
    if root_tag not in {"Law", "law_data_response"}:
        raise AdapterError("EGOV_XML_ROOT")
    law, official_law_id = _law_and_identifier(document, law_id)
    law_bodies = _direct_children(law, "LawBody")
    if len(law_bodies) != 1:
        raise AdapterError("EGOV_XML_LAW_BODY_MISSING")
    _ensure_supported_tree(law)
    # The adapter always creates the Law root plus at least one recognised
    # structural node.  Check the latter up front so the admission command
    # reports an input problem rather than creating no canonical body.
    if not any(_local(item.tag) in _NODE_TAGS for item in law_bodies[0].iter()):
        raise AdapterError("EGOV_XML_STRUCTURE_EMPTY")
    return EgovAdmission(
        raw=raw,
        document=document,
        law=law,
        official_law_id=official_law_id,
        input_kind="egov_api_v2_envelope" if root_tag == "law_data_response" else "egov_law_xml",
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _law_number(law: ET.Element) -> str | None:
    value = _plain_text(_direct_named(law, "LawNum"))
    return value or None


def _base_source_metadata(law: ET.Element, official_law_id: str) -> dict[str, Any]:
    """Source facts available from XML; never infer retrieval facts from mtime."""
    return {
        "schema": EGOV_ACQUISITION_SCHEMA,
        "source_authority": EGOV_SOURCE_AUTHORITY,
        "source_url": None,
        "retrieved_at": None,
        "source_format": EGOV_XML_FULL_TEXT_FORMAT,
        "official_law_id": official_law_id,
        "law_number": _law_number(law),
        "requested_law_id": None,
        "as_of": None,
        "sha256": None,
        # Licence/rights are not inferred from API delivery or XML contents.
        "rights": None,
    }


def is_egov_xml(path: Path) -> bool:
    """Conservative registry sniffing; generic XML remains generic XML."""
    try:
        root = admit_egov_xml(path).document
    except AdapterError:
        return False
    return _local(root.tag) in {"Law", "law_data_response"}


def egov_xml_adapter(path: Path, mapping: dict[str, Any] | None = None) -> Adaptation:
    """Adapt a saved native Law XML document or API v2 XML envelope.

    A bare ``<Law>`` must supply an explicit e-Gov ``law_id`` unless the Law
    itself carries one.  Identity is based on that official key, never a file
    name or a guessed title/number.
    """
    if mapping is not None and (set(mapping) != {"law_id"} or not isinstance(mapping.get("law_id"), str) or not mapping["law_id"].strip()):
        raise AdapterError("EGOV_XML_MAPPING")
    admitted = admit_egov_xml(path, law_id=mapping["law_id"] if mapping else None)
    raw, document, law = admitted.raw, admitted.document, admitted.law
    source_law_key = admitted.official_law_id
    law_body = _direct_named(law, "LawBody")
    assert law_body is not None  # guaranteed by admit_egov_xml
    law_type = next((value for name, value in law.attrib.items() if _local(name) == "LawType"), "national_law")
    temporal = Temporal(promulgated=_promulgated(document, law))
    source_sha256 = admitted.source_sha256
    source = SourceRef(content_addressed_uri(source_sha256), source_sha256, "egov_xml", source_law_key)
    title = _plain_text(_direct_named(law_body, "LawTitle")) or _plain_text(_direct_named(law, "LawTitle")) or source_law_key
    root = LegalNode(
        jurisdiction="Japan",
        authority=law_type or "national_law",
        law_number_key=None,
        source_law_key=source_law_key,
        locator=semantic_locator("unused", None, NodeKind.LAW, "root"),
        kind=NodeKind.LAW,
        depth=0,
        text=_render_text(law) or ET.tostring(law, encoding="unicode", short_empty_elements=False),
        temporal=temporal,
        source=source,
        heading=title,
        attributes=_attributes(law),
    )
    nodes: list[LegalNode] = [root]

    def visit_children(container: ET.Element, parent: LegalNode, path_key: str) -> None:
        counts: dict[str, int] = {}
        for child in container:
            tag = _local(child.tag)
            counts[tag] = counts.get(tag, 0) + 1
            child_path = f"{path_key}/{tag}[{counts[tag]}]"
            kind = _NODE_TAGS.get(tag)
            if kind is None:
                # Known content elements are transparent containers.  Unknown
                # leaves are already retained by _render_text; unknown branches
                # were rejected by _ensure_supported_tree above.
                visit_children(child, parent, child_path)
                continue
            ordinal, branch = _node_number(child, tag)
            text = _render_text(child)
            if not text:
                text = _element_xml(child)
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
            node = LegalNode(
                jurisdiction=root.jurisdiction,
                authority=root.authority,
                law_number_key=None,
                source_law_key=source_law_key,
                locator=locator,
                kind=kind,
                depth=parent.depth + 1,
                text=text,
                temporal=temporal,
                source=source,
                parent_id=parent.node_id,
                ordinal=ordinal,
                branch=branch,
                label=_plain_text(_direct_named(child, f"{tag}Title")) or None,
                heading=_heading(child, tag),
                attributes=_attributes(child),
            )
            nodes.append(node)
            visit_children(child, node, child_path)

    visit_children(law_body, root, "LawBody[1]")
    if len(nodes) == 1:
        raise AdapterError("EGOV_XML_STRUCTURE_EMPTY")
    metadata = _base_source_metadata(law, source_law_key)
    metadata["sha256"] = source.sha256
    return Adaptation(
        tuple(nodes), adapter="egov_xml", inputs=(BuildInput.from_source("source", source),),
        source_metadata=metadata,
    )


@dataclass(frozen=True)
class FetchResult:
    law_id: str
    output: str
    sha256: str
    endpoint: str
    as_of: str | None
    source_url: str
    retrieved_at: str
    official_law_id: str
    law_number: str | None

    def acquisition(self) -> dict[str, str | None]:
        return {
            "schema": EGOV_ACQUISITION_SCHEMA,
            "source_authority": EGOV_SOURCE_AUTHORITY,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "source_format": EGOV_XML_FULL_TEXT_FORMAT,
            "official_law_id": self.official_law_id,
            "law_number": self.law_number,
            "requested_law_id": self.law_id,
            "as_of": self.as_of,
            "sha256": self.sha256,
            "rights": None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "acquisition": self.acquisition(), "as_of": self.as_of,
            "endpoint": self.endpoint, "law_id": self.law_id,
            "law_number": self.law_number, "official_law_id": self.official_law_id,
            "output": self.output, "retrieved_at": self.retrieved_at,
            "sha256": self.sha256, "source_url": self.source_url,
        }


def write_acquisition_receipt(result: FetchResult, output: str | Path) -> Path:
    """Persist only acquisition evidence, separately from immutable XML bytes."""
    target = Path(output).resolve()
    if target.exists():
        raise JLegalError(f"EGOV_FETCH_RECEIPT_EXISTS_REFUSED: {target}")
    _atomic_bytes(target, canonical_json(result.acquisition()) + b"\n")
    return target


def _response_error_code(content: bytes) -> str | None:
    try:
        root = _safe_fromstring(content)
    except (DefusedXmlException, ET.ParseError):
        return None
    if _local(root.tag) != "error_info":
        return None
    return _plain_text(_first_named(root, "code")) or None


def fetch_egov_xml(
    law_id: str,
    output: str | Path,
    *,
    as_of: str | None = None,
    timeout: float = 30.0,
    force: bool = False,
    base_url: str = EGOV_API_V2,
) -> FetchResult:
    """Fetch a full-text API v2 XML envelope into an atomic local snapshot."""
    try:
        import httpx
    except ImportError as exc:
        raise JLegalError("EGOV_FETCH_HTTPX_REQUIRED") from exc
    if not isinstance(law_id, str) or not law_id.strip():
        raise JLegalError("EGOV_FETCH_LAW_ID")
    if type(timeout) not in (int, float) or timeout <= 0:
        raise JLegalError("EGOV_FETCH_TIMEOUT_VALUE")
    normalized_as_of: str | None = None
    if as_of is not None:
        try:
            normalized_as_of = date.fromisoformat(as_of).isoformat()
        except (TypeError, ValueError) as exc:
            raise JLegalError("EGOV_FETCH_AS_OF") from exc
    target = Path(output).resolve()
    if target.exists() and not force:
        raise JLegalError(f"EGOV_FETCH_OUTPUT_EXISTS_REFUSED: {target}")
    endpoint = f"{base_url.rstrip('/')}/law_data/{quote(law_id.strip(), safe='')}"
    params: dict[str, str] = {"response_format": "xml", "law_full_text_format": "xml"}
    if normalized_as_of is not None:
        params["asof"] = normalized_as_of
    try:
        response = httpx.get(endpoint, params=params, timeout=float(timeout), headers={"Accept": "application/xml"}, follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise JLegalError("EGOV_FETCH_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise JLegalError("EGOV_FETCH_NETWORK") from exc
    content = response.content
    if response.status_code < 200 or response.status_code >= 300:
        code = _response_error_code(content)
        suffix = f":{code}" if code else ""
        raise JLegalError(f"EGOV_FETCH_HTTP_{response.status_code}{suffix}")
    try:
        root = _safe_fromstring(content)
        # The API path also accepts law numbers and revision IDs.  Validate the
        # returned official law identity without incorrectly requiring it to be
        # byte-equal to the caller's lookup key.
        law, official_law_id = _law_and_identifier(root, law_id.strip() if _local(root.tag) == "Law" else None)
    except (DefusedXmlException, ET.ParseError, AdapterError) as exc:
        raise JLegalError("EGOV_FETCH_XML") from exc
    _atomic_bytes(target, content)
    # Preserve the server-observed final URL, including any redirect, rather
    # than reconstructing a request URL from local parameters.
    source_url = str(response.url)
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return FetchResult(
        law_id.strip(), str(target), hashlib.sha256(content).hexdigest(), endpoint,
        normalized_as_of, source_url, retrieved_at, official_law_id, _law_number(law),
    )
