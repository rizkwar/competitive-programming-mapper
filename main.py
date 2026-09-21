import json
import subprocess
import sys
import tempfile
from pathlib import Path

from skill_search import (
    analysis_query,
    candidate_context,
    load_skill_documents,
    rank_candidates,
)


ROOT = Path(__file__).resolve().parent

PROMPT_FILE = ROOT / "prompt.md"
SCHEMA_FILE = ROOT / "schema.json"
MATCH_SCHEMA_FILE = ROOT / "match_schema.json"
SKILLS_DIR = ROOT / "skills"


def validate_files(problem_dir: Path) -> None:
    required_files = [
        PROMPT_FILE,
        SCHEMA_FILE,
        MATCH_SCHEMA_FILE,
        problem_dir / "problem.md",
        problem_dir / "solution.md",
    ]

    for file in required_files:
        if not file.exists():
            print("ERROR: Missing file:")
            print(f"  {file}")
            sys.exit(1)


def run_codex(problem_dir: Path, output_file: Path) -> None:
    problem_file = problem_dir / "problem.md"
    solution_file = problem_dir / "solution.md"

    command = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(SCHEMA_FILE),
        "-o",
        str(output_file),
        (
            "Read prompt.md first. "
            f"Then analyze {problem_file.as_posix()} and "
            f"{solution_file.as_posix()} according to the instructions "
            "in prompt.md. Return the required JSON."
        ),
    ]

    print("Running Codex...")
    print()

    try:
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
        )
    except FileNotFoundError:
        print("ERROR: 'codex' was not found in PATH.")
        print("Make sure Codex CLI is installed and works in PowerShell.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Codex exited with code {e.returncode}.")
        sys.exit(e.returncode)


def load_analysis(output_file: Path) -> dict:
    try:
        data = json.loads(
            output_file.read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        print("ERROR: Codex did not create the output file:")
        print(f"  {output_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print("ERROR: Codex output is not valid JSON.")
        print(f"Line {e.lineno}, column {e.colno}: {e.msg}")
        sys.exit(1)

    output_file.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    return data


def get_skill_path(analysis: dict) -> Path:
    paths = analysis.get("skill_path", [])

    if len(paths) != 1:
        print("ERROR: Expected exactly one skill_path.")
        sys.exit(1)

    skill_path = paths[0].strip("/\\")

    if not skill_path:
        print("ERROR: Empty skill path.")
        sys.exit(1)

    skill_file = (
        SKILLS_DIR / f"{skill_path}.md"
    ).resolve()

    try:
        skill_file.relative_to(SKILLS_DIR.resolve())
    except ValueError:
        print("ERROR: Invalid skill path.")
        sys.exit(1)

    return skill_file


def get_existing_skill_path(relative_path: str) -> Path | None:
    """Resolve a model-selected skill path, rejecting traversal and non-files."""
    candidate = (SKILLS_DIR / relative_path.strip("/\\")).resolve()
    try:
        candidate.relative_to(SKILLS_DIR.resolve())
    except ValueError:
        return None
    if candidate.suffix.lower() != ".md":
        candidate = candidate.with_suffix(".md")
    return candidate if candidate.is_file() else None


def ask_existing_skill_match(analysis: dict) -> tuple[str, Path | None, str]:
    """Ask Codex whether a retrieved existing skill should be reused."""
    candidates = rank_candidates(
        analysis,
        load_skill_documents(SKILLS_DIR),
    )
    if not candidates:
        return "CREATE_NEW", None, "No existing skills were retrieved."

    prompt = f"""You are deciding whether a newly analyzed competitive-programming skill already exists.

NEW ANALYSIS:
{analysis_query(analysis)}

EXISTING SKILL CANDIDATES:
{candidate_context(candidates)}

Return REUSE if a candidate teaches essentially the same reusable technique,
EXTEND if one candidate is the right skill but would need additional coverage,
or CREATE_NEW if none is semantically equivalent.
If you choose REUSE or EXTEND, path must be exactly one candidate PATH.
If you choose CREATE_NEW, path must be null.
"""

    with tempfile.NamedTemporaryFile(
        prefix="skill-match-",
        suffix=".json",
        dir=ROOT,
        delete=False,
    ) as handle:
        output_file = Path(handle.name)

    try:
        try:
            subprocess.run(
                [
                    "codex",
                    "exec",
                    "--sandbox",
                    "read-only",
                    "--output-schema",
                    str(MATCH_SCHEMA_FILE),
                    "-o",
                    str(output_file),
                    prompt,
                ],
                cwd=ROOT,
                check=True,
            )
            result = json.loads(output_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
            print("WARNING: Existing-skill matching failed; continuing with new-skill detection.")
            return "CREATE_NEW", None, "Matcher failed."

        decision = result.get("decision")
        selected = get_existing_skill_path(str(result.get("path") or ""))
        candidate_paths = {candidate.relative_path for candidate in candidates}
        selected_relative = selected.relative_to(SKILLS_DIR).with_suffix("").as_posix() if selected else None
        if decision in {"REUSE", "EXTEND"} and selected_relative in candidate_paths:
            return decision, selected, str(result.get("reason", ""))
        if decision == "CREATE_NEW":
            return decision, None, str(result.get("reason", ""))
        return "CREATE_NEW", None, "Matcher returned an invalid candidate path."
    finally:
        output_file.unlink(missing_ok=True)


def create_skill(analysis: dict) -> Path:
    skill_file = get_skill_path(analysis)

    skill_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = (
        f"# {skill_file.stem.replace('_', ' ').title()}\n\n"

        "## Questions\n\n"
        + "\n".join(
            f"- {question}"
            for question in analysis.get("questions", [])
        )
        + "\n\n"

        "## Key Observations\n\n"
        + "\n".join(
            f"- {observation}"
            for observation in analysis.get(
                "key_observations", []
            )
        )
        + "\n\n"

        "## Reasoning Patterns\n\n"
        + "\n".join(
            f"- {pattern}"
            for pattern in analysis.get(
                "reasoning_patterns", []
            )
        )
        + "\n\n"

        "## Probably Related\n\n"
        + "\n".join(
            f"- {related}"
            for related in analysis.get(
                "probably_related", []
            )
        )
        + "\n"
    )

    skill_file.write_text(
        content,
        encoding="utf-8",
    )

    return skill_file


def process_skill(analysis: dict) -> None:
    skill_file = get_skill_path(analysis)

    print()
    print("Skill detection")
    print("----------------")

    if skill_file.exists():
        print("EXISTING SKILL")
        print(skill_file)
        return

    decision, existing, reason = ask_existing_skill_match(analysis)
    if existing is not None:
        print(f"{decision} EXISTING SKILL")
        print(existing)
        if reason:
            print(f"Reason: {reason}")
        return

    print("NEW SKILL")
    print(skill_file)

    created = create_skill(analysis)

    print()
    print("Created skill:")
    print(created)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python main.py <problem_directory>")
        print()
        print("Example:")
        print("  python main.py test")
        sys.exit(1)

    problem_dir = Path(sys.argv[1]).resolve()

    if not problem_dir.exists():
        print("ERROR: Directory does not exist:")
        print(f"  {problem_dir}")
        sys.exit(1)

    if not problem_dir.is_dir():
        print("ERROR: Path is not a directory:")
        print(f"  {problem_dir}")
        sys.exit(1)

    validate_files(problem_dir)

    output_file = problem_dir / "analysis.json"

    print("========================================")
    print(" Competitive Programming Skill Analyzer")
    print("========================================")
    print()

    run_codex(
        problem_dir,
        output_file,
    )

    print("Reading analysis...")

    analysis = load_analysis(
        output_file
    )

    print()
    print("Analysis saved to:")
    print(f"  {output_file}")

    process_skill(analysis)


if __name__ == "__main__":
    main()
