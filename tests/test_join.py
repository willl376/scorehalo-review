"""Tests for the MusicXML page joiner."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scorehalo.join import join_files, join_musicxml
from scorehalo.validate import validate_musicxml


def _doc(measures: int, part_ids: tuple[str, ...] = ("P1",), version: str = "4.0") -> str:
    parts = "".join(
        f'<part id="{pid}">'
        + "".join(
            f'<measure number="{i + 1}">'
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>1</duration><type>quarter</type></note></measure>"
            for i in range(measures)
        )
        + "</part>"
        for pid in part_ids
    )
    part_list = "".join(
        f'<score-part id="{pid}"><part-name>Music</part-name></score-part>' for pid in part_ids
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<score-partwise version="{version}">'
        f"<part-list>{part_list}</part-list>{parts}</score-partwise>"
    )


def _measures(root: ET.Element, part_id: str) -> list[ET.Element]:
    part = next(c for c in root if c.tag == "part" and c.get("id") == part_id)
    return [c for c in part if c.tag == "measure"]


class JoinTests(unittest.TestCase):
    def test_measures_are_concatenated_and_renumbered(self) -> None:
        joined = join_musicxml([_doc(2, ("P1", "P2")), _doc(3, ("P1", "P2"))])
        root = ET.fromstring(joined)
        for part_id in ("P1", "P2"):
            measures = _measures(root, part_id)
            self.assertEqual(len(measures), 5)
            self.assertEqual([m.get("number") for m in measures], ["1", "2", "3", "4", "5"])

    def test_new_page_marker_on_later_pages(self) -> None:
        joined = join_musicxml([_doc(2), _doc(2)])
        root = ET.fromstring(joined)
        measures = _measures(root, "P1")
        self.assertFalse(any(c.tag == "print" for c in measures[0]))
        self.assertEqual(measures[2][0].tag, "print")
        self.assertEqual(measures[2][0].get("new-page"), "yes")

    def test_new_page_marker_can_be_disabled(self) -> None:
        joined = join_musicxml([_doc(2), _doc(2)], new_page=False)
        root = ET.fromstring(joined)
        measures = _measures(root, "P1")
        self.assertFalse(any(c.tag == "print" for m in measures for c in m))

    def test_part_list_preserved(self) -> None:
        joined = join_musicxml([_doc(1)])
        root = ET.fromstring(joined)
        self.assertTrue(any(c.tag == "part-list" for c in root))

    def test_joined_output_is_valid_musicxml(self) -> None:
        joined = join_musicxml([_doc(2, ("P1",)), _doc(2, ("P1",))])
        self.assertEqual(validate_musicxml(joined), [])

    def test_missing_part_in_later_page_is_skipped(self) -> None:
        joined = join_musicxml([_doc(2, ("P1", "P2")), _doc(3, ("P1",))])
        root = ET.fromstring(joined)
        self.assertEqual(len(_measures(root, "P1")), 5)
        self.assertEqual(len(_measures(root, "P2")), 2)

    def test_part_added_on_later_page_is_included(self) -> None:
        joined = join_musicxml([_doc(2, ("P1",)), _doc(3, ("P1", "P2"))])
        root = ET.fromstring(joined)
        self.assertEqual(len(_measures(root, "P1")), 5)
        self.assertEqual(len(_measures(root, "P2")), 3)
        part_list = next(c for c in root if c.tag == "part-list")
        ids = [sp.get("id") for sp in part_list if sp.tag == "score-part"]
        self.assertEqual(ids, ["P1", "P2"])
        self.assertEqual(validate_musicxml(joined), [])

    def test_empty_list_raises(self) -> None:
        with self.assertRaises(ValueError):
            join_musicxml([])

    def test_non_partwise_raises(self) -> None:
        with self.assertRaises(ValueError):
            join_musicxml(["<score-timewise/>"])

    def test_join_files_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.musicxml"
            second = Path(tmp) / "b.musicxml"
            out = Path(tmp) / "score.musicxml"
            first.write_text(_doc(1), encoding="utf-8")
            second.write_text(_doc(1), encoding="utf-8")
            joined = join_files([str(first), str(second)], str(out))
            self.assertTrue(out.is_file())
            self.assertEqual(validate_musicxml(joined), [])
            self.assertEqual(len(_measures(ET.fromstring(joined), "P1")), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
