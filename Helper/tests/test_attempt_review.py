import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import analyze
from Helper.attempt_review import GENERATED_MARKER, validate_attempt_review


class AttemptReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=analyze.ROOT)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.analyze_dir = root / "Problem" / "Analyze"
        self.completed_dir = root / "Problem" / "Completed"
        self.skills_dir = root / "skills"
        self.analyze_dir.mkdir(parents=True)
        self.completed_dir.mkdir(parents=True)
        stage = patch.multiple(
            analyze,
            ANALYZE_DIR=self.analyze_dir,
            COMPLETED_DIR=self.completed_dir,
            SKILLS_DIR=self.skills_dir,
        )
        stage.start()
        self.addCleanup(stage.stop)

        self.problem = self.analyze_dir / "successor-practice"
        self.problem.mkdir()
        (self.problem / "problem.md").write_text("Follow successor choices.\n", encoding="utf-8")
        (self.problem / "editorial.md").write_text(
            "Use repeated successor transitions.\n", encoding="utf-8"
        )
        self.attempt = "I tried choosing the earliest next element, but could not prove it stayed feasible."
        (self.problem / "attempt.md").write_text(self.attempt + "\n", encoding="utf-8")
        self.analysis = {
            "core_idea": "Use successor transitions.",
            "key_observations": ["The successor choice is monotone."],
            "solution_flow": [{
                "skill_index": 1,
                "application": "Follow successor transitions repeatedly.",
            }],
            "skills": [{
                "skill_path": ["graphs", "successor-jumps"],
                "signals": ["Repeated successor transitions appear."],
                "questions": ["Can I skip repeated transitions?"],
                "how_to_apply": ["Build a successor relation, then jump along it."],
                "why_it_works": ["Each jump represents consecutive transitions."],
                "when_it_fails": ["The successor relation changes over time."],
                "reasoning_patterns": ["Compress repeated transitions."],
                "probably_related": [],
            }],
        }

    def fake_analysis(self, provider, folder, output) -> None:
        output.write_text(json.dumps(self.analysis), encoding="utf-8")

    @staticmethod
    def reply(report):
        def run(command, **kwargs):
            output = Path(command[command.index("-o") + 1])
            output.write_text(json.dumps(report), encoding="utf-8")
            return SimpleNamespace(stdout="")
        return run

    def test_rejects_fabricated_evidence_and_skill_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "not found in attempt.md"):
            validate_attempt_review({
                "observations": [{
                    "evidence": "I used binary lifting.",
                    "what_it_shows": "The learner used a jump table.",
                }],
                "skill_connections": [],
            }, self.attempt, 1)
        with self.assertRaisesRegex(ValueError, "nonexistent skill_index"):
            validate_attempt_review({
                "observations": [],
                "skill_connections": [{
                    "skill_index": 2,
                    "evidence": "I tried choosing the earliest next element",
                    "connection": "This is a successor choice.",
                    "practice_task": "Prove that each choice stays feasible.",
                }],
            }, self.attempt, 1)

    @patch("analyze.verify_skill_claims", return_value=True)
    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "Distinct."))
    @patch("analyze.run_analysis")
    @patch("Helper.attempt_review.subprocess.run")
    def test_attempt_creates_grounded_review_and_keeps_skill_general(
        self, run, generate, match, verify,
    ) -> None:
        generate.side_effect = self.fake_analysis
        run.side_effect = self.reply({
            "observations": [{
                "evidence": "I tried choosing the earliest next element",
                "what_it_shows": "You explored a local successor choice.",
            }],
            "skill_connections": [{
                "skill_index": 1,
                "evidence": "could not prove it stayed feasible",
                "connection": "The successor skill needs a feasibility argument for each choice.",
                "practice_task": "Redo this problem by proving each successor choice preserves feasibility.",
            }],
        })

        with redirect_stdout(StringIO()):
            self.assertTrue(analyze.analyze_one(self.problem, "codex"))

        completed = self.completed_dir / "successor-practice"
        learning_review = (completed / "learning_review.md").read_text(encoding="utf-8")
        self.assertIn("could not prove it stayed feasible", learning_review)
        self.assertIn("Practice next:", learning_review)
        self.assertIn("graphs/successor-jumps", learning_review)
        saved_analysis = json.loads((completed / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_analysis["learner_review"]["summary"], "learning_review.md")
        self.assertEqual(
            json.loads((completed / "attempt_review.json").read_text(encoding="utf-8"))[
                "skill_connections"
            ][0]["skill_index"],
            1,
        )
        skill_note = (self.skills_dir / "graphs" / "successor-jumps.md").read_text(encoding="utf-8")
        self.assertNotIn("could not prove", skill_note)
        self.assertIn("LEARNER ATTEMPT", run.call_args.kwargs["input"])

    @patch("analyze.ask_existing_skill_match")
    @patch("analyze.run_analysis")
    @patch("Helper.attempt_review.subprocess.run")
    def test_invalid_attempt_review_stops_before_skill_writes(self, run, generate, match) -> None:
        generate.side_effect = self.fake_analysis
        run.side_effect = self.reply({
            "observations": [{
                "evidence": "I used binary lifting.",
                "what_it_shows": "The learner used a jump table.",
            }],
            "skill_connections": [],
        })

        with redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError, "not found"):
            analyze.analyze_one(self.problem, "codex")

        self.assertTrue(self.problem.is_dir())
        self.assertFalse(self.skills_dir.exists())
        match.assert_not_called()

    @patch("analyze.process_skills", return_value=[{
        "skill_index": 1, "decision": "REUSE", "path": "graphs/successor-jumps.md",
        "written": False, "verification": "verification-1.json",
    }])
    @patch("analyze.run_analysis")
    @patch("Helper.attempt_review.subprocess.run")
    def test_empty_attempt_skips_personal_review(self, review_run, generate, process) -> None:
        (self.problem / "attempt.md").write_text("  \n", encoding="utf-8")
        (self.problem / "learning_review.md").write_text(
            GENERATED_MARKER + "\nOld review\n", encoding="utf-8"
        )
        (self.problem / "attempt_review.json").write_text("{}\n", encoding="utf-8")
        generate.side_effect = self.fake_analysis

        with redirect_stdout(StringIO()):
            self.assertTrue(analyze.analyze_one(self.problem, "codex"))

        review_run.assert_not_called()
        completed = self.completed_dir / "successor-practice"
        self.assertFalse((completed / "learning_review.md").exists())
        self.assertFalse((completed / "attempt_review.json").exists())
        saved = json.loads((completed / "analysis.json").read_text(encoding="utf-8"))
        self.assertNotIn("learner_review", saved)


if __name__ == "__main__":
    unittest.main()
