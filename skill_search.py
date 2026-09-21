"""Find existing skills that may cover a newly analyzed problem."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SkillDocument:
    path: Path
    relative_path: str
    title: str
    text: str
    tokens: frozenset[str]


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.lower()))


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load_skill_documents(skills_dir: Path) -> list[SkillDocument]:
    """Read all Markdown skills below *skills_dir* into a searchable index."""
    documents: list[SkillDocument] = []
    if not skills_dir.exists():
        return documents

    for path in sorted(skills_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = path.relative_to(skills_dir).with_suffix("").as_posix()
        title = _title(text, path.stem.replace("_", " "))
        searchable = " ".join((relative, title, text))
        documents.append(
            SkillDocument(
                path=path,
                relative_path=relative,
                title=title,
                text=text,
                tokens=frozenset(_tokens(searchable)),
            )
        )
    return documents


def analysis_query(analysis: dict) -> str:
    """Create a semantic-search query from the Codex analysis."""
    fields: list[str] = []
    for key in (
        "core_idea",
        "skill_path",
        "key_observations",
        "reasoning_patterns",
        "questions",
        "probably_related",
    ):
        value = analysis.get(key, "")
        if isinstance(value, list):
            fields.extend(str(item) for item in value)
        else:
            fields.append(str(value))
    return " ".join(fields)


def rank_candidates(
    analysis: dict,
    documents: Iterable[SkillDocument],
    limit: int = 8,
) -> list[SkillDocument]:
    """Return the strongest lexical matches for an analysis.

    This is intentionally lightweight retrieval. Codex makes the final semantic
    equivalence decision after seeing this shortlist.
    """
    query_tokens = _tokens(analysis_query(analysis))
    if not query_tokens:
        return []

    scored: list[tuple[float, SkillDocument]] = []
    for document in documents:
        overlap = query_tokens & document.tokens
        if not overlap:
            continue
        score = len(overlap) / max(1, len(query_tokens))
        # Titles and paths are stronger signals than body-text overlap.
        title_path_tokens = _tokens(
            f"{document.title} {document.relative_path}"
        )
        score += 2 * len(query_tokens & title_path_tokens) / max(
            1, len(query_tokens)
        )
        scored.append((score, document))

    scored.sort(key=lambda item: (-item[0], item[1].relative_path))
    return [document for _, document in scored[:limit]]


def candidate_context(candidates: Iterable[SkillDocument]) -> str:
    chunks: list[str] = []
    for candidate in candidates:
        chunks.append(
            f"PATH: {candidate.relative_path}\n"
            f"TITLE: {candidate.title}\n"
            f"CONTENT:\n{candidate.text}"
        )
    return "\n\n--- CANDIDATE ---\n\n".join(chunks)
