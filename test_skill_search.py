import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from main import (
    SKILLS_DIR,
    ask_existing_skill_match,
    extract_json_response,
    get_skill_path,
    process_skill,
    validate_analysis_response,
    validate_match_response,
)
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

    def test_get_skill_path_accepts_string_and_fragment_lists(self) -> None:
        analysis = {"skill_path": ["games", "invariants", "minimum_valuation"]}
        self.assertEqual(
            get_skill_path(analysis),
            SKILLS_DIR / "games" / "invariants" / "minimum_valuation.md",
        )

        analysis = {"skill_path": "game_theory/valuation"}
        self.assertEqual(
            get_skill_path(analysis),
            SKILLS_DIR / "game_theory" / "valuation.md",
        )

    def test_analysis_response_requires_all_schema_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_analysis_response({"core_idea": "invariant"})

    def test_match_response_rejects_invalid_decision(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid value"):
            validate_match_response(
                {"decision": "MAYBE", "path": None, "reason": "Unclear."}
            )

    def test_match_response_requires_path_for_reuse(self) -> None:
        with self.assertRaisesRegex(ValueError, "must provide a path"):
            validate_match_response(
                {"decision": "REUSE", "path": None, "reason": "Same skill."}
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

    @patch("main.ask_existing_skill_match")
    def test_review_mode_previews_without_creating_a_skill(self, match) -> None:
        match.return_value = ("CREATE_NEW", None, "No match.")
        analysis = {
            "skill_path": ["__review_test__/preview_only"],
            "questions": ["Can I find an invariant?"],
            "key_observations": ["The state can be compressed."],
            "reasoning_patterns": ["Preserve the useful invariant."],
            "probably_related": [],
        }
        target = SKILLS_DIR / "__review_test__" / "preview_only.md"
        self.assertFalse(target.exists())

        output = StringIO()
        with redirect_stdout(output):
            process_skill(analysis, "codex", review=True)

        self.assertFalse(target.exists())
        self.assertIn("New-skill preview (not written)", output.getvalue())
        self.assertIn("+++ skills/__review_test__/preview_only.md", output.getvalue())

    @patch("main.draft_skill_extension")
    @patch("main.ask_existing_skill_match")
    def test_review_mode_previews_an_extension_without_writing(
        self,
        match,
        draft,
    ) -> None:
        candidate = load_skill_documents(SKILLS_DIR)[0]
        existing = candidate.path
        before = existing.read_text(encoding="utf-8")
        match.return_value = ("EXTEND", existing, "Related technique.")
        draft.return_value = before + "\n## Extra Insight\n\n- New reusable detail.\n"
        analysis = {"skill_path": ["__review_test__/extension_preview"]}

        output = StringIO()
        with redirect_stdout(output):
            process_skill(analysis, "codex", review=True)

        self.assertEqual(existing.read_text(encoding="utf-8"), before)
        self.assertIn("Extension preview (not written)", output.getvalue())
        self.assertIn("+## Extra Insight", output.getvalue())


if __name__ == "__main__":
    unittest.main()
