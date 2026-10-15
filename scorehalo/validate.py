"""Lightweight MusicXML structural validation (stdlib only).

Not a substitute for full schema validation -- but it catches the failure modes
this project actually hits (empty output, wrong root element, missing
part-list/parts) and needs no network access or extra dependencies.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_musicxml(text: str) -> list[str]:
    """Return a list of structural problems; empty list means valid."""
    if not text or not text.strip():
        return ["document is empty"]

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]

    if _localname(root.tag) != "score-partwise":
        return [f"root element is <{_localname(root.tag)}>, expected <score-partwise>"]

    problems: list[str] = []

    part_list = next((c for c in root if _localname(c.tag) == "part-list"), None)
    if part_list is None:
        problems.append("missing <part-list>")
    elif not any(_localname(c.tag) == "score-part" for c in part_list):
        problems.append("<part-list> has no <score-part>")

    parts = [c for c in root if _localname(c.tag) == "part"]
    if not parts:
        problems.append("no <part> elements")
    for part in parts:
        part_id = part.get("id", "?")
        measures = [c for c in part if _localname(c.tag) == "measure"]
        if not measures:
            problems.append(f"part {part_id!r} has no <measure>")

    return problems


def is_valid_musicxml(text: str) -> bool:
    """True if :func:`validate_musicxml` reports no problems."""
    return not validate_musicxml(text)
