"""Join per-page MusicXML documents into a single score (page concatenation).

Recognition backends work one page at a time, so a multi-page piece arrives as a
list of single-page ``score-partwise`` documents.  This module stitches them into
one continuous score by appending each page's measures to the matching part and
renumbering measures sequentially.  Page boundaries are marked with a
``<print new-page="yes"/>`` so a renderer starts each source page on a new page.

Assumptions (kept deliberately simple and documented):
* Every page is MusicXML ``score-partwise``.
* Parts are identified by their ``id`` (homr emits stable ``P1``, ``P2`` ...).
* The document header is taken from the **first** page.  The part list is the
  ordered *union* of part ids across all pages; ids absent from the first page's
  list get a synthesised ``<score-part>``.
* Only measures are joined; per-page ``<attributes>`` are preserved as-is.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n'


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in parent if _localname(c.tag) == name]


def join_musicxml(documents: list[str], *, new_page: bool = True) -> str:
    """Join a list of single-page MusicXML strings into one score.

    Returns the joined MusicXML document as a string.  Raises ``ValueError`` if
    the list is empty or a document is not ``score-partwise``.
    """
    if not documents:
        raise ValueError("no documents to join")

    roots = [ET.fromstring(doc) for doc in documents]
    for index, root in enumerate(roots):
        if _localname(root.tag) != "score-partwise":
            raise ValueError(
                f"document {index} has root <{_localname(root.tag)}>, expected <score-partwise>"
            )

    first = roots[0]

    # Ordered union of part ids across every page (engines such as homr emit a
    # varying number of parts per page, so a later page may add a new part).
    ordered_parts: list[str] = []
    for root in roots:
        for part in _children(root, "part"):
            part_id = part.get("id")
            if part_id and part_id not in ordered_parts:
                ordered_parts.append(part_id)
    if not ordered_parts:
        raise ValueError("no <part> elements found in any document")

    result = ET.Element("score-partwise", {"version": first.get("version", "4.0")})

    # Carry over header content (work, identification, defaults, credits, ...).
    for child in first:
        if _localname(child.tag) in ("part-list", "part"):
            continue
        result.append(copy.deepcopy(child))

    # Part list: first page's entries, plus synthesised entries for union-only ids.
    part_list_src = _children(first, "part-list")
    new_part_list = ET.Element("part-list")
    known_ids: set[str | None] = set()
    if part_list_src:
        for score_part in _children(part_list_src[0], "score-part"):
            new_part_list.append(copy.deepcopy(score_part))
            known_ids.add(score_part.get("id"))
    for part_id in ordered_parts:
        if part_id not in known_ids:
            score_part = ET.SubElement(new_part_list, "score-part", {"id": part_id})
            ET.SubElement(score_part, "part-name").text = f"Part {part_id}"
    result.append(new_part_list)

    counters: dict[str, int] = {pid: 0 for pid in ordered_parts}

    for part_id in ordered_parts:
        part_el = ET.SubElement(result, "part", {"id": part_id})
        for doc_index, root in enumerate(roots):
            source_part = next(
                (p for p in _children(root, "part") if p.get("id") == part_id), None
            )
            if source_part is None:
                continue
            for measure_index, measure in enumerate(_children(source_part, "measure")):
                joined = copy.deepcopy(measure)
                counters[part_id] += 1
                joined.set("number", str(counters[part_id]))
                if new_page and doc_index > 0 and measure_index == 0:
                    # Insert new-page print before notes/attributes if possible
                    print_el = ET.Element("print", {"new-page": "yes"})
                    inserted = False
                    for idx, child in enumerate(list(joined)):
                        if _localname(child.tag) in ("attributes", "direction", "note", "backup", "forward", "sound", "barline"):
                            joined.insert(idx, print_el)
                            inserted = True
                            break
                    if not inserted:
                        joined.insert(0, print_el)
                part_el.append(joined)

    ET.indent(result, space="  ")
    return _XML_DECL + ET.tostring(result, encoding="unicode")


def join_files(paths: list[str], out_path: str, *, new_page: bool = True) -> str:
    """Read MusicXML files, join them, write ``out_path``, and return the result."""
    documents = [Path(p).read_text(encoding="utf-8") for p in paths]
    joined = join_musicxml(documents, new_page=new_page)
    Path(out_path).write_text(joined, encoding="utf-8")
    return joined
