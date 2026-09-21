# Competitive Programming Skill Mapper

Analyze a problem with Codex (default) or GitHub Copilot:

```powershell
python main.py test
python main.py test --provider copilot
```

Evaluate reuse decisions without creating or changing any skill files:

```powershell
python evaluate.py --provider codex
python evaluate.py --provider copilot
```

Add cases to `evaluation_cases.json`. Each case refers to a directory with
`problem.md` and `solution.md`, and may define an expected `decision` and
existing skill `path`. Evaluation output is stored under `evaluation_results/`.
