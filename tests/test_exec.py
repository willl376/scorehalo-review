"""Tests for the shared subprocess-timeout helper."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from scorehalo.backends import _exec
from scorehalo.backends.base import BackendError


class TimeoutForTests(unittest.TestCase):
    def test_default_when_unset(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCOREHALO_FOO_TIMEOUT", None)
            self.assertEqual(_exec.timeout_for("foo", default=42.0), 42.0)

    def test_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"SCOREHALO_FOO_TIMEOUT": "5"}):
            self.assertEqual(_exec.timeout_for("foo"), 5.0)

    def test_invalid_env_ignored(self) -> None:
        with mock.patch.dict(os.environ, {"SCOREHALO_FOO_TIMEOUT": "abc"}):
            self.assertEqual(_exec.timeout_for("foo", default=7.0), 7.0)

    def test_nonpositive_env_ignored(self) -> None:
        with mock.patch.dict(os.environ, {"SCOREHALO_FOO_TIMEOUT": "0"}):
            self.assertEqual(_exec.timeout_for("foo", default=9.0), 9.0)


class RunTests(unittest.TestCase):
    def test_success_returns_completed_process(self) -> None:
        proc = _exec.run([sys.executable, "-c", "print('hi')"], engine="unit")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hi", proc.stdout)

    def test_timeout_raises_backend_error(self) -> None:
        with self.assertRaises(BackendError):
            _exec.run(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                engine="unit",
                timeout=0.5,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
