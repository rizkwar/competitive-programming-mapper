import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import Helper.practice as practice


class PracticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.problem = self.root / "example"
        self.problem.mkdir()
        (self.problem / "problem.md").write_text("# Example\n\nFind a pattern.\n", encoding="utf-8")
        (self.problem / "practice.json").write_text(
            json.dumps({"skills": ["invariants/minimum"], "hints": ["First clue", "Second clue"]}),
            encoding="utf-8",
        )
        sessions = patch.object(practice, "SESSIONS_DIR", self.root / "sessions")
        resolver = patch.object(practice, "resolve_practice_directory", return_value=self.problem)
        sessions.start()
        resolver.start()
        self.addCleanup(sessions.stop)
        self.addCleanup(resolver.stop)

    def test_progressive_hints_and_reflection(self) -> None:
        with redirect_stdout(StringIO()):
            session = practice.start("example")
            self.assertEqual(practice.hint(session["id"]), "First clue")
            self.assertEqual(practice.hint(session["id"]), "Second clue")
            self.assertIsNone(practice.hint(session["id"]))
            finished = practice.finish(session["id"], "solved", "I found an invariant.")
            totals = practice.stats()

        self.assertEqual(finished["hints_used"], 2)
        self.assertEqual(finished["reflection"], "I found an invariant.")
        self.assertEqual(totals, {"started": 1, "completed": 1, "solved": 1, "hints_used": 2})
        with self.assertRaisesRegex(ValueError, "complete"):
            practice.hint(session["id"])

    def test_finishing_points_to_analysis_stage(self) -> None:
        with redirect_stdout(StringIO()):
            session = practice.start("example")
        output = StringIO()
        with redirect_stdout(output):
            practice.finish(session["id"], "stuck", "I could not find the invariant.")
        self.assertIn("Problem/Analyze", output.getvalue())
        self.assertIn("python analyze.py", output.getvalue())

    def test_start_without_hint_plan(self) -> None:
        (self.problem / "practice.json").unlink()
        output = StringIO()
        with redirect_stdout(output):
            session = practice.start("example")
        self.assertEqual(session["hints_used"], 0)
        self.assertIn("Hints available: 0", output.getvalue())

    def test_rejects_bad_hint_plan(self) -> None:
        (self.problem / "practice.json").write_text(
            json.dumps({"hints": [""]}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "nonempty strings"):
            practice.start("example")


if __name__ == "__main__":
    unittest.main()
