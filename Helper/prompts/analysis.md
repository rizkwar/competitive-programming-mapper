# Task

Analyze a competitive programming problem and its human-written editorial.
Identify the reusable techniques behind the solution and explain how they
combine. Do not merely summarize the implementation.

## Problem analysis

`core_idea`: Explain the complete solution idea in 1-3 sentences. This is
specific to the problem and stays in its `analysis.json`.

`key_observations`: Record the problem-specific observations and proof facts
that lead to the solution. Keep enough detail to understand the editorial.

`solution_flow`: Describe the order in which the extracted skills solve this
problem. Each step has a 1-based `skill_index` into `skills` and a concrete
`application` explaining that skill's role here. A skill may appear more than
once if used at different stages. This flow stays with the completed problem;
do not copy it into the reusable skill notes.

## Reusable skills

Return one `skills` entry for each distinct technique that would be useful on
another problem. A solution may need one skill or several; usually 1-3 is
enough. Split a compound recipe into separate skills when its parts have
different recognition clues, proof obligations, or uses. Do not split routine
implementation steps or create several names for the same technique.

For each skill return:

- `skill_path`: a taxonomy path, as lowercase segments such as
  `graphs/successor-transitions/binary-lifting`. The first segment is a broad
  category. Use names for ideas, not procedures, formulas, variables, or
  complexity bounds.
- `signals`: reusable clues that suggest the technique may apply.
- `questions`: short prompts that help a contestant discover it.
- `how_to_apply`: a short sequence of decisions, starting with the condition
  to check and ending with what to verify.
- `why_it_works`: the invariant, exchange, bound, or proof that justifies the
  decisions. State the assumptions. A concise formula is welcome when it
  clarifies the proof; define its terms.
- `when_it_fails`: a real missing assumption, counterexample, or boundary of
  the argument. Give a small example when possible. Do not invent a limitation.
- `reasoning_patterns`: concise transferable takeaways.
- `probably_related`: paths to other relevant skills, if known.

Keep skill fields reusable across problems. Avoid problem names, exact input
values, variable names from the editorial, and one-off story details. A formula
can remain when it expresses the general technique. Preserve the conditions
that make it true.

The final skill notes contain only the skill fields above. The problem's
specific combination, observations, and proof details belong in its completed
analysis. Return JSON following the supplied schema.
