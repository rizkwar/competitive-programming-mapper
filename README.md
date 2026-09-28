# Competitive Programming Practice Field

This repository is a personal place to solve competitive programming problems
and turn completed solutions into reusable thinking skills. The normal flow is:

```text
Problem/Practice/<problem>/problem.md
             ↓ solve it in Main-Field/
Problem/Analyze/<problem>/problem.md + editorial.md
             ↓ python analyze.py
Problem/Completed/<problem>/analysis.json   +   skills/<topic>.md
```

The analyzer reads the problem and your editorial, extracts general reasoning
patterns with an AI CLI, searches the local skill library, and decides whether
to reuse an existing skill, extend one, or create a new note. It does not use
your source code as the editorial.

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
4. From the repository root, run:

   ```powershell
   python analyze.py
   ```

The command processes **every problem folder directly inside**
`Problem/Analyze/`. It creates `analysis.json`, handles the skill decision, and
moves each successfully processed folder to `Problem/Completed/`. Failed
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
