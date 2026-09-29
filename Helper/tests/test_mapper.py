import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from analyze import (
    ROOT,
    SKILLS_DIR,
    ask_existing_skill_match,
    draft_skill_extension,
    extract_json_response,
    get_skill_path,
    process_skill,
    validate_analysis_response,
    validate_match_response,
    normalize_skill_path_parts,
    missing_teaching_sections,
    skill_content,
    skill_quality_warnings,
    validate_skill_path_parts,
)
from Helper.skill_search import load_skill_documents, rank_candidates


@contextmanager
def seeded_library():
    """Give tests a private library instead of depending on local ignored skills."""
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        skills = Path(directory) / "skills"
        skill = skills / "invariants" / "minimum-level.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "# Minimum Level\n\n## Questions\n\n- What is the minimum level?\n",
            encoding="utf-8",
        )
        with patch("analyze.SKILLS_DIR", skills):
            yield skills, skill


def teaching_extension(before: str, insight: str) -> str:
    return (
        before
        + "\n## Signals\n\n- A preserved statistic appears.\n"
        + f"\n## How to Apply\n\n1. {insight}\n"
        + "\n## Why It Works\n\n- Each transition preserves the statistic.\n"
        + "\n## When It Fails\n\n- Another transition can change it.\n"
    )


def completed_analysis(skill: dict) -> dict:
    return {
        "core_idea": "Use the extracted technique.",
        "key_observations": [],
        "solution_flow": [{"skill_index": 1, "application": "Apply it here."}],
        "skills": [skill],
    }


class SkillSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.problem_dir = Path(temporary.name)
        verifier = patch("analyze.verify_skill_claims", return_value=True)
        verifier.start()
        self.addCleanup(verifier.stop)

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

    def test_skill_path_rejects_traversal_and_unsafe_terms(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            validate_skill_path_parts(["games", "..", "secret"])

        with self.assertRaisesRegex(ValueError, "implementation details"):
            validate_skill_path_parts(["variable", "powers"])

    def test_skill_path_rejects_invalid_segment_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "lowercase"):
            validate_skill_path_parts(["Greedy Ideas"])

    def test_skill_path_normalizes_phrase_labels_and_broad_category(self) -> None:
        self.assertEqual(
            normalize_skill_path_parts(
                [
                    "greedy optimization",
                    "successor structures",
                    "binary lifting",
                ]
            ),
            ["greedy", "successor-structures", "binary-lifting"],
        )

    def test_skill_quality_validator_warns_without_rejecting_content(self) -> None:
        warnings = skill_quality_warnings(
            "In this problem, use two pointers and precompute transitions for index i."
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("in this problem", warnings[0])
        self.assertEqual(
            skill_quality_warnings("Let index i satisfy $dp[i] = dp[i-1] + 1$."),
            [],
        )
        self.assertEqual(
            skill_quality_warnings(
                "Use two pointers, binary lifting, suffix arrays, segment trees, "
                "precompute, iterate, and scan as reusable algorithmic ideas."
            ),
            [],
        )

    def test_analysis_response_requires_all_schema_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "Analysis needs"):
            validate_analysis_response({"core_idea": "invariant"})

    def test_analysis_response_requires_teaching_fields(self) -> None:
        skill = {
            "reasoning_patterns": ["Track the invariant."],
            "questions": ["What stays unchanged?"],
            "skill_path": ["invariants"],
            "probably_related": [],
        }
        analysis = completed_analysis(skill)
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_analysis_response(analysis)

        skill.update({
            "signals": ["An operation preserves a quantity."],
            "how_to_apply": ["Identify the preserved quantity."],
            "why_it_works": ["Each transition keeps it constant."],
            "when_it_fails": ["An operation can change that quantity."],
        })
        self.assertEqual(validate_analysis_response(analysis), analysis)

    def test_teaching_fields_cannot_be_blank(self) -> None:
        analysis = completed_analysis({
            "reasoning_patterns": ["Track an invariant."],
            "questions": ["What stays unchanged?"],
            "signals": ["A move may preserve a value."],
            "how_to_apply": ["  "],
            "why_it_works": ["Each move preserves the value."],
            "when_it_fails": ["Some moves can change it."],
            "skill_path": ["invariants"],
            "probably_related": [],
        })
        with self.assertRaisesRegex(ValueError, "how_to_apply.*useful item"):
            validate_analysis_response(analysis)

    def test_solution_flow_must_reference_each_real_skill(self) -> None:
        skill = {
            "skill_path": ["greedy", "safe-choice"],
            "signals": ["Choices affect future feasibility."],
            "questions": ["Can I preserve feasibility?"],
            "how_to_apply": ["Check that a completion remains."],
            "why_it_works": ["The invariant keeps a completion available."],
            "when_it_fails": ["The check omits a required constraint."],
            "reasoning_patterns": ["Preserve future feasibility."],
            "probably_related": [],
        }
        analysis = completed_analysis(skill)
        analysis["solution_flow"][0]["skill_index"] = 2
        with self.assertRaisesRegex(ValueError, "nonexistent skill_index"):
            validate_analysis_response(analysis)

    def test_skill_note_teaches_application_proof_and_boundary(self) -> None:
        analysis = {
            "signals": ["A choice must keep a resource available."],
            "questions": ["What must remain feasible?"],
            "how_to_apply": ["Choose a move only if the remaining state stays feasible."],
            "why_it_works": ["If $f(s) \\ge 0$ is preserved, every choice leaves a completion."],
            "when_it_fails": ["The test fails when $f(s)$ overlooks a required constraint."],
            "reasoning_patterns": ["Preserve future feasibility."],
            "probably_related": [],
        }
        content = skill_content(analysis, SKILLS_DIR / "greedy" / "safe-choice.md")
        self.assertIn("## Signals\n\n- A choice", content)
        self.assertIn("## How to Apply\n\n1. Choose", content)
        self.assertIn("## Why It Works\n\n- If $f(s) \\ge 0$", content)
        self.assertIn("## When It Fails\n\n- The test fails", content)
        self.assertEqual(missing_teaching_sections(content), [])
        self.assertIn(
            "Signals",
            missing_teaching_sections("## Signals\n\n## How to Apply\n\n1. Try a move.\n"),
        )

    def test_analysis_response_rejects_empty_skill_content(self) -> None:
        analysis = completed_analysis({
            "reasoning_patterns": [],
            "questions": [],
            "signals": [],
            "how_to_apply": [],
            "why_it_works": [],
            "when_it_fails": [],
            "skill_path": ["invariants"],
            "probably_related": [],
        })
        with self.assertRaisesRegex(ValueError, "needs a useful item"):
            validate_analysis_response(analysis)

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

    @patch("analyze.subprocess.run")
    def test_copilot_match_sends_a_string_to_standard_input(self, run) -> None:
        with seeded_library() as (skills, _):
            candidate = load_skill_documents(skills)[0]
            run.return_value.stdout = (
                '{"decision":"REUSE",'
                f'"path":"{candidate.relative_path}",'
                '"reason":"Same technique."}'
            )
            analysis = {
                "core_idea": "classify game positions using minimum level",
                "skill_path": ["games/invariants/minimum_valuation"],
            }
            decision, existing, _ = ask_existing_skill_match(analysis, "copilot")
            self.assertEqual(decision, "REUSE")
            self.assertIsNotNone(existing)
            self.assertIsInstance(run.call_args.kwargs["input"], str)

    @patch("analyze.subprocess.run")
    def test_codex_match_sends_candidate_notes_via_standard_input(self, run) -> None:
        with seeded_library() as (skills, _):
            candidate = load_skill_documents(skills)[0]

            def reply(command, **kwargs):
                output = Path(command[command.index("-o") + 1])
                output.write_text(
                    '{"decision":"REUSE","path":"'
                    + candidate.relative_path
                    + '","reason":"Same technique."}',
                    encoding="utf-8",
                )
            run.side_effect = reply
            analysis = {
                "core_idea": "Use a minimum level invariant.",
                "skill_path": ["invariants", "minimum-level"],
            }

            decision, existing, _ = ask_existing_skill_match(analysis, "codex")

            self.assertEqual(decision, "REUSE")
            self.assertIsNotNone(existing)
            self.assertEqual(run.call_args.args[0][-1], "-")
            self.assertIn("EXISTING SKILL CANDIDATES", run.call_args.kwargs["input"])

    @patch("analyze.subprocess.run")
    def test_codex_extension_sends_full_note_via_standard_input(self, run) -> None:
        with seeded_library() as (_, existing):
            def reply(command, **kwargs):
                output = Path(command[command.index("-o") + 1])
                output.write_text(
                    teaching_extension(existing.read_text(encoding="utf-8"), "Keep the invariant."),
                    encoding="utf-8",
                )
            run.side_effect = reply

            proposal = draft_skill_extension({"core_idea": "invariant"}, existing, "codex")

            self.assertIn("## Why It Works", proposal)
            self.assertEqual(run.call_args.args[0][-1], "-")
            self.assertIn("EXISTING SKILL:", run.call_args.kwargs["input"])

    @patch("analyze.subprocess.run", side_effect=OSError("CLI unavailable"))
    def test_matcher_failure_does_not_create_a_new_skill(self, run) -> None:
        analysis = {
            "core_idea": "classify states using an invariant",
            "skill_path": ["__review_test__", "matcher_failure"],
        }

        decision, existing, reason = ask_existing_skill_match(analysis, "copilot")

        self.assertEqual(decision, "MATCH_FAILED")
        self.assertIsNone(existing)
        self.assertEqual(reason, "Matcher failed.")

    @patch("analyze.ask_existing_skill_match")
    def test_review_mode_previews_without_creating_a_skill(self, match) -> None:
        match.return_value = ("CREATE_NEW", None, "No match.")
        analysis = {
            "skill_path": ["__review_test__/preview_only"],
            "core_idea": "Compress the state to its decisive invariant.",
            "signals": ["A small statistic controls feasibility."],
            "questions": ["Can I find an invariant?"],
            "how_to_apply": ["Identify the decisive statistic."],
            "why_it_works": ["All future choices depend only on that statistic."],
            "when_it_fails": ["It fails if another state detail affects a transition."],
            "key_observations": ["The state can be compressed."],
            "reasoning_patterns": ["Preserve the useful invariant."],
            "probably_related": [],
        }
        target = SKILLS_DIR / "__review_test__" / "preview_only.md"
        self.assertFalse(target.exists())

        output = StringIO()
        with redirect_stdout(output):
            process_skill(analysis, "codex", self.problem_dir, review=True)

        self.assertFalse(target.exists())
        self.assertIn("New-skill preview (not written)", output.getvalue())
        self.assertIn("+++ skills/__review_test__/preview_only.md", output.getvalue())
        self.assertIn("## Signals", output.getvalue())
        self.assertIn("A small statistic controls feasibility.", output.getvalue())
        self.assertIn("## How to Apply", output.getvalue())
        self.assertIn("## Why It Works", output.getvalue())
        self.assertIn("## When It Fails", output.getvalue())
        self.assertNotIn("## Core Idea", output.getvalue())
        self.assertNotIn("## Key Observations", output.getvalue())
        self.assertNotIn("Compress the state to its decisive invariant.", output.getvalue())

    @patch("analyze.draft_skill_extension")
    @patch("analyze.ask_existing_skill_match")
    def test_review_mode_previews_an_extension_without_writing(
        self,
        match,
        draft,
    ) -> None:
        with seeded_library() as (_, existing):
            before = existing.read_text(encoding="utf-8")
            match.return_value = ("EXTEND", existing, "Related technique.")
            draft.return_value = teaching_extension(before, "Use the new reusable detail.")
            analysis = {"skill_path": ["__review_test__/extension_preview"]}

            output = StringIO()
            with redirect_stdout(output):
                process_skill(analysis, "codex", self.problem_dir, review=True)

            self.assertEqual(existing.read_text(encoding="utf-8"), before)
            self.assertIn("Extension preview (not written)", output.getvalue())
            self.assertIn("+## How to Apply", output.getvalue())

    @patch("builtins.input", return_value="y")
    @patch("analyze.draft_skill_extension")
    @patch("analyze.ask_existing_skill_match")
    def test_apply_extension_requires_flag_and_confirmation(
        self,
        match,
        draft,
        confirm,
    ) -> None:
        with seeded_library() as (_, existing):
            before = existing.read_text(encoding="utf-8")
            proposal = teaching_extension(before, "Use the new reusable detail.")
            match.return_value = ("EXTEND", existing, "Related technique.")
            draft.return_value = proposal

            process_skill({"skill_path": ["unused"]}, "codex", self.problem_dir, apply_extension=True)

            self.assertEqual(existing.read_text(encoding="utf-8"), proposal)
            confirm.assert_called_once()

    @patch("analyze.draft_skill_extension")
    @patch("analyze.ask_existing_skill_match")
    def test_extension_stays_unmodified_without_apply_flag(self, match, draft) -> None:
        with seeded_library() as (_, existing):
            before = existing.read_text(encoding="utf-8")
            match.return_value = ("EXTEND", existing, "Related technique.")
            draft.return_value = teaching_extension(before, "Preview only.")

            process_skill({"skill_path": ["unused"]}, "codex", self.problem_dir)

            self.assertEqual(existing.read_text(encoding="utf-8"), before)

    @patch("analyze.draft_skill_extension")
    @patch("analyze.ask_existing_skill_match")
    def test_extension_without_teaching_sections_is_rejected(self, match, draft) -> None:
        with seeded_library() as (_, existing):
            before = existing.read_text(encoding="utf-8")
            match.return_value = ("EXTEND", existing, "Related technique.")
            draft.return_value = before + "\n## Extra Insight\n\n- Generic advice.\n"
            output = StringIO()

            with redirect_stdout(output):
                result = process_skill({"skill_path": ["unused"]}, "codex", self.problem_dir)

            self.assertEqual(result, "EXTEND_FAILED")
            self.assertEqual(existing.read_text(encoding="utf-8"), before)
            self.assertIn("Extension lacks teaching sections", output.getvalue())

    @patch("analyze.ask_existing_skill_match", return_value=("CREATE_NEW", None, "Different insight."))
    def test_existing_path_collision_does_not_overwrite_skill(self, match) -> None:
        with seeded_library() as (_, existing):
            before = existing.read_text(encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                process_skill({"skill_path": ["invariants", "minimum-level"]}, "codex", self.problem_dir)
            self.assertEqual(existing.read_text(encoding="utf-8"), before)
            self.assertIn("PATH COLLISION", output.getvalue())
            match.assert_called_once()

    @patch("analyze.ask_existing_skill_match")
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
            process_skill(analysis, "codex", self.problem_dir)

        self.assertFalse(target.exists())
        self.assertIn("No skill was created.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
