import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import analyze


class VerificationTests(unittest.TestCase):
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

        self.problem_dir = self.analyze_dir / "mex-case"
        self.problem_dir.mkdir()
        (self.problem_dir / "problem.md").write_text(
            "Find the MEX of a group of values.\n", encoding="utf-8"
        )
        (self.problem_dir / "editorial.md").write_text(
            "A group with 0 and 1 has MEX at least 2.\n", encoding="utf-8"
        )
        self.analysis = {
            "core_idea": "Use the frequency of zero.",
            "key_observations": [
                "A group with exactly one zero has MEX 1 regardless of positives."
            ],
            "reasoning_patterns": ["Use a critical value to test feasibility."],
            "questions": ["Which value is critical?"],
            "signals": ["The objective depends on the first missing value."],
            "skill_path": ["feasibility", "critical-value"],
            "probably_related": [],
        }

    @staticmethod
    def provider_reply(report):
        def run(command, **kwargs):
            output = Path(command[command.index("-o") + 1])
            output.write_text(json.dumps(report), encoding="utf-8")
            return SimpleNamespace(stdout="")
        return run

    def test_rejects_inconsistent_verdicts(self) -> None:
        with self.assertRaisesRegex(ValueError, "PASS cannot"):
            analyze.validate_verification_response({
                "status": "PASS", "checks": ["Tried {0, 1}: MEX is 2."],
                "issues": [{
                    "claim": "MEX is 1", "reason": "False", "counterexample": "{0, 1}"
                }],
            })
        with self.assertRaisesRegex(ValueError, "needs an issue"):
            analyze.validate_verification_response({
                "status": "UNCERTAIN", "checks": ["Considered small sets."], "issues": []
            })

    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "No match."))
    @patch("analyze.run_analysis")
    @patch("analyze.subprocess.run")
    def test_false_claim_prevents_skill_and_archive(self, run, generate, match) -> None:
        generate.side_effect = lambda provider, folder, output: output.write_text(
            json.dumps(self.analysis), encoding="utf-8"
        )
        run.side_effect = self.provider_reply({
            "status": "FAIL",
            "checks": ["Tried {0, 1}: it has one zero and MEX 2."],
            "issues": [{
                "claim": self.analysis["key_observations"][0],
                "reason": "Presence of 1 changes the MEX.",
                "counterexample": "{0, 1} has MEX 2.",
            }],
        })

        with redirect_stdout(StringIO()):
            self.assertFalse(analyze.analyze_one(self.problem_dir, "codex"))

        self.assertTrue(self.problem_dir.is_dir())
        self.assertFalse((self.skills_dir / "feasibility" / "critical-value.md").exists())
        self.assertFalse((self.completed_dir / "mex-case").exists())
        report = json.loads((self.problem_dir / "verification.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("{0, 1}", report["checks"][0])
        self.assertIn("Actively try small counterexamples", run.call_args.kwargs["input"])
        self.assertIn("A group with 0 and 1", run.call_args.kwargs["input"])
        self.assertEqual(run.call_args.args[0][-1], "-")
        match.assert_called_once()

    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "No match."))
    @patch("analyze.run_analysis")
    @patch("analyze.subprocess.run")
    def test_pass_creates_skill_and_archives_review(self, run, generate, match) -> None:
        corrected = dict(self.analysis)
        corrected["key_observations"] = [
            "A group containing 0 but not 1 has MEX 1."
        ]
        generate.side_effect = lambda provider, folder, output: output.write_text(
            json.dumps(corrected), encoding="utf-8"
        )
        run.side_effect = self.provider_reply({
            "status": "PASS",
            "checks": ["Tried {0} and {0, 2}: both have MEX 1."],
            "issues": [],
        })

        with redirect_stdout(StringIO()):
            self.assertTrue(analyze.analyze_one(self.problem_dir, "codex"))

        self.assertTrue((self.skills_dir / "feasibility" / "critical-value.md").is_file())
        self.assertEqual(
            json.loads((self.completed_dir / "mex-case" / "verification.json").read_text(encoding="utf-8"))["status"],
            "PASS",
        )

    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "No match."))
    @patch("analyze.run_analysis")
    @patch("analyze.subprocess.run", side_effect=OSError("provider unavailable"))
    def test_verifier_error_fails_closed(self, run, generate, match) -> None:
        generate.side_effect = lambda provider, folder, output: output.write_text(
            json.dumps(self.analysis), encoding="utf-8"
        )
        with redirect_stdout(StringIO()):
            self.assertFalse(analyze.analyze_one(self.problem_dir, "codex"))
        self.assertFalse((self.skills_dir / "feasibility" / "critical-value.md").exists())
        report = json.loads((self.problem_dir / "verification.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "ERROR")

    @patch("builtins.input", return_value="y")
    @patch("analyze.draft_skill_extension")
    @patch("analyze.ask_existing_skill_match")
    @patch("analyze.subprocess.run")
    def test_failed_extension_review_blocks_confirmed_write(self, run, match, draft, confirm) -> None:
        existing = self.skills_dir / "existing.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("# Existing\n", encoding="utf-8")
        draft.return_value = "# Existing\n\n- MEX is always 1 when 0 is present.\n"
        match.return_value = ("EXTEND", existing, "Related.")
        run.side_effect = self.provider_reply({
            "status": "FAIL",
            "checks": ["Tried {0, 1}: MEX is 2."],
            "issues": [{
                "claim": "MEX is always 1 when 0 is present.",
                "reason": "Value 1 can also be present.",
                "counterexample": "{0, 1} has MEX 2.",
            }],
        })

        with redirect_stdout(StringIO()):
            result = analyze.process_skill(
                self.analysis, "codex", self.problem_dir, apply_extension=True
            )

        self.assertEqual(result, "VERIFY_FAILED")
        self.assertEqual(existing.read_text(encoding="utf-8"), "# Existing\n")
        confirm.assert_not_called()

    @patch("analyze.ask_existing_skill_match")
    @patch("analyze.verify_skill_claims", return_value=False)
    def test_reuse_still_requires_valid_analysis(self, verify, match) -> None:
        existing = self.skills_dir / "existing.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("# Existing\n", encoding="utf-8")
        match.return_value = ("REUSE", existing, "Same technique.")

        with redirect_stdout(StringIO()):
            result = analyze.process_skill(self.analysis, "codex", self.problem_dir)

        self.assertEqual(result, "VERIFY_FAILED")
        verify.assert_called_once_with(self.analysis, self.problem_dir, "codex", "REUSE")


if __name__ == "__main__":
    unittest.main()
