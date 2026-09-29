import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from Helper.skill_search import (
    analysis_query,
    candidate_context,
    load_skill_documents,
    rank_candidates,
)


ROOT = Path(__file__).resolve().parent
HELPER_DIR = ROOT / "Helper"
PROBLEMS_DIR = ROOT / "Problem"
PRACTICE_DIR = PROBLEMS_DIR / "Practice"
ANALYZE_DIR = PROBLEMS_DIR / "Analyze"
COMPLETED_DIR = PROBLEMS_DIR / "Completed"
SKILL_SEGMENT_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]*$")
TAXONOMY_WORD_RE = re.compile(r"[^a-z0-9_-]+")
KNOWN_BROAD_CATEGORIES = {
    "binary-search",
    "counting",
    "construction",
    "data-structures",
    "dp",
    "dynamic-programming",
    "feasibility",
    "geometry",
    "graph",
    "graphs",
    "greedy",
    "math",
    "number-theory",
    "optimization",
    "search",
    "sorting",
    "strings",
    "trees",
}
IMPLEMENTATION_PATH_TERMS = {
    "complexity",
    "variable",
}
SKILL_SPECIFICITY_WARNINGS = (
    ("in this problem", "problem-specific framing"),
    ("given input", "problem-specific input description"),
    ("output", "problem-specific output description"),
)

PROMPT_FILE = HELPER_DIR / "prompts" / "analysis.md"
SCHEMA_FILE = HELPER_DIR / "config" / "analysis_schema.json"
MATCH_SCHEMA_FILE = HELPER_DIR / "config" / "match_schema.json"
VERIFICATION_PROMPT_FILE = HELPER_DIR / "prompts" / "verification.md"
VERIFICATION_SCHEMA_FILE = HELPER_DIR / "config" / "verification_schema.json"
SKILLS_DIR = ROOT / "skills"


def find_cli(name: str) -> str:
    """Prefer npm's Windows shim when another launcher shadows it on PATH."""
    if os.name == "nt" and name == "copilot":
        npm_cli = Path(os.environ.get("APPDATA", "")) / "npm" / "copilot.cmd"
        if npm_cli.is_file():
            return str(npm_cli)

    return shutil.which(name) or name


def editorial_file(problem_dir: Path) -> Path:
    """Accept editorial.md for new work and solution.md for older problems."""
    editorial = problem_dir / "editorial.md"
    return editorial if editorial.is_file() else problem_dir / "solution.md"


def validate_files(problem_dir: Path) -> None:
    required_files = [
        PROMPT_FILE,
        SCHEMA_FILE,
        MATCH_SCHEMA_FILE,
        VERIFICATION_PROMPT_FILE,
        VERIFICATION_SCHEMA_FILE,
        problem_dir / "problem.md",
        editorial_file(problem_dir),
    ]

    for file in required_files:
        if not file.exists():
            print("ERROR: Missing file:")
            print(f"  {file}")
            sys.exit(1)


def resolve_problem_directory(value: str) -> Path:
    """Resolve a problem name only inside Problem/Analyze."""
    if not value or Path(value).name != value or value in {".", ".."}:
        raise ValueError("Use a folder name from Problem/Analyze.")
    requested = (ANALYZE_DIR / value).resolve()
    if requested.parent != ANALYZE_DIR.resolve():
        raise ValueError("Only folders in Problem/Analyze can be analyzed.")
    return requested


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
    if not isinstance(value, dict) or set(value) != {
        "core_idea", "key_observations", "solution_flow", "skills"
    }:
        raise ValueError(
            "Analysis needs core_idea, key_observations, solution_flow, and skills only."
        )
    if not isinstance(value["core_idea"], str) or not value["core_idea"].strip():
        raise ValueError("Analysis core_idea must be a nonempty string.")
    if not isinstance(value["key_observations"], list) or not all(
        isinstance(item, str) for item in value["key_observations"]
    ):
        raise ValueError("Analysis key_observations must be a list of strings.")
    skills = value["skills"]
    if not isinstance(skills, list) or not skills:
        raise ValueError("Analysis needs at least one reusable skill.")
    skill_fields = (
        "skill_path", "signals", "questions", "how_to_apply",
        "why_it_works", "when_it_fails", "reasoning_patterns", "probably_related",
    )
    for index, skill in enumerate(skills, 1):
        if not isinstance(skill, dict):
            raise ValueError(f"Skill {index} must be an object.")
        try:
            validate_schema_response(
                skill, required=skill_fields, list_fields=skill_fields
            )
        except ValueError as error:
            raise ValueError(f"Skill {index}: {error}") from error
        for field in skill_fields[:-1]:
            if not any(item.strip() for item in skill[field]):
                raise ValueError(f"Skill {index} field '{field}' needs a useful item.")
    flow = value["solution_flow"]
    if not isinstance(flow, list) or not flow:
        raise ValueError("Analysis needs a nonempty solution_flow.")
    used_indices: set[int] = set()
    for step in flow:
        if not isinstance(step, dict) or set(step) != {"skill_index", "application"}:
            raise ValueError("Each solution_flow step needs skill_index and application.")
        index = step["skill_index"]
        if type(index) is not int or not 1 <= index <= len(skills):
            raise ValueError("solution_flow refers to a nonexistent skill_index.")
        if not isinstance(step["application"], str) or not step["application"].strip():
            raise ValueError("Each solution_flow application must explain the skill's role.")
        used_indices.add(index)
    if used_indices != set(range(1, len(skills) + 1)):
        raise ValueError("Every extracted skill must appear in solution_flow.")
    return value


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


def validate_verification_response(value: dict) -> dict:
    if set(value) != {"status", "checks", "issues"}:
        raise ValueError("Verification needs status, checks, and issues only.")
    if not isinstance(value["status"], str) or value["status"] not in {"PASS", "FAIL", "UNCERTAIN"}:
        raise ValueError("Verification status must be PASS, FAIL, or UNCERTAIN.")
    if not isinstance(value["checks"], list) or not value["checks"] or not all(
        isinstance(check, str) and check.strip() for check in value["checks"]
    ):
        raise ValueError("Verification needs at least one described check.")
    if not isinstance(value["issues"], list):
        raise ValueError("Verification issues must be a list.")
    for issue in value["issues"]:
        if not isinstance(issue, dict) or set(issue) != {"claim", "reason", "counterexample"}:
            raise ValueError("Each verification issue needs claim, reason, and counterexample.")
        if not all(isinstance(issue[field], str) for field in issue):
            raise ValueError("Verification issue fields must be strings.")
        if not issue["claim"].strip() or not issue["reason"].strip():
            raise ValueError("Verification issues need a claim and reason.")
    if value["status"] == "PASS" and value["issues"]:
        raise ValueError("PASS cannot have unresolved issues.")
    if value["status"] != "PASS" and not value["issues"]:
        raise ValueError("FAIL or UNCERTAIN needs an issue.")
    return value


def run_codex(problem_dir: Path, output_file: Path) -> None:
    problem_file = problem_dir / "problem.md"
    solution_file = editorial_file(problem_dir)

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
            "Read Helper/prompts/analysis.md first. "
            f"Then analyze {problem_file.as_posix()} and "
            f"{solution_file.as_posix()} according to the instructions "
            "in Helper/prompts/analysis.md. Return the required JSON."
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
{editorial_file(problem_dir).read_text(encoding="utf-8")}

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
        data = validate_analysis_response(data)
        paths: set[str] = set()
        for index, skill in enumerate(data["skills"], 1):
            raw_parts = _flatten_skill_path_items(skill["skill_path"])
            if any(part in {".", ".."} for part in raw_parts):
                raise ValueError(f"Skill {index} path cannot contain '.' or '..'.")
            parts = normalize_skill_path_parts(raw_parts)
            if not parts:
                raise ValueError(f"Skill {index} needs a valid skill_path.")
            validate_skill_path_parts(parts)
            path = "/".join(parts)
            if path in paths:
                raise ValueError(f"Duplicate proposed skill path: {path}.")
            paths.add(path)
            skill["skill_path"] = parts
        output_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return data
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


def normalize_skill_path_parts(parts: list[str]) -> list[str]:
    """Convert AI path labels into one lowercase, taxonomy-safe segment each."""
    normalized: list[str] = []
    for part in parts:
        words = [word for word in TAXONOMY_WORD_RE.split(part.lower()) if word]
        if not words:
            continue
        candidate = "-".join(words)
        normalized.append(candidate)

    if normalized and normalized[0].split("-")[0] in KNOWN_BROAD_CATEGORIES:
        normalized[0] = normalized[0].split("-")[0]

    return normalized


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
    if any(part in {".", ".."} for part in raw_parts):
        print("ERROR: Invalid skill path: Skill paths cannot contain '.' or '..'.")
        sys.exit(1)
    raw_parts = normalize_skill_path_parts(raw_parts)
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
    documents = load_skill_documents(SKILLS_DIR)
    candidates = rank_candidates(analysis, documents)
    proposed_path = get_skill_path(analysis)
    exact_path_document = next(
        (document for document in documents if document.path.resolve() == proposed_path),
        None,
    )
    if exact_path_document is not None and exact_path_document not in candidates:
        candidates = [exact_path_document, *candidates[:7]]
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
                        "-",
                    ],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    input=prompt,
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
    """Build a reusable thinking guide, not a problem-specific solution note."""
    sections = (
        ("Signals", "signals", False),
        ("Questions", "questions", False),
        ("How to Apply", "how_to_apply", True),
        ("Why It Works", "why_it_works", False),
        ("When It Fails", "when_it_fails", False),
        ("Reasoning Patterns", "reasoning_patterns", False),
        ("Probably Related", "probably_related", False),
    )
    parts = [f"# {skill_file.stem.replace('_', ' ').title()}"]
    for heading, field, ordered in sections:
        items = _string_list(analysis.get(field, []))
        if not items:
            continue
        lines = [f"{index}. {item}" if ordered else f"- {item}"
                 for index, item in enumerate(items, 1)]
        parts.append(f"## {heading}\n\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n"


def skill_quality_warnings(content: str) -> list[str]:
    """Return review warnings for details that may be too problem-specific."""
    lowered = content.lower()
    return [
        f"{term}: {description}"
        for term, description in SKILL_SPECIFICITY_WARNINGS
        if re.search(rf"\b{re.escape(term)}\b", lowered)
    ]


def print_skill_quality_warnings(content: str) -> None:
    warnings = skill_quality_warnings(content)
    if not warnings:
        return
    print()
    print("WARNING: Skill may contain problem-specific details")
    print("----------------------------------------------------")
    for warning in warnings:
        print(f"- {warning}")
    print("Review the proposal and generalize these details if needed.")


def strip_markdown_fence(content: str) -> str:
    content = content.strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", content, re.DOTALL)
    return (fenced.group(1) if fenced else content).rstrip() + "\n"


def missing_teaching_sections(content: str) -> list[str]:
    """Find required teaching sections absent or empty in a proposed skill."""
    headings = list(re.finditer(r"^## ([^\r\n]+?)[ \t]*$", content, flags=re.MULTILINE))
    bodies = {
        match.group(1).strip(): content[
            match.end():headings[index + 1].start() if index + 1 < len(headings) else len(content)
        ].strip()
        for index, match in enumerate(headings)
    }
    return [
        heading for heading in ("Signals", "How to Apply", "Why It Works", "When It Fails")
        if not bodies.get(heading)
    ]


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
add only reusable insights missing from it, and return Markdown only. Organize
the result with nonempty sections named exactly ## Signals, ## How to Apply,
## Why It Works, and ## When It Fails. Keep useful questions, reasoning
patterns, and related skills. Explain the technique's conditions, application,
proof, and boundaries; use concise formulas when they help, with defined terms.
Do not use tools.
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
                        "-",
                    ],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    input=prompt,
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


def verify_skill_claims(
    analysis: dict,
    problem_dir: Path,
    provider: str,
    decision: str,
    proposed_content: str = "",
    previous_content: str = "",
    skill_index: int | None = None,
) -> bool:
    """Review claims in a separate AI call and keep an inspectable report."""
    prompt = f"""{VERIFICATION_PROMPT_FILE.read_text(encoding='utf-8')}

MODE: {decision}

PROBLEM:
{(problem_dir / 'problem.md').read_text(encoding='utf-8')}

EDITORIAL:
{editorial_file(problem_dir).read_text(encoding='utf-8')}

ANALYSIS:
{json.dumps(analysis, indent=2, ensure_ascii=False)}

PREVIOUS SKILL (only relevant for EXTEND):
{previous_content}

PROPOSED SKILL (empty for REUSE):
{proposed_content}

Do not use tools. Return only one JSON object.
"""
    report_name = f"verification-{skill_index}.json" if skill_index else "verification.json"
    report_file = problem_dir / report_name
    with tempfile.NamedTemporaryFile(
        prefix="skill-verification-", suffix=".json", dir=ROOT, delete=False
    ) as handle:
        output_file = Path(handle.name)

    try:
        if provider == "codex":
            subprocess.run(
                [
                    "codex", "exec", "--sandbox", "read-only", "--output-schema",
                    str(VERIFICATION_SCHEMA_FILE), "-o", str(output_file), "-",
                ],
                cwd=ROOT, check=True, capture_output=True, text=True,
                encoding="utf-8", timeout=240, input=prompt,
            )
            result = extract_json_response(output_file.read_text(encoding="utf-8"))
        else:
            completed = subprocess.run(
                [find_cli("copilot"), "--silent", "--no-ask-user", "--output-format=text"],
                cwd=ROOT, check=True, capture_output=True, text=True,
                encoding="utf-8", timeout=240,
                input=f"{prompt}\nREQUIRED JSON SCHEMA:\n{VERIFICATION_SCHEMA_FILE.read_text(encoding='utf-8')}",
            )
            result = extract_json_response(completed.stdout)
        report = validate_verification_response(result)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, ValueError) as error:
        report = {
            "status": "ERROR",
            "checks": [],
            "issues": [{
                "claim": "Verification run",
                "reason": str(error),
                "counterexample": "",
            }],
        }
    finally:
        output_file.unlink(missing_ok=True)

    report_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Claim review: {report['status']} ({report_file})")
    for issue in report["issues"]:
        print(f"- {issue['claim']}: {issue['reason']}")
        if issue["counterexample"]:
            print(f"  Counterexample: {issue['counterexample']}")
    return report["status"] == "PASS"


@dataclass(frozen=True)
class SkillPlan:
    index: int
    decision: str
    path: Path
    proposal: str | None = None
    before: str | None = None


def prepare_skill(
    skill: dict,
    provider: str,
    problem_dir: Path,
    *,
    index: int = 1,
    verification_input: dict | None = None,
    review: bool = False,
    numbered_report: bool = False,
) -> tuple[str, SkillPlan | None]:
    """Match and verify one skill without modifying the library."""
    skill_file = get_skill_path(skill)
    evidence = verification_input if verification_input is not None else skill
    report_index = index if numbered_report else None

    print(f"\nSkill {index}: {'/'.join(_flatten_skill_path_items(skill['skill_path']))}")
    print("----------------")
    decision, existing, reason = ask_existing_skill_match(skill, provider)
    if decision == "MATCH_FAILED":
        print("MATCHING FAILED")
        print("No skill was created. Rerun after reviewing the matcher error.")
        if reason:
            print(f"Reason: {reason}")
        return decision, None

    if existing is not None:
        print(f"{decision} EXISTING SKILL")
        print(existing)
        if reason:
            print(f"Reason: {reason}")
        if decision == "EXTEND":
            before = existing.read_text(encoding="utf-8")
            proposal = draft_skill_extension(skill, existing, provider)
            if proposal is None:
                return "EXTEND_FAILED", None
            missing_sections = missing_teaching_sections(proposal)
            if missing_sections:
                print("Extension lacks teaching sections: " + ", ".join(missing_sections))
                return "EXTEND_FAILED", None
            print("\nExtension proposal\n------------------")
            print_skill_quality_warnings(proposal)
            label = existing.relative_to(ROOT).as_posix()
            print_diff(before, proposal, label, label)
            if not verify_skill_claims(
                evidence, problem_dir, provider, "EXTEND", proposal, before,
                skill_index=report_index,
            ):
                print("Extension not applied; review its claim report.")
                return "VERIFY_FAILED", None
            return decision, SkillPlan(index, decision, existing, proposal, before)
        if not verify_skill_claims(
            evidence, problem_dir, provider, "REUSE", skill_index=report_index
        ):
            print("Analysis not archived; review its claim report.")
            return "VERIFY_FAILED", None
        return decision, SkillPlan(index, decision, existing)

    print("CREATE NEW SKILL")
    print(skill_file)
    if skill_file.exists():
        print("PATH COLLISION: This path already has a different skill.")
        return "PATH_COLLISION", None
    proposal = skill_content(skill, skill_file)
    print_skill_quality_warnings(proposal)
    if not verify_skill_claims(
        evidence, problem_dir, provider, "CREATE_NEW", proposal,
        skill_index=report_index,
    ):
        print("Skill not created; review its claim report.")
        return "VERIFY_FAILED", None
    if review:
        print("\nNew-skill preview (not written)\n------------------------------")
        print_diff("", proposal, "/dev/null", skill_file.relative_to(ROOT).as_posix())
    return decision, SkillPlan(index, decision, skill_file, proposal)


def apply_skill_plans(plans: list[SkillPlan], apply_extensions: bool) -> None:
    """Write verified proposals together and restore earlier files on failure."""
    writes = [
        plan for plan in plans
        if plan.decision == "CREATE_NEW" or (
            plan.decision == "EXTEND" and apply_extensions
        )
    ]
    originals: list[tuple[Path, bytes | None]] = []
    try:
        for plan in writes:
            if plan.decision == "CREATE_NEW":
                plan.path.parent.mkdir(parents=True, exist_ok=True)
                with plan.path.open("x", encoding="utf-8") as handle:
                    originals.append((plan.path, None))
                    handle.write(plan.proposal or "")
            else:
                current = plan.path.read_bytes()
                normalized = current.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                if normalized != plan.before:
                    raise RuntimeError(f"Skill changed during review: {plan.path}")
                originals.append((plan.path, current))
                plan.path.write_text(plan.proposal or "", encoding="utf-8")
    except BaseException:
        for path, original in reversed(originals):
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            except OSError as error:
                print(f"WARNING: Could not restore {path}: {error}")
        raise
    for plan in writes:
        action = "Created" if plan.decision == "CREATE_NEW" else "Updated"
        print(f"{action} skill: {plan.path}")


def process_skill(
    analysis: dict,
    provider: str,
    problem_dir: Path,
    review: bool = False,
    apply_extension: bool = False,
) -> str:
    """Handle one skill directly; the full workflow uses process_skills."""
    status, plan = prepare_skill(
        analysis, provider, problem_dir, review=review
    )
    if plan is None:
        return status
    if review:
        if plan.decision == "EXTEND":
            print("Extension preview (not written)")
        return status
    update = False
    if plan.decision == "EXTEND":
        if apply_extension:
            update = input("\nApply this extension? [y/N]: ").strip().lower() in {"y", "yes"}
        if not update:
            print("Extension preview (not written)")
    apply_skill_plans([plan], update)
    return status


def process_skills(
    analysis: dict,
    provider: str,
    problem_dir: Path,
    *,
    review: bool = False,
    apply_extension: bool = False,
) -> list[dict] | None:
    """Prepare every skill before any write, then record the resolved paths."""
    plans: list[SkillPlan] = []
    for index, skill in enumerate(analysis["skills"], 1):
        evidence = {
            "core_idea": analysis["core_idea"],
            "key_observations": analysis["key_observations"],
            "solution_flow": [
                step for step in analysis["solution_flow"]
                if step["skill_index"] == index
            ],
            "skill": skill,
        }
        _, plan = prepare_skill(
            skill, provider, problem_dir, index=index,
            verification_input=evidence, review=review, numbered_report=True,
        )
        if plan is None:
            print("No skills were written for this problem.")
            return None
        plans.append(plan)

    write_paths = [plan.path.resolve() for plan in plans if plan.decision != "REUSE"]
    if len(write_paths) != len(set(write_paths)):
        print("Multiple extracted skills resolved to one writable note; revise the analysis.")
        return None

    update = False
    if review:
        if any(plan.decision == "EXTEND" for plan in plans):
            print("Extension preview (not written)")
    else:
        extensions = sum(plan.decision == "EXTEND" for plan in plans)
        if extensions and apply_extension:
            update = input(
                f"\nApply {extensions} verified extension(s)? [y/N]: "
            ).strip().lower() in {"y", "yes"}
        apply_skill_plans(plans, update)
    return [
        {
            "skill_index": plan.index,
            "decision": plan.decision,
            "path": plan.path.relative_to(SKILLS_DIR).as_posix(),
            "written": not review and (
                plan.decision == "CREATE_NEW" or (
                    plan.decision == "EXTEND" and update
                )
            ),
            "verification": f"verification-{plan.index}.json",
        }
        for plan in plans
    ]


def analyze_one(
    problem_dir: Path,
    provider: str,
    *,
    review: bool = False,
    apply_extension: bool = False,
) -> bool:
    """Analyze one staged folder, then archive it only after successful handling."""
    problem_dir = problem_dir.resolve()
    if problem_dir.parent != ANALYZE_DIR.resolve() or not problem_dir.is_dir():
        raise ValueError("Only problem folders in Problem/Analyze can be analyzed.")
    destination = COMPLETED_DIR / problem_dir.name
    if destination.exists():
        raise FileExistsError(f"Completed problem already exists: {destination}")
    validate_files(problem_dir)

    print(f"\nAnalyzing: {problem_dir.name}")
    output_file = problem_dir / "analysis.json"
    run_analysis(provider, problem_dir, output_file)
    analysis = load_analysis(output_file, provider)
    resolved = process_skills(
        analysis, provider, problem_dir,
        review=review, apply_extension=apply_extension,
    )
    if resolved is None:
        print(f"Kept in Problem/Analyze: {problem_dir.name}")
        return False
    if review:
        print(f"Review only; kept in Problem/Analyze: {problem_dir.name}")
        return True

    analysis["resolved_skills"] = resolved
    output_file.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Completed problem already exists: {destination}")
    problem_dir.rename(destination)
    print(f"Completed: {destination}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Problem/Analyze and move successful folders to Problem/Completed."
    )
    parser.add_argument("--name", help="Analyze one named folder in Problem/Analyze.")
    parser.add_argument("--provider", choices=("codex", "copilot"), default="codex")
    parser.add_argument("--review", action="store_true", help="Preview skills and keep folders in Analyze.")
    parser.add_argument("--apply-extension", action="store_true", help="Ask before updating an existing skill.")
    args = parser.parse_args()

    try:
        if args.name:
            problems = [resolve_problem_directory(args.name)]
        else:
            problems = sorted(path for path in ANALYZE_DIR.iterdir() if path.is_dir()) if ANALYZE_DIR.exists() else []
    except ValueError as error:
        parser.error(str(error))
    if not problems:
        print("No problems in Problem/Analyze.")
        return

    succeeded = 0
    failed = 0
    for problem_dir in problems:
        try:
            if analyze_one(problem_dir, args.provider, review=args.review, apply_extension=args.apply_extension):
                succeeded += 1
            else:
                failed += 1
        except (Exception, SystemExit) as error:
            failed += 1
            print(f"ERROR: {problem_dir.name}: {error}", file=sys.stderr)
            print("Folder remains in Problem/Analyze for retry.", file=sys.stderr)
    print(f"Processed: {succeeded} succeeded, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
