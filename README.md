# Competitive Programming Skill Mapper

Competitive Programming Skill Mapper is a local CLI tool that turns a
competitive-programming problem and a human-written solution into a reusable
problem-solving skill note.

It focuses on the reasoning behind a solution rather than copying tags such as
`greedy`, `strings`, or `segment tree`.

```text
problem.md + solution.md
        |
        v
AI reasoning analysis
        |
        v
existing-skill retrieval
        |
        v
REUSE / EXTEND / CREATE_NEW
        |
        v
review or create a Markdown skill
```

## Requirements

- Windows PowerShell, macOS, or Linux
- Python 3.10 or newer
- One supported AI CLI:
  - Codex CLI, for the default `codex` provider
  - GitHub Copilot CLI, for the optional `copilot` provider
- An authenticated account for the selected AI provider

The Python application uses only the standard library. No `pip install` step
is required.

## Setup

Clone the repository and enter the project directory:

```powershell
git clone https://github.com/rizkwar/competitive-programming-mapper.git
cd competitive-programming-chain-of-thoughts
```

Verify Python:

```powershell
python --version
```

Install and authenticate either Codex CLI or GitHub Copilot CLI according to
that tool's documentation. Verify that the selected command is available:

```powershell
codex --version
copilot --version
```

Only the provider you plan to use needs to be installed.

## Problem organization

Store problems below the `Problems/` directory. Each problem gets its own
folder containing exactly these input files:

```text
Problems/
├── mex-multiset/
│   ├── problem.md
│   ├── solution.md
│   └── analysis.json          # generated after analysis
├── problemA/
│   ├── problem.md
│   └── solution.md
└── problemB/
    ├── problem.md
    └── solution.md
```

`problem.md` should contain the statement. `solution.md` should contain a
human-written explanation, editorial, or proof. It should not be source code.

## Basic usage

Analyze a named problem inside `Problems/`:

```powershell
python main.py mex-multiset
```

The command:

1. Reads `Problems/mex-multiset/problem.md`.
2. Reads `Problems/mex-multiset/solution.md`.
3. Asks the selected AI provider to extract reusable reasoning.
4. Saves the result to `Problems/mex-multiset/analysis.json`.
5. Searches Markdown files below `skills/`.
6. Decides whether to reuse, extend, or create a skill.

You can also pass a direct folder path:

```powershell
python main.py Problems/mex-multiset
```

Direct paths are useful for folders outside the default `Problems/` directory.

## AI providers

Codex is the default:

```powershell
python main.py mex-multiset
```

Use GitHub Copilot instead:

```powershell
python main.py mex-multiset --provider copilot
```

The provider must be either `codex` or `copilot`.

## Safe review mode

Preview a proposed change without writing anything below `skills/`:

```powershell
python main.py mex-multiset --review
```

Review mode prints a unified diff:

- `CREATE_NEW` shows the proposed Markdown file.
- `REUSE` shows the selected existing skill.
- `EXTEND` shows a complete revised version of the existing skill.

Review mode does not modify skill files.

## Applying an extension

`EXTEND` means that an existing skill is the correct home for the new insight,
but the skill should gain additional reusable material.

To apply an extension:

```powershell
python main.py mex-multiset --apply-extension
```

The CLI displays the complete diff and asks for confirmation:

```text
Apply this extension? [y/N]:
```

The file is written only when you answer `y` or `yes`. Any other answer leaves
the existing skill unchanged.

Without `--apply-extension`, extensions remain preview-only.

## Decisions

### `REUSE`

An existing skill already teaches essentially the same reusable technique.
No new skill file is created.

### `EXTEND`

An existing skill teaches the same core technique, but the new problem adds
general insights worth incorporating. The default behavior is preview-only.

### `CREATE_NEW`

No retrieved skill is semantically equivalent. A new Markdown skill is created
under the AI-proposed taxonomy path.

## Generated skill structure

New skills are Markdown files under `skills/`, for example:

```text
skills/
└── feasibility/
    └── frequency-analysis/
        └── critical-resource/
            └── multiplicity-driven-construction.md
```

Generated notes contain:

- Core Idea
- Signals
- Questions
- Key Observations
- Reasoning Patterns
- Probably Related

The taxonomy path is validated to reject traversal, invalid names, and
implementation-oriented terms such as `precompute`, `iterate`, and `loop`.

## Evaluation

Evaluation cases are listed in `evaluation_cases.json`. Run the suite with
Codex:

```powershell
python evaluate.py --provider codex
```

Or with Copilot:

```powershell
python evaluate.py --provider copilot
```

Evaluation never creates or modifies skill files. Results are written under
the ignored `evaluation_results/` directory.

Each case can define an expected decision and selected skill path:

```json
{
  "id": "minimum-valuation-game",
  "problem_dir": "Problems/mex-multiset",
  "expected": {
    "decision": "REUSE",
    "path": "game_theory/invariants/valuation_analysis/minimum_level_parity_classification"
  }
}
```

Use a custom suite or output directory when needed:

```powershell
python evaluate.py --provider codex --suite benchmarks\cases.json
python evaluate.py --provider codex --results-dir temporary-results
```

## Tests

Run the test suite:

```powershell
python -m unittest -v test_skill_search.py
```

Or run all discovered unittest files quietly:

```powershell
python -m unittest -q
```

The tests cover response validation, path safety, retrieval, provider failure
handling, review previews, and confirmed extension behavior.

## Project structure

```text
.
├── Problems/             # problem.md and solution.md inputs
├── skills/               # reusable generated skill notes
├── main.py               # analysis and skill-management CLI
├── skill_search.py       # Markdown indexing and candidate ranking
├── evaluate.py           # benchmark runner
├── prompt.md             # analysis instructions
├── schema.json           # analysis response schema
├── match_schema.json     # reuse/extend/new response schema
└── test_skill_search.py  # unit tests
```

## Troubleshooting

### Missing `problem.md` or `solution.md`

Make sure the selected folder has both files:

```text
Problems/my-problem/problem.md
Problems/my-problem/solution.md
```

### Provider command not found

Install the corresponding CLI and make sure it is available in your shell:

```powershell
codex --version
copilot --version
```

### Matcher failure

The tool will report `MATCH_FAILED` and will not create a skill. This is
intentional: a provider outage or malformed response must not silently create a
duplicate skill. Review the provider error and rerun the command.

### Existing skill was not modified

`EXTEND` is preview-only unless you pass:

```powershell
--apply-extension
```

You must also explicitly answer `y` or `yes` at the confirmation prompt.
