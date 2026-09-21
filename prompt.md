# Task

Analyze a competitive programming problem and its human-written solution.

The goal is to identify the reusable problem-solving skills and thinking
patterns behind the solution.

Do NOT simply summarize the solution.

## core_idea

Describe the central idea of the solution in 1-3 sentences.

## key_observations

List the important observations that lead toward the solution.

These should explain WHY the solution becomes possible.

## reasoning_patterns

Extract reusable problem-solving patterns.

Focus on ideas that could apply to other competitive programming problems.

For example:

- reducing a problem to an invariant
- fixing a prefix
- preserving future feasibility
- counting by an exact minimum
- exchanging choices
- compressing DP state

Avoid problem-specific implementation details.

## questions

Create short, generic thinking questions that could help a contestant
discover the relevant idea.

Examples:

Can I fix something?

What information actually matters?

Can I reduce the state?

What happens if I fix the minimum?

Can I preserve an invariant?

Can I count by fixing an exact value?

Questions must be reusable across many problems.

## signals

List short, reusable clues that suggest this skill may apply to a problem.

Examples:

- a small critical resource determines how many groups can contribute
- the objective depends on the first missing value
- choices must preserve future feasibility

Avoid problem-specific values, variable names, and implementation details.

## skill_path

Create the hierarchical path for the MAIN reusable skill.

The path represents a taxonomy, not the solution procedure.

Use:

broad_category / family / technique / pattern

For example:

construction/prefix/greedy/lexicographic/smallest_safe_next_element

DO NOT put these in the path:

- implementation steps
- formulas
- variable names
- complexity calculations
- "precompute..."
- "iterate..."
- "calculate..."

The path should describe WHAT KIND OF THINKING the solution uses.

## probably_related

List reusable skills that overlap with the solution but are not the
main skill.

These may belong to completely different branches.

Return paths only.

## Important

The solution is Markdown and may contain prose, formulas, and explanations.

Use the reasoning and proof in the solution to identify the underlying
skill.

Do not focus on programming language or implementation details.

Return JSON following the supplied schema.