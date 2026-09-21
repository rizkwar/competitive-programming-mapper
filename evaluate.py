"""Evaluate analysis and existing-skill matching without writing skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from main import (
    ROOT,
    SKILLS_DIR,
    ask_existing_skill_match,
    get_skill_path,
    load_analysis,
    run_analysis,
    validate_files,
)
from skill_search import load_skill_documents, rank_candidates


DEFAULT_SUITE = ROOT / "evaluation" / "cases.json"
DEFAULT_RESULTS = ROOT / "evaluation_results"


def relative_skill_path(skill_file: Path | None) -> str | None:
    if skill_file is None:
        return None
    return skill_file.relative_to(SKILLS_DIR).with_suffix("").as_posix()


def evaluate_case(case: dict, provider: str, results_dir: Path) -> dict:
    """Run one case through analysis and matching, but never create a skill."""
    case_id = case["id"]
    configured_path = Path(case["problem_dir"])
    problem_dir = (
        configured_path
        if configured_path.is_absolute()
        else (ROOT / configured_path).resolve()
    )
    validate_files(problem_dir)

    case_dir = results_dir / provider / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    analysis_file = case_dir / "analysis.json"
    run_analysis(provider, problem_dir, analysis_file)
    analysis = load_analysis(analysis_file, provider)

    candidates = rank_candidates(
        analysis,
        load_skill_documents(SKILLS_DIR),
    )
    proposed_file = get_skill_path(analysis)
    if proposed_file.exists():
        decision = "REUSE"
        selected = proposed_file
        reason = "The generated skill path already exists."
    else:
        decision, selected, reason = ask_existing_skill_match(analysis, provider)

    expected = case.get("expected")
    actual = {
        "decision": decision,
        "path": relative_skill_path(selected),
    }
    passed = None
    if expected is not None:
        passed = all(actual.get(key) == value for key, value in expected.items())

    result = {
        "id": case_id,
        "provider": provider,
        "problem_dir": case["problem_dir"],
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "reason": reason,
        "proposed_skill_path": relative_skill_path(proposed_file),
        "retrieved_candidates": [
            {
                "path": candidate.relative_path,
                "title": candidate.title,
            }
            for candidate in candidates
        ],
        "analysis": analysis,
    }
    (case_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate skill reuse decisions without modifying skills."
    )
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--provider",
        choices=("codex", "copilot"),
        default="codex",
    )
    args = parser.parse_args()

    try:
        suite = json.loads(args.suite.read_text(encoding="utf-8"))
        cases = suite["cases"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        print(f"ERROR: Could not read evaluation suite: {error}")
        sys.exit(1)

    if not isinstance(cases, list) or not cases:
        print("ERROR: The evaluation suite needs at least one case.")
        sys.exit(1)

    results = [evaluate_case(case, args.provider, args.results_dir) for case in cases]
    labeled = [result for result in results if result["passed"] is not None]
    passed = sum(result["passed"] for result in labeled)

    print(f"Evaluated {len(results)} case(s) with {args.provider}.")
    if labeled:
        print(f"Passed {passed}/{len(labeled)} labeled case(s).")
    else:
        print("No cases are labeled yet; review the generated result files.")
    for result in results:
        status = "UNLABELED" if result["passed"] is None else (
            "PASS" if result["passed"] else "FAIL"
        )
        print(f"{status}: {result['id']} → {result['actual']['decision']} "
              f"{result['actual']['path'] or ''}")


if __name__ == "__main__":
    main()
