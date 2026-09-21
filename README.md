# Competitive Programming Skill Mapper

Analyze a problem with Codex (default) or GitHub Copilot:

```powershell
python main.py test
python main.py test --provider copilot
```

Preview a proposed new skill or extension without writing under `skills/`:

```powershell
python main.py test --review
python main.py test --provider copilot --review
```

Review mode prints a unified Markdown diff. Rerun the same command without
`--review` to create a new skill; existing skills are never edited automatically.

Evaluate reuse decisions without creating or changing any skill files:

```powershell
python evaluate.py --provider codex
python evaluate.py --provider copilot
```

Add cases to `evaluation_cases.json`. Each case refers to a directory with
`problem.md` and `solution.md`, and may define an expected `decision` and
existing skill `path`. Evaluation output is stored under `evaluation_results/`.
