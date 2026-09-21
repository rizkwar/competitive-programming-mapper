import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import ask_existing_skill_match, extract_json_response
from skill_search import load_skill_documents, rank_candidates


class SkillSearchTests(unittest.TestCase):
    def test_retrieves_semantically_related_existing_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory)
            target = skills / "game_theory" / "valuation.md"
            target.parent.mkdir(parents=True)
            target.write_text(
                "# Minimum Valuation State Classification\n\n"
                "Compress game states using the minimum valuation invariant.\n",
                encoding="utf-8",
            )
            unrelated = skills / "strings" / "prefix.md"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("# Prefix Matching\n\nString prefixes.\n", encoding="utf-8")

            analysis = {
                "core_idea": "compress a game state using the minimum valuation",
                "skill_path": ["games", "invariants", "state_compression"],
            }
            candidates = rank_candidates(analysis, load_skill_documents(skills))

            self.assertEqual(candidates[0].relative_path, "game_theory/valuation")

    def test_empty_index_returns_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                rank_candidates({"core_idea": "invariant"}, load_skill_documents(Path(directory))),
                [],
            )

    def test_parses_copilot_json_wrapped_in_markdown(self) -> None:
        response = "```json\n{\"core_idea\": \"invariant\"}\n```"
        self.assertEqual(
            extract_json_response(response),
            {"core_idea": "invariant"},
        )

    @patch("main.subprocess.run")
    def test_copilot_match_sends_a_string_to_standard_input(self, run) -> None:
        candidate = load_skill_documents(Path("skills"))[0]
        run.return_value.stdout = (
            '{"decision":"REUSE",'
            f'"path":"{candidate.relative_path}",'
            '"reason":"Same technique."}'
        )
        analysis = {
            "core_idea": "classify game positions using valuation parity",
            "skill_path": ["games/invariants/minimum_valuation"],
        }

        decision, existing, _ = ask_existing_skill_match(analysis, "copilot")

        self.assertEqual(decision, "REUSE")
        self.assertIsNotNone(existing)
        self.assertIsInstance(run.call_args.kwargs["input"], str)


if __name__ == "__main__":
    unittest.main()
