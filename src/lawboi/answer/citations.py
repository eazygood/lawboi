import re
from collections import defaultdict
from typing import Optional

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


def format_context(provisions: list[dict], max_chars: Optional[int] = None) -> str:
    parts = []
    for p in provisions:
        section = p.get("section_num", "")
        act_title = p.get("metadata", {}).get("act_title", "")
        eli = p.get("metadata", {}).get("eli", "")
        text = p.get("text", "")
        if max_chars is not None and len(text) > max_chars:
            text = text[:max_chars] + " […truncated]"
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
        source_global_id = meta.get("source_global_id")
        result.append({
            "act_title": meta.get("act_title", ""),
            "section": f"§ {section}",
            "subsection": c.subsection or meta.get("subsection", ""),
            "eli": eli_raw,
            "heading": meta.get("heading", ""),
            "url": (
                f"https://www.riigiteataja.ee/akt/{source_global_id}"
                if source_global_id else ""
            ),
        })
    return result


_SECTION_MENTION = re.compile(r"§\s*(\d+[a-z]?)", re.IGNORECASE)


def find_unverified_sections(answer: str, citations: list[dict]) -> list[str]:
    """Section numbers mentioned in the answer text with no matching validated citation."""
    validated = {_normalize_section(c["section"]).lower() for c in citations}
    mentioned = {m.group(1).lower() for m in _SECTION_MENTION.finditer(answer)}
    return sorted(mentioned - validated, key=lambda s: (len(s), s))


_ESTONIAN_CHARS = set("äöüõšž")

# Common function words as a fallback signal for Estonian questions that happen to
# have no diacritics (e.g. "Kui kaua on mul aega vaidlustada?").
_ESTONIAN_WORDS = {
    "mis", "kus", "kes", "kas", "kui", "kuidas", "miks", "millal", "kaua",
    "ja", "ning", "või", "ei", "ega", "on", "ma", "mul", "mulle", "mind", "minu",
    "sa", "sul", "sulle", "sind", "sinu", "ta", "tema", "meie", "teie", "nemad",
    "see", "seda", "selle", "oma", "aga", "siis", "palun", "aitäh",
    "tööandja", "töötaja", "seadus", "õigus",
}
_ENGLISH_WORDS = {
    "the", "is", "are", "what", "how", "when", "where", "why", "who",
    "can", "could", "should", "would", "this", "that", "and", "or", "but",
    "please", "thanks", "thank", "you", "my", "your", "employer", "employee",
    "law", "rights", "does", "did", "will", "have", "has",
}


def detect_language(text: str) -> str:
    lowered = text.lower()
    if any(c in _ESTONIAN_CHARS for c in lowered):
        return "et"
    words = set(re.findall(r"[a-zäöüõšž]+", lowered))
    et_hits = len(words & _ESTONIAN_WORDS)
    en_hits = len(words & _ENGLISH_WORDS)
    if et_hits > 0 and et_hits >= en_hits:
        return "et"
    return "en"  # default: matches prior behavior when no Estonian signal is found
