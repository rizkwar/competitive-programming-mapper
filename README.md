# Competitive Programming Practice Field

This repository is a personal place to solve competitive programming problems
and turn completed solutions into reusable thinking skills. The normal flow is:

```text
Problem/Practice/<problem>/problem.md
             ↓ solve it in Main-Field/
Problem/Analyze/<problem>/problem.md + editorial.md
             ↓ python analyze.py
Problem/Completed/<problem>/analysis.json   +   skills/<technique>.md
```

The analyzer reads the problem and your editorial, extracts general reasoning
patterns with an AI CLI, then matches each distinct technique against the local
skill library. A problem can reuse, extend, or create several skill notes. Its
`analysis.json` records the solution flow and points each step to a numbered
skill; `resolved_skills` records the notes actually matched or created. It does
not use your source code as the editorial.

New skill notes teach the technique through recognition clues, questions,
steps for applying it, an explanation of why it works, and cases where the
argument fails. Concise formulas are allowed when they clarify the reasoning.
Existing notes remain readable; extensions must include these teaching
sections before they can be saved.

## Requirements

- Python 3.10 or newer; no Python packages to install
- An installed and authenticated Codex CLI (default) or GitHub Copilot CLI

## Work on a problem

1. Create `Problem/Practice/<name>/problem.md` and paste the statement there.
2. Write and run your solution in `Main-Field/`. That folder contains the
   existing `A.cpp` through `M.cpp` work files. The analyzer does not modify
   them.
3. When finished, move the problem folder from `Problem/Practice/` to
   `Problem/Analyze/`. Add `editorial.md` containing your explanation or proof.
   An existing `solution.md` is also accepted.
   Optionally include `attempt.md` with what you tried, where you got stuck,
   and which ideas you could not justify.
4. From the repository root, run:

   ```powershell
   python analyze.py
   ```

### Compile and test samples

Save sample input and expected output beside the problem:

```text
Problem/Practice/my-problem/samples/1.in
Problem/Practice/my-problem/samples/1.out
Problem/Practice/my-problem/samples/2.in
Problem/Practice/my-problem/samples/2.out
```

If your code is in `Main-Field/A.cpp`, compile it and run every `.in` sample
with one command from the repository root:

```powershell
python -m Helper.run A my-problem
```

The runner uses `g++`, allows two seconds per sample, and compares output as
whitespace-separated tokens. It reports `PASS`, `WRONG ANSWER`, `RUNTIME ERROR`,
or `TIMEOUT`; a sample pass is only a sample check. Use `--timeout 5` to allow
five seconds. For problems with multiple valid outputs, omit the `.out` file or
use `--no-compare` to see your output without judging it. After moving the
problem, add `--stage Analyze` or `--stage Completed` to test it there.

The command processes **every problem folder directly inside**
`Problem/Analyze/`. It creates `analysis.json`, handles every skill decision,
and moves each successfully processed folder to `Problem/Completed/`. All skill
proposals for a problem are checked before any note is written. Failed
problems remain in `Problem/Analyze/` so you can fix and retry them. An
existing folder of the same name in `Completed` is never overwritten.

To process just one staged problem or choose Copilot:

```powershell
python analyze.py --name my-problem
python analyze.py --provider copilot
```

`python analyze.py --review` previews skill changes and keeps the folders in
`Analyze`. By default, a genuinely new skill is written under `skills/`.
Extensions are shown as previews; use `--apply-extension` to review and confirm
updating an existing skill. Reused skills are left unchanged.

Before creating or updating a skill, the analyzer runs a separate claim review
against the statement and editorial, including small counterexample attempts.
Each result is saved as `verification-<skill-index>.json` beside `analysis.json`.
A failed, uncertain, or unavailable review leaves the problem in `Analyze`
and does not write the proposed skill. Read the reported claim, correct any
mistaken source text or reasoning, and rerun the analyzer. The review helps
catch mistakes but cannot prove a skill correct.

If `attempt.md` has notes, the analyzer also writes `learning_review.md` and
`attempt_review.json` in the problem folder. The review quotes your notes,
connects recorded attempts to numbered skills, and suggests a specific
practice task. It will not claim you missed an idea just because you did not
mention it. A review with an unsupported quote stops processing so you can
inspect the attempt. With no attempt notes, this extra step is skipped.

Only folders under `Problem/Analyze/` can be passed to the analyzer. It cannot
analyze a problem directly from `Practice` or `Completed`.

## Optional guided practice

`practice.json` can be added to a folder in `Problem/Practice/` for progressive
hints. For example:

```json
{
  "skills": ["greedy/invariants"],
  "hints": [
    "What small statistic controls the answer?",
    "What happens in each extreme case?"
  ]
}
```

From the repository root:

```powershell
python -m Helper.practice start my-problem
python -m Helper.practice hint <session-id>
python -m Helper.practice finish <session-id> --outcome solved --reflection "What I learned"
python -m Helper.practice stats
```

Hints are optional. Personal sessions are saved under the ignored `.practice/`
directory. After finishing, move the problem folder to `Analyze` and add the
editorial as described above.

## Project layout

| Path | Purpose |
| --- | --- |
| `Problem/Practice/` | Problems currently being solved |
| `Main-Field/` | Source code workspace |
| `Problem/Analyze/` | Finished problems waiting for AI analysis |
| `Problem/Completed/` | Archived problems and generated analyses |
| `skills/` | Local reusable skill notes |
| `analyze.py` | Batch analysis command |
| `Helper/` | Prompts, schemas, practice utility, evaluation, and tests |

Personal problem folders, skill notes, and session history are ignored by Git.
The three workflow folders are kept in fresh checkouts with `.gitkeep` files.

## Checks and evaluation

Run the tests from the repository root:

```powershell
python -m unittest discover -s Helper/tests -q
```

The provider-backed evaluation command is:

```powershell
python -m Helper.evaluate --provider codex
```

Its case list is in `Helper/evaluation/cases.json`; results go to the ignored
`evaluation_results/` directory. The included case is currently unlabeled, so
its output needs manual review.
