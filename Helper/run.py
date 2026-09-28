"""Compile a Main-Field C++ file and run a problem's saved samples."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SLOT_RE = re.compile(r"^[A-M]$")
STAGES = ("Practice", "Analyze", "Completed")


def problem_folder(name: str, stage: str) -> Path:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Use a problem folder name, without a path.")
    stage_dir = (ROOT / "Problem" / stage).resolve()
    folder = (stage_dir / name).resolve()
    if folder.parent != stage_dir or not folder.is_dir():
        raise ValueError(f"Problem folder not found in Problem/{stage}: {name}")
    return folder


def display(data: bytes, limit: int = 3000) -> str:
    text = data.decode("utf-8", errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n... (truncated)"


def run_samples(
    slot: str,
    name: str,
    *,
    stage: str = "Practice",
    timeout: float = 2.0,
    compiler: str = "g++",
    no_compare: bool = False,
) -> int:
    slot = slot.upper()
    if not SLOT_RE.fullmatch(slot):
        raise ValueError("Code slot must be a letter from A through M.")
    if stage not in STAGES:
        raise ValueError(f"Stage must be one of: {', '.join(STAGES)}.")
    if timeout <= 0:
        raise ValueError("Timeout must be greater than zero.")

    folder = problem_folder(name, stage)
    source = ROOT / "Main-Field" / f"{slot}.cpp"
    if not source.is_file():
        raise ValueError(f"Source file not found: {source}")
    samples_dir = folder / "samples"
    inputs = sorted(samples_dir.glob("*.in")) if samples_dir.is_dir() else []
    if not inputs:
        raise ValueError(f"No sample inputs found in {samples_dir}. Add 1.in and 1.out.")

    with tempfile.TemporaryDirectory(prefix="cp-run-") as temporary:
        binary = Path(temporary) / ("solution.exe" if os.name == "nt" else "solution")
        command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", str(source), "-o", str(binary)]
        print(f"Compiling Main-Field/{slot}.cpp...")
        try:
            compiled = subprocess.run(command, capture_output=True, timeout=30)
        except FileNotFoundError:
            print(f"Compiler not found: {compiler}", file=sys.stderr)
            return 2
        except subprocess.TimeoutExpired:
            print("Compilation timed out after 30 seconds.", file=sys.stderr)
            return 1
        if compiled.returncode != 0:
            print("Compilation failed:", file=sys.stderr)
            print(display(compiled.stderr), file=sys.stderr)
            return 1
        if compiled.stderr:
            print(display(compiled.stderr), file=sys.stderr)

        passed = 0
        failed = 0
        unverified = 0
        for input_file in inputs:
            expected_file = input_file.with_suffix(".out")
            try:
                result = subprocess.run(
                    [str(binary)],
                    input=input_file.read_bytes(),
                    capture_output=True,
                    timeout=timeout,
                    cwd=temporary,
                )
            except subprocess.TimeoutExpired:
                print(f"TIMEOUT {input_file.name} (>{timeout:g}s)")
                failed += 1
                continue
            if result.returncode != 0:
                print(f"RUNTIME ERROR {input_file.name} (exit {result.returncode})")
                if result.stderr:
                    print(display(result.stderr))
                failed += 1
                continue
            if no_compare or not expected_file.is_file():
                print(f"RUN {input_file.name} (output not checked)")
                print(display(result.stdout))
                unverified += 1
                continue
            expected = expected_file.read_bytes()
            if result.stdout.split() == expected.split():
                print(f"PASS {input_file.name}")
                passed += 1
            else:
                print(f"WRONG ANSWER {input_file.name}")
                print(f"Expected:\n{display(expected)}")
                print(f"Actual:\n{display(result.stdout)}")
                failed += 1
        print(f"Results: {passed} passed, {failed} failed, {unverified} unchecked.")
        return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a C++ slot and run saved problem samples.")
    parser.add_argument("slot", help="Main-Field source letter, A through M.")
    parser.add_argument("problem", help="Folder name under Problem/<stage>.")
    parser.add_argument("--stage", choices=STAGES, default="Practice")
    parser.add_argument("--timeout", type=float, default=2.0, help="Seconds allowed per sample (default: 2).")
    parser.add_argument("--compiler", default="g++", help="C++ compiler command (default: g++).")
    parser.add_argument("--no-compare", action="store_true", help="Show output without checking .out files.")
    args = parser.parse_args()
    try:
        code = run_samples(
            args.slot,
            args.problem,
            stage=args.stage,
            timeout=args.timeout,
            compiler=args.compiler,
            no_compare=args.no_compare,
        )
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
