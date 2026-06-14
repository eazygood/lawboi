import re
from collections import defaultdict


def format_context(provisions: list[dict]) -> str:
    parts = []
    for p in provisions:
        section = p.get("section_num", "")
        act_title = p.get("metadata", {}).get("act_title", "")
        eli = p.get("metadata", {}).get("eli", "")
        text = p.get("text", "")
        parts.append(f"[§ {section} | {act_title} | {eli}]\n{text}")
    return "\n\n---\n\n".join(parts)


def extract_citations(answer: str, provisions: list[dict]) -> list[dict]:
    by_section: dict[str, list[dict]] = defaultdict(list)
    for p in provisions:
        section = p.get("section_num", "")
        if section and re.search(rf"§\s*{re.escape(section)}\b", answer):
            by_section[section].append(p)

    citations = []
    seen: set[tuple[str, str]] = set()
    for section, candidates in by_section.items():
        if len(candidates) > 1:
            mentioned = [
                p for p in candidates
                if p.get("metadata", {}).get("act_title", "") in answer
                or p.get("metadata", {}).get("eli", "") in answer
            ]
            candidates = mentioned if mentioned else candidates[:1]
        for p in candidates:
            meta = p.get("metadata", {})
            eli_raw = meta.get("eli", "")
            key = (section, eli_raw)
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "act_title": meta.get("act_title", ""),
                "section": f"§ {section}",
                "subsection": meta.get("subsection", ""),
                "eli": eli_raw,
                "url": (
                    f"https://www.riigiteataja.ee/akt/"
                    f"{eli_raw.replace(' ', '_').replace(',', '')}"
                ),
            })
    return citations


def detect_language(text: str) -> str:
    estonian_chars = set("äöüõšž")
    count = sum(1 for c in text.lower() if c in estonian_chars)
    return "et" if count > 2 else "en"
