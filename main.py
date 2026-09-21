import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent
SCHEMA = ROOT / "schema.json"
PROMPT = ROOT / "prompt.md"


def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <problem_directory>")
        sys.exit(1)

    problem_dir = Path(sys.argv[1])

    problem = problem_dir / "problem.md"
    solution = problem_dir / "solution.md"
    output = problem_dir / "analysis.json"

    if not problem.exists():
        print(f"Missing: {problem}")
        sys.exit(1)

    if not solution.exists():
        print(f"Missing: {solution}")
        sys.exit(1)

    if not SCHEMA.exists():
        print(f"Missing: {SCHEMA}")
        sys.exit(1)

    if not PROMPT.exists():
        print(f"Missing: {PROMPT}")
        sys.exit(1)

    command = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(SCHEMA),
        "-o",
        str(output),
        (
            "Read prompt.md, then analyze the competitive programming "
            f"problem in {problem.as_posix()} and its solution in "
            f"{solution.as_posix()}. Follow the instructions in prompt.md "
            "and return the required JSON."
        ),
    ]

    try:
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
        )
    except FileNotFoundError:
        print("Could not find 'codex' in PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Codex failed with exit code {e.returncode}.")
        sys.exit(e.returncode)

    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Codex output is not valid JSON: {output}")
        sys.exit(1)

    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {output}")


if __name__ == "__main__":
    main()