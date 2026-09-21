import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
