import json
import tempfile
import unittest
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
                    "reasoning_patterns": ["Track the invariant."],
                    "questions": ["What stays unchanged?"],
                    "skill_path": ["invariants", "tracking"],
                    "probably_related": [],
                }
            ),
            encoding="utf-8",
        )

    @patch("analyze.process_skill", return_value="CREATE_NEW")
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
        skill.assert_called_once()

    @patch("analyze.process_skill", return_value="MATCH_FAILED")
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
    @patch("analyze.process_skill", return_value="CREATE_NEW")
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


if __name__ == "__main__":
    unittest.main()
