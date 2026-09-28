"""Local practice sessions with progressive hints and post-solve reflection."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from main import (
    ROOT,
    load_analysis,
    process_skill,
    resolve_problem_directory,
    run_analysis,
)


SESSIONS_DIR = ROOT / ".practice" / "sessions"
SESSION_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_plan(problem_dir: Path) -> dict:
    plan_file = problem_dir / "practice.json"
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {plan_file}: {error}") from error
    if not isinstance(plan, dict):
        raise ValueError("practice.json must be an object.")
    hints = plan.get("hints")
    if not isinstance(hints, list) or not hints or not all(
        isinstance(hint, str) and hint.strip() for hint in hints
    ):
        raise ValueError("practice.json needs a nonempty list of hints.")
    skills = plan.get("skills", [])
    if not isinstance(skills, list) or not all(
        isinstance(skill, str) and skill.strip() for skill in skills
    ):
        raise ValueError("practice.json skills must be a list of paths.")
    return plan


def load_session(session_id: str) -> dict:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("Invalid session ID.")
    path = SESSIONS_DIR / f"{session_id}.json"
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read session {session_id}: {error}") from error
    if not isinstance(session, dict) or session.get("id") != session_id:
        raise ValueError("Invalid session data.")
    return session


def save_session(session: dict) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session['id']}.json"
    path.write_text(json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def start(problem_name: str) -> dict:
    problem_dir = resolve_problem_directory(problem_name)
    statement_file = problem_dir / "problem.md"
    if not statement_file.is_file():
        raise ValueError(f"Missing problem statement: {statement_file}")
    plan = load_plan(problem_dir)
    statement = statement_file.read_text(encoding="utf-8")
    session = {
        "id": secrets.token_hex(6),
        "problem_dir": str(problem_dir),
        "started_at": now_utc(),
        "completed_at": None,
        "outcome": None,
        "reflection": None,
        "hints_used": 0,
    }
    save_session(session)
    print(statement)
    print(f"\nSession: {session['id']}")
    print(f"Hints available: {len(plan['hints'])}")
    print(f"Next: python practice.py hint {session['id']}")
    return session


def hint(session_id: str) -> str | None:
    session = load_session(session_id)
    if session["completed_at"] is not None:
        raise ValueError("This session is complete.")
    plan = load_plan(Path(session["problem_dir"]))
    index = session["hints_used"]
    if index >= len(plan["hints"]):
        print("No more hints are available.")
        return None
    value = plan["hints"][index]
    session["hints_used"] = index + 1
    save_session(session)
    print(f"Hint {index + 1}/{len(plan['hints'])}: {value}")
    return value


def finish(session_id: str, outcome: str, reflection: str) -> dict:
    session = load_session(session_id)
    if session["completed_at"] is not None:
        raise ValueError("This session is already complete.")
    reflection = reflection.strip()
    if not reflection:
        raise ValueError("Write a reflection before finishing the session.")
    session["outcome"] = outcome
    session["reflection"] = reflection
    session["completed_at"] = now_utc()
    save_session(session)
    plan = load_plan(Path(session["problem_dir"]))
    print(f"Recorded {outcome} with {session['hints_used']} hint(s) used.")
    if plan.get("skills"):
        print("Related skills:")
        for skill in plan["skills"]:
            print(f"  {skill}")
    if (Path(session["problem_dir"]) / "solution.md").is_file():
        print(f"Propose a skill: python practice.py propose {session_id}")
    return session


def propose(session_id: str, provider: str) -> None:
    session = load_session(session_id)
    if session["completed_at"] is None:
        raise ValueError("Finish the practice session before requesting AI analysis.")
    problem_dir = Path(session["problem_dir"])
    if not (problem_dir / "solution.md").is_file():
        raise ValueError("Add solution.md before requesting AI analysis.")
    output_file = problem_dir / "analysis.json"
    run_analysis(provider, problem_dir, output_file)
    analysis = load_analysis(output_file, provider)
    process_skill(analysis, provider, review=True)
    print(f"To apply an approved new skill, run: python main.py \"{problem_dir}\"")


def stats() -> dict:
    sessions = []
    for path in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(session, dict):
            sessions.append(session)
    complete = [item for item in sessions if item.get("completed_at")]
    solved = sum(item.get("outcome") == "solved" for item in complete)
    result = {
        "started": len(sessions),
        "completed": len(complete),
        "solved": solved,
        "hints_used": sum(item.get("hints_used", 0) for item in complete),
    }
    print(
        f"Started: {result['started']} | Completed: {result['completed']} | "
        f"Solved: {result['solved']} | Hints used: {result['hints_used']}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Practice CP problems with progressive hints.")
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start", help="Start a problem without opening its solution.")
    start_parser.add_argument("problem")
    hint_parser = commands.add_parser("hint", help="Reveal the next hint.")
    hint_parser.add_argument("session_id")
    finish_parser = commands.add_parser("finish", help="Record your result and reflection.")
    finish_parser.add_argument("session_id")
    finish_parser.add_argument("--outcome", choices=("solved", "stuck"), required=True)
    finish_parser.add_argument("--reflection", required=True)
    propose_parser = commands.add_parser("propose", help="Preview an AI skill proposal after practice.")
    propose_parser.add_argument("session_id")
    propose_parser.add_argument("--provider", choices=("codex", "copilot"), default="codex")
    commands.add_parser("stats", help="Show local practice totals.")
    args = parser.parse_args()
    try:
        if args.command == "start":
            start(args.problem)
        elif args.command == "hint":
            hint(args.session_id)
        elif args.command == "finish":
            finish(args.session_id, args.outcome, args.reflection)
        elif args.command == "propose":
            propose(args.session_id, args.provider)
        else:
            stats()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
