import argparse
import difflib
import json
import os
import re
import shutil
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
SKILL_SEGMENT_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]*$")
IMPLEMENTATION_PATH_TERMS = {
    "calculate",
    "complexity",
    "iterate",
    "loop",
    "precompute",
    "variable",
}

PROMPT_FILE = ROOT / "prompt.md"
SCHEMA_FILE = ROOT / "schema.json"
MATCH_SCHEMA_FILE = ROOT / "match_schema.json"
SKILLS_DIR = ROOT / "skills"


def find_cli(name: str) -> str:
    """Prefer npm's Windows shim when another launcher shadows it on PATH."""
    if os.name == "nt" and name == "copilot":
        npm_cli = Path(os.environ.get("APPDATA", "")) / "npm" / "copilot.cmd"
        if npm_cli.is_file():
            return str(npm_cli)

    return shutil.which(name) or name


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


def extract_json_response(response: str) -> dict:
    """Parse a JSON object even when a CLI wraps it in a Markdown fence."""
    response = response.strip()
    try:
        value = json.loads(response)
    except json.JSONDecodeError:
        fenced = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            response,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if fenced:
            value = json.loads(fenced.group(1))
        else:
            raise
    if not isinstance(value, dict):
        raise ValueError("AI response must be a JSON object.")
    return value


def validate_schema_response(
    value: dict,
    *,
    required: tuple[str, ...],
    list_fields: tuple[str, ...] = (),
    string_fields: tuple[str, ...] = (),
    optional_fields: tuple[str, ...] = (),
) -> dict:
    """Validate the small response shapes used by the analysis pipeline."""
    missing = [field for field in required if field not in value]
    if missing:
        raise ValueError(f"AI response is missing required field(s): {', '.join(missing)}.")

    unexpected = sorted(
        set(value)
        - set(required)
        - set(list_fields)
        - set(string_fields)
        - set(optional_fields)
    )
    if unexpected:
        raise ValueError(
            f"AI response contains unexpected field(s): {', '.join(unexpected)}."
        )

    for field in list_fields:
        if field not in value and field in optional_fields:
            continue
        if not isinstance(value[field], list) or not all(
            isinstance(item, str) for item in value[field]
        ):
            raise ValueError(f"AI response field '{field}' must be a list of strings.")

    for field in string_fields:
        if not isinstance(value[field], str):
            raise ValueError(f"AI response field '{field}' must be a string.")

    return value


def validate_analysis_response(value: dict) -> dict:
    return validate_schema_response(
        value,
        required=(
            "core_idea",
            "key_observations",
            "reasoning_patterns",
            "questions",
            "skill_path",
            "probably_related",
        ),
        list_fields=(
            "key_observations",
            "reasoning_patterns",
            "questions",
            "skill_path",
            "probably_related",
            "signals",
        ),
        string_fields=("core_idea",),
        optional_fields=("signals",),
    )


def validate_match_response(value: dict) -> dict:
    validate_schema_response(
        value,
        required=("decision", "path", "reason"),
        string_fields=("decision", "reason"),
        optional_fields=("path",),
    )
    if value["decision"] not in {"REUSE", "EXTEND", "CREATE_NEW"}:
        raise ValueError("AI response field 'decision' has an invalid value.")
    if value["path"] is not None and not isinstance(value["path"], str):
        raise ValueError("AI response field 'path' must be a string or null.")
    if value["decision"] == "CREATE_NEW" and value["path"] is not None:
        raise ValueError("CREATE_NEW responses must use a null path.")
    if value["decision"] in {"REUSE", "EXTEND"} and not value["path"]:
        raise ValueError(f"{value['decision']} responses must provide a path.")
    return value


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


def run_copilot(problem_dir: Path, output_file: Path) -> None:
    """Run GitHub Copilot CLI without giving it file or shell permissions."""
    prompt = f"""Analyze a competitive-programming problem and solution.

TASK INSTRUCTIONS:
{PROMPT_FILE.read_text(encoding="utf-8")}

REQUIRED JSON SCHEMA:
{SCHEMA_FILE.read_text(encoding="utf-8")}

PROBLEM:
{(problem_dir / "problem.md").read_text(encoding="utf-8")}

SOLUTION:
{(problem_dir / "solution.md").read_text(encoding="utf-8")}

Do not use tools. Return only one JSON object that conforms to the schema.
"""
    command = [
        find_cli("copilot"),
        "--silent",
        "--no-ask-user",
        "--output-format=text",
    ]

    print("Running GitHub Copilot...")
    print()

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            input=prompt,
        )
        analysis = extract_json_response(completed.stdout)
        output_file.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except FileNotFoundError:
        print("ERROR: 'copilot' was not found in PATH.")
        print("Install and authenticate GitHub Copilot CLI, then try again.")
        sys.exit(1)
    except subprocess.CalledProcessError as error:
        print("ERROR: GitHub Copilot CLI failed.")
        if error.stderr:
            print(error.stderr.strip())
        sys.exit(error.returncode)
    except json.JSONDecodeError:
        print("ERROR: GitHub Copilot did not return valid JSON.")
        sys.exit(1)


def run_analysis(provider: str, problem_dir: Path, output_file: Path) -> None:
    if provider == "codex":
        run_codex(problem_dir, output_file)
    else:
        run_copilot(problem_dir, output_file)


def load_analysis(output_file: Path, provider: str) -> dict:
    try:
        data = json.loads(
            output_file.read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        print(f"ERROR: {provider.title()} did not create the output file:")
        print(f"  {output_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: {provider.title()} output is not valid JSON.")
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

    try:
        return validate_analysis_response(data)
    except ValueError as error:
        print(f"ERROR: {provider.title()} returned invalid analysis JSON.")
        print(f"  {error}")
        sys.exit(1)


def _flatten_skill_path_items(value: object) -> list[str]:
    """Normalize skill_path payloads that may be list fragments or a single string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_skill_path_items(item))
        return items
    text = str(value).strip()
    if not text:
        return []
    cleaned = text.replace("\\", "/")
    parts = [part.strip() for part in cleaned.split("/") if part.strip()]
    return parts


def validate_skill_path_parts(parts: list[str]) -> None:
    for part in parts:
        if part in {".", ".."}:
            raise ValueError("Skill paths cannot contain '.' or '..'.")
        if not SKILL_SEGMENT_RE.fullmatch(part):
            raise ValueError(
                f"Invalid skill path segment '{part}'. Use lowercase letters, "
                "digits, underscores, or hyphens."
            )
        if part in IMPLEMENTATION_PATH_TERMS:
            raise ValueError(
                f"Skill path segment '{part}' describes implementation details, "
                "not a reusable reasoning pattern."
            )


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


def get_skill_path(analysis: dict) -> Path:
    payload = analysis.get("skill_path", [])
    raw_parts = _flatten_skill_path_items(payload)
    if not raw_parts:
        print("ERROR: Empty skill path.")
        sys.exit(1)

    try:
        validate_skill_path_parts(raw_parts)
    except ValueError as error:
        print(f"ERROR: Invalid skill path: {error}")
        sys.exit(1)

    skill_path = "/".join(raw_parts)
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


def ask_existing_skill_match(
    analysis: dict,
    provider: str,
) -> tuple[str, Path | None, str]:
    """Ask the selected AI provider whether a retrieved skill should be reused."""
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
            if provider == "codex":
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
            else:
                match_prompt = (
                    f"{prompt}\n\nREQUIRED JSON SCHEMA:\n"
                    f"{MATCH_SCHEMA_FILE.read_text(encoding='utf-8')}\n"
                    "Do not use tools. Return only one JSON object."
                )
                completed = subprocess.run(
                    [
                        find_cli("copilot"),
                        "--silent",
                        "--no-ask-user",
                        "--output-format=text",
                    ],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    input=match_prompt,
                )
                result = extract_json_response(completed.stdout)
            validate_match_response(result)
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            ValueError,
            OSError,
        ) as error:
            if isinstance(error, ValueError):
                print(f"WARNING: Existing-skill matcher returned invalid JSON: {error}")
            print("WARNING: Existing-skill matching failed; no skill will be created.")
            return "MATCH_FAILED", None, "Matcher failed."

        decision = result.get("decision")
        selected = get_existing_skill_path(str(result.get("path") or ""))
        candidate_paths = {candidate.relative_path for candidate in candidates}
        selected_relative = selected.relative_to(SKILLS_DIR).with_suffix("").as_posix() if selected else None
        if decision in {"REUSE", "EXTEND"} and selected_relative in candidate_paths:
            return decision, selected, str(result.get("reason", ""))
        if decision == "CREATE_NEW":
            return decision, None, str(result.get("reason", ""))
        return "MATCH_FAILED", None, "Matcher returned an invalid candidate path."
    finally:
        output_file.unlink(missing_ok=True)


def skill_content(analysis: dict, skill_file: Path) -> str:
    """Build the Markdown content for a newly proposed skill."""
    questions = _string_list(analysis.get("questions", []))
    signals = _string_list(analysis.get("signals", []))
    observations = _string_list(analysis.get("key_observations", []))
    patterns = _string_list(analysis.get("reasoning_patterns", []))
    related = _string_list(analysis.get("probably_related", []))

    return (
        f"# {skill_file.stem.replace('_', ' ').title()}\n\n"

        "## Core Idea\n\n"
        + analysis.get("core_idea", "").strip()
        + "\n\n"

        "## Signals\n\n"
        + "\n".join(f"- {signal}" for signal in signals)
        + "\n\n"

        "## Questions\n\n"
        + "\n".join(f"- {question}" for question in questions)
        + "\n\n"

        "## Key Observations\n\n"
        + "\n".join(f"- {observation}" for observation in observations)
        + "\n\n"

        "## Reasoning Patterns\n\n"
        + "\n".join(f"- {pattern}" for pattern in patterns)
        + "\n\n"

        "## Probably Related\n\n"
        + "\n".join(f"- {related_item}" for related_item in related)
        + "\n"
    )


def create_skill(analysis: dict) -> Path:
    skill_file = get_skill_path(analysis)

    skill_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    skill_file.write_text(
        skill_content(analysis, skill_file),
        encoding="utf-8",
    )

    return skill_file


def strip_markdown_fence(content: str) -> str:
    content = content.strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", content, re.DOTALL)
    return (fenced.group(1) if fenced else content).rstrip() + "\n"


def draft_skill_extension(analysis: dict, skill_file: Path, provider: str) -> str | None:
    """Ask the selected provider for a full revised skill, without writing it."""
    existing_content = skill_file.read_text(encoding="utf-8")
    prompt = f"""Improve an existing competitive-programming skill with useful,
non-duplicative insights from a newly analyzed problem.

EXISTING SKILL PATH: {skill_file.relative_to(SKILLS_DIR).as_posix()}
EXISTING SKILL:
{existing_content}

NEW ANALYSIS:
{json.dumps(analysis, indent=2, ensure_ascii=False)}

Return the complete revised Markdown skill. Preserve helpful existing material,
add only reusable insights missing from it, and return Markdown only. Do not use tools.
"""

    try:
        if provider == "codex":
            with tempfile.NamedTemporaryFile(
                prefix="skill-extension-",
                suffix=".md",
                dir=ROOT,
                delete=False,
            ) as handle:
                output_file = Path(handle.name)
            try:
                subprocess.run(
                    [
                        "codex",
                        "exec",
                        "--sandbox",
                        "read-only",
                        "-o",
                        str(output_file),
                        prompt,
                    ],
                    cwd=ROOT,
                    check=True,
                )
                return strip_markdown_fence(output_file.read_text(encoding="utf-8"))
            finally:
                output_file.unlink(missing_ok=True)

        completed = subprocess.run(
            [
                find_cli("copilot"),
                "--silent",
                "--no-ask-user",
                "--output-format=text",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            input=prompt,
        )
        return strip_markdown_fence(completed.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        print("WARNING: Could not draft an extension preview.")
        return None


def print_diff(before: str, after: str, from_file: str, to_file: str) -> None:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=from_file,
        tofile=to_file,
    )
    rendered = "".join(diff)
    print(rendered if rendered else "(No content changes proposed.)")


def process_skill(
    analysis: dict,
    provider: str,
    review: bool = False,
    apply_extension: bool = False,
) -> None:
    skill_file = get_skill_path(analysis)

    print()
    print("Skill detection")
    print("----------------")

    if skill_file.exists():
        print("REUSE EXISTING SKILL")
        print(skill_file)
        return

    decision, existing, reason = ask_existing_skill_match(analysis, provider)
    if decision == "MATCH_FAILED":
        print("MATCHING FAILED")
        print("No skill was created. Rerun after reviewing the matcher error.")
        if reason:
            print(f"Reason: {reason}")
        return

    if existing is not None:
        print(f"{decision} EXISTING SKILL")
        print(existing)
        if reason:
            print(f"Reason: {reason}")
        if (review or apply_extension) and decision == "EXTEND":
            proposal = draft_skill_extension(analysis, existing, provider)
            if proposal is not None:
                print()
                print("Extension proposal")
                print("------------------")
                print_diff(
                    existing.read_text(encoding="utf-8"),
                    proposal,
                    existing.relative_to(ROOT).as_posix(),
                    existing.relative_to(ROOT).as_posix(),
                )
                if apply_extension:
                    answer = input("\nApply this extension? [y/N]: ").strip().lower()
                    if answer in {"y", "yes"}:
                        existing.write_text(proposal, encoding="utf-8")
                        print(f"Updated skill: {existing}")
                    else:
                        print("Extension not applied.")
                else:
                    print("Extension preview (not written)")
        return

    print("CREATE NEW SKILL")
    print(skill_file)

    if review:
        print()
        print("New-skill preview (not written)")
        print("------------------------------")
        print_diff(
            "",
            skill_content(analysis, skill_file),
            "/dev/null",
            skill_file.relative_to(ROOT).as_posix(),
        )
        return

    created = create_skill(analysis)

    print()
    print("Created skill:")
    print(created)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a problem into a reusable competitive-programming skill."
    )
    parser.add_argument("problem_directory")
    parser.add_argument(
        "--provider",
        choices=("codex", "copilot"),
        default="codex",
        help="AI CLI to use (default: codex).",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Preview the proposed skill change without writing under skills/.",
    )
    parser.add_argument(
        "--apply-extension",
        action="store_true",
        help="Show and explicitly confirm an EXTEND proposal before writing it.",
    )
    args = parser.parse_args()

    problem_dir = Path(args.problem_directory).resolve()

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

    run_analysis(
        args.provider,
        problem_dir,
        output_file,
    )

    print("Reading analysis...")

    analysis = load_analysis(output_file, args.provider)

    print()
    print("Analysis saved to:")
    print(f"  {output_file}")

    process_skill(
        analysis,
        args.provider,
        args.review,
        args.apply_extension,
    )


if __name__ == "__main__":
    main()
