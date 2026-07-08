import re
from collections import defaultdict

from pydantic import BaseModel, Field


class CitationOut(BaseModel):
    section: str = Field(description="Section number cited, e.g. '97' or '§ 97'.")
    act_title: str = Field(description="Title of the act the section belongs to.")
    subsection: str = Field(default="", description="Subsection/lõige, if cited, else empty.")


class AnswerPayload(BaseModel):
    answer: str = Field(description="The full answer to the user's question.")
    citations: list[CitationOut] = Field(
        default_factory=list,
        description="Every provision actually relied on to answer the question.")


def format_context(provisions: list[dict]) -> str:
    parts = []
    for p in provisions:
        section = p.get("section_num", "")
        act_title = p.get("metadata", {}).get("act_title", "")
        eli = p.get("metadata", {}).get("eli", "")
        text = p.get("text", "")
        parts.append(f"[§ {section} | {act_title} | {eli}]\n{text}")
    return "\n\n---\n\n".join(parts)


def _normalize_section(section: str) -> str:
    m = re.search(r"\d+[a-z]?", section)
    return m.group() if m else section.strip()


def validate_citations(citations: list[CitationOut], provisions: list[dict]) -> list[dict]:
    """Drop any LLM-returned citation that doesn't match a retrieved provision."""
    by_section: dict[str, list[dict]] = defaultdict(list)
    for p in provisions:
        by_section[p.get("section_num", "")].append(p)

    result = []
    seen: set[tuple[str, str]] = set()
    for c in citations:
        section = _normalize_section(c.section)
        candidates = by_section.get(section)
        if not candidates:
            continue
        match = next(
            (p for p in candidates
             if p.get("metadata", {}).get("act_title", "") == c.act_title),
            candidates[0],
        )
        meta = match.get("metadata", {})
        eli_raw = meta.get("eli", "")
        key = (section, eli_raw)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "act_title": meta.get("act_title", ""),
            "section": f"§ {section}",
            "subsection": c.subsection or meta.get("subsection", ""),
            "eli": eli_raw,
            "url": (
                f"https://www.riigiteataja.ee/akt/"
                f"{eli_raw.replace(' ', '_').replace(',', '')}"
            ),
        })
    return result


def detect_language(text: str) -> str:
    estonian_chars = set("äöüõšž")
    count = sum(1 for c in text.lower() if c in estonian_chars)
    return "et" if count >= 1 else "en"
