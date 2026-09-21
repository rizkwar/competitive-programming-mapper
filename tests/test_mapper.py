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
    validate_skill_path_parts,
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

    def test_skill_path_rejects_traversal_and_implementation_terms(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            validate_skill_path_parts(["games", "..", "secret"])

        with self.assertRaisesRegex(ValueError, "implementation details"):
            validate_skill_path_parts(["precompute", "powers"])

    def test_skill_path_rejects_invalid_segment_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "lowercase"):
            validate_skill_path_parts(["Greedy Ideas"])

    def test_analysis_response_requires_all_schema_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_analysis_response({"core_idea": "invariant"})

    def test_analysis_response_allows_legacy_missing_signals(self) -> None:
        analysis = {
            "core_idea": "invariant",
            "key_observations": [],
            "reasoning_patterns": [],
            "questions": [],
            "skill_path": ["invariants"],
            "probably_related": [],
        }
        self.assertEqual(validate_analysis_response(analysis), analysis)

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

    @patch("main.subprocess.run", side_effect=OSError("CLI unavailable"))
    def test_matcher_failure_does_not_create_a_new_skill(self, run) -> None:
        analysis = {
            "core_idea": "classify states using an invariant",
            "skill_path": ["__review_test__", "matcher_failure"],
        }

        decision, existing, reason = ask_existing_skill_match(analysis, "copilot")

        self.assertEqual(decision, "MATCH_FAILED")
        self.assertIsNone(existing)
        self.assertEqual(reason, "Matcher failed.")

    @patch("main.ask_existing_skill_match")
    def test_review_mode_previews_without_creating_a_skill(self, match) -> None:
        match.return_value = ("CREATE_NEW", None, "No match.")
        analysis = {
            "skill_path": ["__review_test__/preview_only"],
            "core_idea": "Compress the state to its decisive invariant.",
            "signals": ["A small statistic controls feasibility."],
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
        self.assertIn("## Signals", output.getvalue())
        self.assertIn("A small statistic controls feasibility.", output.getvalue())
        self.assertNotIn("## Core Idea", output.getvalue())
        self.assertNotIn("## Key Observations", output.getvalue())
        self.assertNotIn("Compress the state to its decisive invariant.", output.getvalue())

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

    @patch("builtins.input", return_value="y")
    @patch("main.draft_skill_extension")
    @patch("main.ask_existing_skill_match")
    def test_apply_extension_requires_flag_and_confirmation(
        self,
        match,
        draft,
        confirm,
    ) -> None:
        candidate = load_skill_documents(SKILLS_DIR)[0]
        existing = candidate.path
        before = existing.read_text(encoding="utf-8")
        proposal = before + "\n## Extra Insight\n\n- New reusable detail.\n"
        match.return_value = ("EXTEND", existing, "Related technique.")
        draft.return_value = proposal

        process_skill({"skill_path": ["unused"]}, "codex", apply_extension=True)

        self.assertEqual(existing.read_text(encoding="utf-8"), proposal)
        confirm.assert_called_once()
        existing.write_text(before, encoding="utf-8")

    @patch("main.draft_skill_extension")
    @patch("main.ask_existing_skill_match")
    def test_extension_stays_unmodified_without_apply_flag(self, match, draft) -> None:
        candidate = load_skill_documents(SKILLS_DIR)[0]
        existing = candidate.path
        before = existing.read_text(encoding="utf-8")
        match.return_value = ("EXTEND", existing, "Related technique.")
        draft.return_value = before + "\n## Extra Insight\n\n- Preview only.\n"

        process_skill({"skill_path": ["unused"]}, "codex")

        self.assertEqual(existing.read_text(encoding="utf-8"), before)

    @patch("main.ask_existing_skill_match")
    def test_matcher_failure_stops_skill_creation(self, match) -> None:
        match.return_value = ("MATCH_FAILED", None, "Matcher failed.")
        analysis = {
            "skill_path": ["__review_test__", "matcher_failure_process"],
            "questions": [],
            "key_observations": [],
            "reasoning_patterns": [],
            "probably_related": [],
        }
        target = SKILLS_DIR / "__review_test__" / "matcher_failure_process.md"

        output = StringIO()
        with redirect_stdout(output):
            process_skill(analysis, "codex")

        self.assertFalse(target.exists())
        self.assertIn("No skill was created.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
