import json
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import analyze


class AnalyzeWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.analyze_dir = root / "Problem" / "Analyze"
        self.completed_dir = root / "Problem" / "Completed"
        self.practice_dir = root / "Problem" / "Practice"
        self.analyze_dir.mkdir(parents=True)
        self.completed_dir.mkdir(parents=True)
        self.practice_dir.mkdir(parents=True)
        stage = patch.multiple(
            analyze,
            ANALYZE_DIR=self.analyze_dir,
            COMPLETED_DIR=self.completed_dir,
            PRACTICE_DIR=self.practice_dir,
        )
        stage.start()
        self.addCleanup(stage.stop)

    def make_problem(self, name: str = "alpha") -> Path:
        folder = self.analyze_dir / name
        folder.mkdir()
        (folder / "problem.md").write_text("# Problem\n", encoding="utf-8")
        (folder / "editorial.md").write_text("Use an invariant.\n", encoding="utf-8")
        return folder

    @staticmethod
    def fake_analysis(provider: str, problem_dir: Path, output_file: Path) -> None:
        output_file.write_text(
            json.dumps(
                {
                    "core_idea": "Track an invariant.",
                    "key_observations": [],
                    "solution_flow": [
                        {"skill_index": 1, "application": "Track the invariant across moves."}
                    ],
                    "skills": [{
                        "reasoning_patterns": ["Track the invariant."],
                        "questions": ["What stays unchanged?"],
                        "signals": ["A property is preserved by each operation."],
                        "how_to_apply": ["Identify the preserved property."],
                        "why_it_works": ["Every allowed move leaves that property unchanged."],
                        "when_it_fails": ["If an operation changes it, it is not an invariant."],
                        "skill_path": ["invariants", "tracking"],
                        "probably_related": [],
                    }],
                }
            ),
            encoding="utf-8",
        )

    @patch("analyze.process_skills", return_value=[{
        "skill_index": 1, "decision": "CREATE_NEW", "path": "invariants/tracking.md",
        "written": True, "verification": "verification-1.json",
    }])
    @patch("analyze.run_analysis")
    def test_success_moves_folder_with_analysis(self, run, skill) -> None:
        source = self.make_problem()
        run.side_effect = self.fake_analysis
        with redirect_stdout(StringIO()):
            self.assertTrue(analyze.analyze_one(source, "codex"))
        destination = self.completed_dir / "alpha"
        self.assertFalse(source.exists())
        self.assertTrue((destination / "problem.md").is_file())
        self.assertTrue((destination / "editorial.md").is_file())
        self.assertTrue((destination / "analysis.json").is_file())
        completed = json.loads((destination / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(completed["solution_flow"][0]["skill_index"], 1)
        self.assertEqual(completed["resolved_skills"][0]["path"], "invariants/tracking.md")
        skill.assert_called_once()

    @patch("analyze.process_skills", return_value=None)
    @patch("analyze.run_analysis")
    def test_match_failure_keeps_folder_for_retry(self, run, skill) -> None:
        source = self.make_problem()
        run.side_effect = self.fake_analysis
        with redirect_stdout(StringIO()):
            self.assertFalse(analyze.analyze_one(source, "codex"))
        self.assertTrue(source.is_dir())
        self.assertFalse((self.completed_dir / "alpha").exists())

    def test_rejects_practice_stage_and_destination_collision(self) -> None:
        source = self.make_problem()
        outside = self.practice_dir / "beta"
        outside.mkdir()
        with self.assertRaisesRegex(ValueError, "Only problem folders"):
            analyze.analyze_one(outside, "codex")
        (self.completed_dir / "alpha").mkdir()
        with self.assertRaises(FileExistsError):
            analyze.analyze_one(source, "codex")
        self.assertTrue(source.is_dir())

    def test_editorial_name_falls_back_to_solution(self) -> None:
        source = self.analyze_dir / "old"
        source.mkdir()
        legacy = source / "solution.md"
        legacy.write_text("Old editorial", encoding="utf-8")
        self.assertEqual(analyze.editorial_file(source), legacy)

    @patch("sys.argv", ["analyze.py"])
    @patch("analyze.process_skills", return_value=[{
        "skill_index": 1, "decision": "CREATE_NEW", "path": "invariants/tracking.md",
        "written": True, "verification": "verification-1.json",
    }])
    @patch("analyze.run_analysis")
    def test_batch_moves_successes_and_keeps_failures(self, run, skill) -> None:
        good = self.make_problem("good")
        bad = self.analyze_dir / "bad"
        bad.mkdir()
        (bad / "problem.md").write_text("# Incomplete\n", encoding="utf-8")
        run.side_effect = self.fake_analysis
        with redirect_stdout(StringIO()), patch("sys.stderr", new=StringIO()):
            with self.assertRaises(SystemExit) as raised:
                analyze.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse(good.exists())
        self.assertTrue((self.completed_dir / "good" / "analysis.json").is_file())
        self.assertTrue(bad.is_dir())
        self.assertFalse((self.completed_dir / "bad").exists())

    @patch("analyze.verify_skill_claims", return_value=True)
    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "Distinct."))
    @patch("analyze.run_analysis")
    def test_two_skills_are_saved_with_their_solution_flow(self, run, match, verify) -> None:
        source = self.make_problem("two-skills")
        with tempfile.TemporaryDirectory(dir=analyze.ROOT) as directory:
            with patch("analyze.SKILLS_DIR", Path(directory) / "skills"):
                def generate(provider, folder, output):
                    self.fake_analysis(provider, folder, output)
                    data = json.loads(output.read_text(encoding="utf-8"))
                    second = deepcopy(data["skills"][0])
                    second["skill_path"] = ["graphs", "successor-jumps"]
                    second["how_to_apply"] = ["Jump along repeated successor transitions."]
                    data["skills"].append(second)
                    data["solution_flow"].append({
                        "skill_index": 2,
                        "application": "Skip many successor transitions after finding the invariant.",
                    })
                    output.write_text(json.dumps(data), encoding="utf-8")
                run.side_effect = generate

                with redirect_stdout(StringIO()):
                    self.assertTrue(analyze.analyze_one(source, "codex"))

                self.assertEqual(match.call_count, 2)
                self.assertEqual(verify.call_count, 2)
                self.assertEqual(
                    [call.kwargs["skill_index"] for call in verify.call_args_list], [1, 2]
                )
                self.assertTrue((Path(directory) / "skills" / "invariants" / "tracking.md").is_file())
                self.assertTrue((Path(directory) / "skills" / "graphs" / "successor-jumps.md").is_file())
                completed = json.loads(
                    (self.completed_dir / "two-skills" / "analysis.json").read_text(encoding="utf-8")
                )
                self.assertEqual(len(completed["solution_flow"]), 2)
                self.assertEqual(
                    [item["path"] for item in completed["resolved_skills"]],
                    ["invariants/tracking.md", "graphs/successor-jumps.md"],
                )

    @patch("analyze.verify_skill_claims", side_effect=[True, False])
    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "Distinct."))
    @patch("analyze.run_analysis")
    def test_second_skill_failure_writes_no_skills(self, run, match, verify) -> None:
        source = self.make_problem("failed-pair")
        with tempfile.TemporaryDirectory(dir=analyze.ROOT) as directory:
            skills_dir = Path(directory) / "skills"
            with patch("analyze.SKILLS_DIR", skills_dir):
                def generate(provider, folder, output):
                    self.fake_analysis(provider, folder, output)
                    data = json.loads(output.read_text(encoding="utf-8"))
                    second = deepcopy(data["skills"][0])
                    second["skill_path"] = ["graphs", "successor-jumps"]
                    data["skills"].append(second)
                    data["solution_flow"].append({
                        "skill_index": 2, "application": "Jump along successor transitions."
                    })
                    output.write_text(json.dumps(data), encoding="utf-8")
                run.side_effect = generate

                with redirect_stdout(StringIO()):
                    self.assertFalse(analyze.analyze_one(source, "codex"))

                self.assertTrue(source.is_dir())
                self.assertFalse(skills_dir.exists())
                self.assertFalse((self.completed_dir / "failed-pair").exists())

    def test_write_failure_restores_earlier_skill(self) -> None:
        with tempfile.TemporaryDirectory(dir=analyze.ROOT) as directory:
            skills = Path(directory) / "skills"
            first = skills / "first.md"
            second = skills / "second.md"
            skills.mkdir()
            second.write_text("Existing note\n", encoding="utf-8")
            plans = [
                analyze.SkillPlan(1, "CREATE_NEW", first, "# First\n"),
                analyze.SkillPlan(2, "CREATE_NEW", second, "# Second\n"),
            ]

            with self.assertRaises(FileExistsError):
                analyze.apply_skill_plans(plans, apply_extensions=False)

            self.assertFalse(first.exists())
            self.assertEqual(second.read_text(encoding="utf-8"), "Existing note\n")

    def test_changed_existing_skill_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(dir=analyze.ROOT) as directory:
            existing = Path(directory) / "skill.md"
            existing.write_text("# Original\n", encoding="utf-8")
            plan = analyze.SkillPlan(
                1, "EXTEND", existing, "# Proposal\n", "# Original\n"
            )
            existing.write_text("# Edited during review\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "changed during review"):
                analyze.apply_skill_plans([plan], apply_extensions=True)

            self.assertEqual(existing.read_text(encoding="utf-8"), "# Edited during review\n")


if __name__ == "__main__":
    unittest.main()
