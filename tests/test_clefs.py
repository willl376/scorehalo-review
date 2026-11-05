"""Read-only clef/staff audit tests.

The audit never edits a score: it records declarations, assigns the active clef
to each note by musical onset, and reports what it cannot resolve.  These tests
pin the semantics that matter for OMR review (inheritance, mid-measure changes,
voice serialization order, conflicts, unknown timing) and the manifest summary.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from scorehalo import clefs, join, validate, verification


def a(inner: str = "", attrs: str = "") -> str:
    return f"<attributes>{inner}</attributes>" if not attrs else f"<attributes {attrs}>{inner}</attributes>"


def clef(sign: str = "G", line: str | None = "2", staff: int | None = None, octave: str | None = None, attrs: str = "") -> str:
    parts = [f"<sign>{sign}</sign>"]
    if line is not None:
        parts.append(f"<line>{line}</line>")
    if octave is not None:
        parts.append(f"<clef-octave-change>{octave}</clef-octave-change>")
    number = f' number="{staff}"' if staff is not None else ""
    extra = f" {attrs}" if attrs else ""
    return f"<clef{number}{extra}>" + "".join(parts) + "</clef>"


D = "<divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>"


def note(duration: int = 1, extra: str = "") -> str:
    return (
        f"<note>{extra}<pitch><step>C</step><octave>4</octave></pitch>"
        f"<duration>{duration}</duration></note>"
    )


def m(inner: str, number: int = 1) -> str:
    return f'<measure number="{number}">{inner}</measure>'


def doc(*measures: str, pid: str = "P1", xmlns: str = "") -> str:
    ns = f' xmlns="{xmlns}"' if xmlns else ""
    return (
        f"<score-partwise{ns}><part-list><score-part id=\"{pid}\">"
        f"<part-name>Test</part-name></score-part></part-list>"
        f'<part id="{pid}">' + "".join(measures) + "</part></score-partwise>"
    )


def doc_parts(*parts: tuple[str, str, str], xmlns: str = "") -> str:
    """Build a multi-part score: each part is (id, name, measure-xml)."""
    ns = f' xmlns="{xmlns}"' if xmlns else ""
    part_list = "".join(
        f'<score-part id="{pid}"><part-name>{name}</part-name></score-part>'
        for pid, name, _ in parts
    )
    bodies = "".join(
        f'<part id="{pid}">{measures}</part>' for pid, _, measures in parts
    )
    return (
        f"<score-partwise{ns}><part-list>{part_list}</part-list>"
        f"{bodies}</score-partwise>"
    )


class ClefAuditTests(unittest.TestCase):
    def test_grand_staff_assigns_per_staff(self) -> None:
        xml = doc(m(a(D + "<staves>2</staves>" + clef() + clef("F", "4", 2)) + note() + note(extra="<staff>2</staff>")))
        report = clefs.audit_clefs(xml)
        self.assertEqual([n["clef"]["sign"] for n in report["note_assignments"]], ["G", "F"])
        self.assertEqual(report["findings"], [])

    def test_inherited_clef_keeps_its_declaration_origin(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef()) + note()), m(note(), 2)))
        self.assertEqual(report["note_assignments"][1]["clef_origin"], "inherited")
        self.assertEqual(report["note_assignments"][1]["clef"]["measure_ordinal"], 1)

    def test_mid_measure_change_applies_from_its_onset(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef()) + note() + a(clef("F", "4")) + note())))
        self.assertEqual([n["clef"]["sign"] for n in report["note_assignments"]], ["G", "F"])

    def test_voice_two_reads_score_order_not_serialization_order(self) -> None:
        xml = doc(m(a(D + clef()) + note(2) + a(clef("F", "4")) + note(2)
                    + "<backup><duration>4</duration></backup>" + note(extra="<voice>2</voice>")))
        self.assertEqual(clefs.audit_clefs(xml)["note_assignments"][-1]["clef"]["sign"], "G")

    def test_clef_serialized_later_still_applies_at_its_time(self) -> None:
        xml = doc(m(a(D + clef()) + note(4)
                    + "<backup><duration>4</duration></backup><forward><duration>2</duration></forward>"
                    + a(clef("F", "4")) + note()))
        self.assertEqual(clefs.audit_clefs(xml)["note_assignments"][-1]["clef"]["sign"], "F")

    def test_missing_declaration_is_reported_not_guessed(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D) + note())))
        self.assertIn("clef_unresolved", [f["code"] for f in report["findings"]])
        self.assertIsNone(report["note_assignments"][0]["clef"])

    def test_additional_clef_does_not_replace_primary(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef()) + note() + a(clef("F", "4", attrs='additional="yes"')) + note())))
        self.assertEqual(report["note_assignments"][-1]["clef"]["sign"], "G")

    def test_hidden_clef_still_applies(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef("F", "4", attrs='print-object="no"')) + note())))
        self.assertEqual(report["note_assignments"][0]["clef"]["sign"], "F")

    def test_octave_change_is_recorded(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef(octave="-1")) + note())))
        self.assertEqual(report["note_assignments"][0]["clef"]["octave_change"], "-1")

    def test_alto_clef_is_not_forced_to_treble(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef("C", "3")) + note())))
        self.assertEqual(report["findings"], [])

    def test_percussion_clef_needs_no_line(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef("percussion", None)) + note())))
        self.assertNotIn("clef_line_invalid", [f["code"] for f in report["findings"]])

    def test_invalid_sign_is_flagged(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef("X")) + note())))
        self.assertIn("clef_sign_invalid", [f["code"] for f in report["findings"]])

    def test_clef_for_undeclared_staff_is_flagged(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef(staff=2)) + note())))
        self.assertIn("clef_staff_invalid", [f["code"] for f in report["findings"]])

    def test_conflicting_clefs_at_one_time_are_not_guessed(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef() + clef("F", "4")) + note())))
        self.assertIn("clef_conflict", [f["code"] for f in report["findings"]])
        self.assertIsNone(report["note_assignments"][0]["clef"])

    def test_conflict_is_reported_once_not_once_per_note(self) -> None:
        many = "".join(note() for _ in range(12))
        report = clefs.audit_clefs(doc(m(a(D + clef() + clef("F", "4")) + many)))
        conflicts = [f for f in report["findings"] if f["code"] == "clef_conflict"]
        self.assertEqual(len(conflicts), 1)

    def test_unknown_timing_yields_unresolved(self) -> None:
        report = clefs.audit_clefs(doc(m(a(clef()) + note() + a(clef("F", "4")) + note())))
        self.assertIsNone(report["note_assignments"][-1]["clef"])

    def test_namespaced_document(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef()) + note()), xmlns="urn:test"))
        self.assertEqual(len(report["declarations"]), 1)

    def test_grace_note_does_not_advance_time(self) -> None:
        report = clefs.audit_clefs(doc(m(a(D + clef()) + note(extra="<grace/>") + note())))
        self.assertEqual([n["onset"] for n in report["note_assignments"]], ["0", "0"])

    def test_malformed_xml_is_an_error_finding(self) -> None:
        report = clefs.audit_clefs("<bad>")
        self.assertEqual(report["findings"][0]["code"], "clef_xml_parse")
        self.assertEqual(report["findings"][0]["severity"], "error")

    def test_public_validation_api(self) -> None:
        self.assertTrue(validate.validate_clefs(doc(m(a(D) + note()))))
        self.assertFalse(validate.validate_clefs(doc(m(a(D + clef()) + note()))))


class ClefJoinTests(unittest.TestCase):
    def test_declaration_payloads_survive_a_join(self) -> None:
        page = doc(m(a(D + clef("F", "4", octave="-1")) + note()))
        joined = join.join_musicxml([page, page])
        self.assertEqual(len(clefs.declaration_inventory(joined)["P1"]), 2)
        self.assertEqual(
            clefs.declaration_inventory(joined)["P1"],
            clefs.declaration_inventory(page)["P1"] * 2,
        )

    def test_union_join_with_varying_part_sets_preserves_clefs(self) -> None:
        """Real homr output gains a part on later pages; the union join must work."""
        page_one = doc(m(a(D + clef()) + note()))
        page_two = doc_parts(
            ("P1", "Test", m(a(D + clef()) + note())),
            ("P2", "Piano", m(a(D + clef("F", "4")) + note())),
        )
        joined = join.join_musicxml([page_one, page_two])
        inventory = clefs.declaration_inventory(joined)
        self.assertEqual(len(inventory["P1"]), 2)
        self.assertEqual(len(inventory["P2"]), 1)
        self.assertEqual(len(ET.fromstring(joined).findall(".//note")), 3)

    def test_compare_clef_maps_reports_difference(self) -> None:
        a_doc = doc(m(a(D + clef()) + note()))
        b_doc = doc(m(a(D + clef("F", "4")) + note()))
        result = clefs.compare_clef_maps(a_doc, b_doc)
        self.assertFalse(result["declarations_identical"])
        self.assertEqual(result["source_accuracy"], "not_assessed")


class VerificationIntegrationTests(unittest.TestCase):
    def test_clef_findings_merge_into_verification(self) -> None:
        report = verification.verify_musicxml(doc(m(a(D) + note())))
        self.assertIn("clef_unresolved", [f["code"] for f in report["findings"]])
        self.assertEqual(report["clefs"]["declarations"], [])

    def test_overfull_measure_is_flagged(self) -> None:
        report = verification.verify_musicxml(doc(m(a(D + clef()) + note(5))))
        self.assertIn("overfull_measure", [f["code"] for f in report["findings"]])

    def test_additive_meter_is_understood(self) -> None:
        attrs = (
            "<divisions>1</divisions><time><beats>3+2</beats>"
            "<beat-type>8</beat-type></time>"
        )
        report = verification.verify_musicxml(doc(m(a(attrs + clef()) + note(5))))
        self.assertNotIn("meter_unassessed", [f["code"] for f in report["findings"]])

    def test_summary_drops_per_note_detail_but_keeps_findings(self) -> None:
        report = verification.verify_musicxml(doc(m(a(D + clef()) + note() + note())))
        self.assertTrue(report["clefs"]["note_assignments"])
        compact = verification.summary(report)
        self.assertNotIn("events", compact)
        self.assertNotIn("note_assignments", compact["clefs"])
        self.assertEqual(compact["clefs"]["note_assignment_count"], 2)
        self.assertEqual(len(compact["clefs"]["declarations"]), 1)


if __name__ == "__main__":
    unittest.main()
