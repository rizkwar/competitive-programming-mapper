import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PROMPT_FILE = ROOT / "prompt.md"
SCHEMA_FILE = ROOT / "schema.json"


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
        print("Make sure Codex CLI is installed and 'codex' works in your terminal.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Codex exited with code {e.returncode}.")
        sys.exit(e.returncode)


def format_json(output_file: Path) -> None:
    if not output_file.exists():
        print(f"ERROR: Codex did not create {output_file}.")
        sys.exit(1)

    try:
        data = json.loads(output_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("ERROR: Codex output is not valid JSON.")
        print(f"Location: line {e.lineno}, column {e.colno}")
        print(f"Message: {e.msg}")
        sys.exit(1)

    output_file.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def validate_files(problem_dir: Path) -> None:
    required_files = [
        PROMPT_FILE,
        SCHEMA_FILE,
        problem_dir / "problem.md",
        problem_dir / "solution.md",
    ]

    for file in required_files:
        if not file.exists():
            print(f"ERROR: Missing file:")
            print(f"  {file}")
            sys.exit(1)


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
        print(f"ERROR: Directory does not exist:")
        print(f"  {problem_dir}")
        sys.exit(1)

    if not problem_dir.is_dir():
        print(f"ERROR: Not a directory:")
        print(f"  {problem_dir}")
        sys.exit(1)

    validate_files(problem_dir)

    output_file = problem_dir / "analysis.json"

    print("========================================")
    print(" Competitive Programming Skill Analyzer")
    print("========================================")
    print()
    print(f"Problem directory : {problem_dir}")
    print(f"Problem           : {problem_dir / 'problem.md'}")
    print(f"Solution          : {problem_dir / 'solution.md'}")
    print(f"Prompt            : {PROMPT_FILE}")
    print(f"Schema            : {SCHEMA_FILE}")
    print(f"Output            : {output_file}")
    print()

    run_codex(problem_dir, output_file)

    print()
    print("Formatting JSON...")

    format_json(output_file)

    print()
    print("Done.")
    print(f"Analysis saved to:")
    print(f"  {output_file}")


if __name__ == "__main__":
    main()