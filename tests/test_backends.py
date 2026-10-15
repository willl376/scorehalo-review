"""Contract tests for the pluggable recognition-backend interface."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scorehalo import backends
from scorehalo.backends import BackendError, RecognizeRequest, get_backend
from scorehalo.validate import is_valid_musicxml, validate_musicxml


def _fake_source(name: str = "song.pdf", data: bytes = b"%PDF-1.4 stub") -> Path:
    directory = tempfile.mkdtemp(prefix="scorehalo-test-")
    path = Path(directory) / name
    path.write_bytes(data)
    return path


class RegistryTests(unittest.TestCase):
    def test_builtin_backends_registered(self) -> None:
        for name in ("stub", "homr", "oemer", "audiveris"):
            self.assertIn(name, backends.all_backends())

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(BackendError):
            get_backend("does-not-exist")

    def test_describe_backends_shape(self) -> None:
        info = {b["name"]: b for b in backends.describe_backends()}
        self.assertTrue(info["stub"]["available"])
        self.assertEqual(info["homr"]["license"], "AGPL-3.0")
        self.assertEqual(info["oemer"]["license"], "MIT")
        self.assertEqual(info["audiveris"]["license"], "AGPL-3.0")


class StubBackendTests(unittest.TestCase):
    def test_stub_is_available(self) -> None:
        self.assertTrue(get_backend("stub").is_available())

    def test_stub_output_is_valid_musicxml(self) -> None:
        result = get_backend("stub").recognize(RecognizeRequest(source=_fake_source()))
        self.assertEqual(result.backend, "stub")
        self.assertEqual(validate_musicxml(result.musicxml), [])
        self.assertTrue(is_valid_musicxml(result.musicxml))
        self.assertIn("<score-partwise", result.musicxml)
        self.assertTrue(result.warnings)

    def test_stub_is_deterministic(self) -> None:
        backend = get_backend("stub")
        first = backend.recognize(RecognizeRequest(source=_fake_source())).musicxml
        second = backend.recognize(RecognizeRequest(source=_fake_source())).musicxml
        self.assertEqual(first, second)

    def test_stub_escapes_title(self) -> None:
        src = _fake_source(name="a&b<c>.pdf")
        result = get_backend("stub").recognize(RecognizeRequest(source=src))
        self.assertIn("a&amp;b&lt;c&gt;", result.musicxml)
        self.assertEqual(validate_musicxml(result.musicxml), [])


class UnavailableBackendTests(unittest.TestCase):
    def test_unavailable_backend_raises_cleanly(self) -> None:
        for name in ("homr", "oemer", "audiveris"):
            backend = get_backend(name)
            if backend.is_available():
                self.skipTest(f"{name} is installed on this machine")
            with self.assertRaises(BackendError):
                backend.recognize(RecognizeRequest(source=_fake_source("page.png", b"png")))


class ValidationTests(unittest.TestCase):
    def test_empty_document(self) -> None:
        self.assertEqual(validate_musicxml(""), ["document is empty"])

    def test_not_xml(self) -> None:
        self.assertTrue(validate_musicxml("hello world")[0].startswith("not well-formed"))

    def test_wrong_root(self) -> None:
        problems = validate_musicxml("<score-timewise/>")
        self.assertTrue(any("root element" in p for p in problems))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
