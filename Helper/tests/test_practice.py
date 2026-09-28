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
        resolver = patch.object(practice, "resolve_problem_directory", return_value=self.problem)
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

    def test_ai_proposal_requires_finished_session_and_solution(self) -> None:
        with redirect_stdout(StringIO()):
            session = practice.start("example")
        with self.assertRaisesRegex(ValueError, "Finish"):
            practice.propose(session["id"], "codex")
        with redirect_stdout(StringIO()):
            practice.finish(session["id"], "stuck", "I could not find the invariant.")
        with self.assertRaisesRegex(ValueError, "solution.md"):
            practice.propose(session["id"], "codex")

    def test_rejects_bad_hint_plan(self) -> None:
        (self.problem / "practice.json").write_text(
            json.dumps({"hints": [""]}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "nonempty list"):
            practice.start("example")


if __name__ == "__main__":
    unittest.main()
