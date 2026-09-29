import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analyze
from Helper import evaluate


class MultiSkillEvaluationTests(unittest.TestCase):
    def test_evaluation_reports_each_skill_without_writing_notes(self) -> None:
        with tempfile.TemporaryDirectory(dir=analyze.ROOT) as directory:
            root = Path(directory)
            problem = root / "problem"
            problem.mkdir()
            (problem / "problem.md").write_text("Use two techniques.\n", encoding="utf-8")
            (problem / "editorial.md").write_text("Apply both techniques.\n", encoding="utf-8")
            skills_dir = root / "skills"
            existing = skills_dir / "graphs" / "successor-jumps.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("# Successor Jumps\n", encoding="utf-8")

            def skill(path):
                return {
                    "skill_path": path,
                    "signals": ["Repeated transitions appear."],
                    "questions": ["Can I skip transitions?"],
                    "how_to_apply": ["Identify and jump over transitions."],
                    "why_it_works": ["Each jump represents consecutive transitions."],
                    "when_it_fails": ["Transitions change between jumps."],
                    "reasoning_patterns": ["Compress repeated transitions."],
                    "probably_related": [],
                }

            analysis = {
                "core_idea": "Use an invariant, then jump along transitions.",
                "key_observations": [],
                "solution_flow": [
                    {"skill_index": 1, "application": "Find the invariant."},
                    {"skill_index": 2, "application": "Skip repeated transitions."},
                ],
                "skills": [
                    skill(["invariants", "tracking"]),
                    skill(["graphs", "successor-jumps"]),
                ],
            }

            def generate(provider, folder, output):
                output.write_text(json.dumps(analysis), encoding="utf-8")

            with patch("analyze.SKILLS_DIR", skills_dir), \
                 patch("Helper.evaluate.SKILLS_DIR", skills_dir), \
                 patch("Helper.evaluate.run_analysis", side_effect=generate), \
                 patch("Helper.evaluate.ask_existing_skill_match", side_effect=[
                     ("CREATE_NEW", None, "Distinct."),
                     ("REUSE", existing, "Already covered."),
                 ]):
                result = evaluate.evaluate_case(
                    {"id": "two", "problem_dir": str(problem)},
                    "codex", root / "results",
                )

            self.assertEqual(
                result["actual"]["skills"],
                [
                    {"decision": "CREATE_NEW", "path": None},
                    {"decision": "REUSE", "path": "graphs/successor-jumps"},
                ],
            )
            self.assertEqual(len(result["analysis"]["solution_flow"]), 2)
            self.assertFalse((skills_dir / "invariants" / "tracking.md").exists())


if __name__ == "__main__":
    unittest.main()
