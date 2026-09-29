"""Connect an optional learner attempt to the problem's extracted skills."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path


HELPER_DIR = Path(__file__).resolve().parent
PROMPT_FILE = HELPER_DIR / "prompts" / "attempt_review.md"
SCHEMA_FILE = HELPER_DIR / "config" / "attempt_review_schema.json"
GENERATED_MARKER = "<!-- Generated from attempt.md by Helper/attempt_review.py -->"


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def validate_attempt_review(value: object, attempt: str, skill_count: int) -> dict:
    """Reject invented excerpts and references to skills outside the analysis."""
    if not isinstance(value, dict) or set(value) != {"observations", "skill_connections"}:
        raise ValueError("Attempt review needs observations and skill_connections only.")
    if not isinstance(value["observations"], list) or not isinstance(value["skill_connections"], list):
        raise ValueError("Attempt review entries must be lists.")

    source = _normalized(attempt)
    for item in value["observations"]:
        if not isinstance(item, dict) or set(item) != {"evidence", "what_it_shows"}:
            raise ValueError("Each observation needs evidence and what_it_shows.")
        if not isinstance(item["what_it_shows"], str) or not item["what_it_shows"].strip():
            raise ValueError("Each observation needs an explanation.")
        _check_evidence(item["evidence"], source)

    for item in value["skill_connections"]:
        if not isinstance(item, dict) or set(item) != {
            "skill_index", "evidence", "connection", "practice_task"
        }:
            raise ValueError("Each skill connection needs an index, evidence, connection, and task.")
        index = item["skill_index"]
        if type(index) is not int or not 1 <= index <= skill_count:
            raise ValueError("Skill connection refers to a nonexistent skill_index.")
        for field in ("connection", "practice_task"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"Skill connection needs a useful {field}.")
        _check_evidence(item["evidence"], source)
    return value


def _check_evidence(evidence: object, source: str) -> None:
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Attempt evidence must be a nonempty excerpt.")
    if len(evidence) > 240:
        raise ValueError("Attempt evidence must be a short excerpt (240 characters or fewer).")
    if _normalized(evidence) not in source:
        raise ValueError(f"Attempt evidence was not found in attempt.md: {evidence!r}")


def render_learning_review(review: dict, analysis: dict) -> str:
    """Make the structured review easy to read beside a completed problem."""
    lines = [
        GENERATED_MARKER,
        "# Learning Review",
        "",
        "Based on [attempt.md](attempt.md) and this problem's editorial.",
        "",
        "## What You Recorded",
        "",
    ]
    if review["observations"]:
        for item in review["observations"]:
            lines.extend([
                f"> {' '.join(item['evidence'].split())}",
                "",
                item["what_it_shows"],
                "",
            ])
    else:
        lines.extend(["The attempt does not give enough detail for a specific observation.", ""])

    lines.extend(["## Connections to Skills", ""])
    if review["skill_connections"]:
        for item in review["skill_connections"]:
            path = "/".join(analysis["skills"][item["skill_index"] - 1]["skill_path"])
            lines.extend([
                f"### Skill {item['skill_index']}: `{path}`",
                "",
                f"> {' '.join(item['evidence'].split())}",
                "",
                item["connection"],
                "",
                f"**Practice next:** {item['practice_task']}",
                "",
            ])
    else:
        lines.extend(["No skill gap can be inferred from the recorded attempt.", ""])
    return "\n".join(lines).rstrip() + "\n"


def _extract_json(response: str) -> dict:
    response = response.strip()
    try:
        value = json.loads(response)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.I | re.S)
        if not fenced:
            raise
        value = json.loads(fenced.group(1))
    if not isinstance(value, dict):
        raise ValueError("Attempt review response must be a JSON object.")
    return value


def review_attempt_if_present(
    problem_dir: Path,
    analysis: dict,
    provider: str,
    root: Path,
    copilot_cli: str,
) -> dict | None:
    """Run one separate review only when the learner supplied attempt.md."""
    attempt_file = problem_dir / "attempt.md"
    if not attempt_file.is_file():
        _remove_generated_review(problem_dir)
        return None
    attempt = attempt_file.read_text(encoding="utf-8")
    if not attempt.strip():
        _remove_generated_review(problem_dir)
        return None

    editorial = problem_dir / "editorial.md"
    if not editorial.is_file():
        editorial = problem_dir / "solution.md"
    prompt = f"""{PROMPT_FILE.read_text(encoding='utf-8')}

PROBLEM:
{(problem_dir / 'problem.md').read_text(encoding='utf-8')}

EDITORIAL:
{editorial.read_text(encoding='utf-8')}

LEARNER ATTEMPT (the only source for evidence about the learner):
{attempt}

EXTRACTED SKILL ANALYSIS:
{json.dumps(analysis, indent=2, ensure_ascii=False)}

Return only one JSON object. Do not use tools.
"""

    try:
        if provider == "codex":
            with tempfile.NamedTemporaryFile(
                prefix="attempt-review-", suffix=".json", dir=root, delete=False
            ) as handle:
                output_file = Path(handle.name)
            try:
                subprocess.run(
                    [
                        "codex", "exec", "--sandbox", "read-only", "--output-schema",
                        str(SCHEMA_FILE), "-o", str(output_file), "-",
                    ],
                    cwd=root, check=True, capture_output=True, text=True,
                    encoding="utf-8", timeout=240, input=prompt,
                )
                value = _extract_json(output_file.read_text(encoding="utf-8"))
            finally:
                output_file.unlink(missing_ok=True)
        else:
            completed = subprocess.run(
                [copilot_cli, "--silent", "--no-ask-user", "--output-format=text"],
                cwd=root, check=True, capture_output=True, text=True,
                encoding="utf-8", timeout=240,
                input=f"{prompt}\nREQUIRED JSON SCHEMA:\n{SCHEMA_FILE.read_text(encoding='utf-8')}",
            )
            value = _extract_json(completed.stdout)
        review = validate_attempt_review(value, attempt, len(analysis["skills"]))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"Could not review attempt.md: {error}") from error

    (problem_dir / "attempt_review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (problem_dir / "learning_review.md").write_text(
        render_learning_review(review, analysis), encoding="utf-8"
    )
    return review


def _remove_generated_review(problem_dir: Path) -> None:
    """Discard a stale generated review when its source attempt is gone."""
    summary = problem_dir / "learning_review.md"
    if summary.is_file() and summary.read_text(encoding="utf-8").startswith(GENERATED_MARKER):
        summary.unlink()
        (problem_dir / "attempt_review.json").unlink(missing_ok=True)
