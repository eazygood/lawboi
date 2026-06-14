from lawboi.ports.llm import LLMProvider
from lawboi.domain.errors import NoSourcesFoundError
from lawboi.answer.prompts import SYSTEM_PROMPT, DISCLAIMER
from lawboi.answer.citations import format_context, extract_citations, detect_language


class AnswerService:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def answer(self, query: str, provisions: list[dict]) -> dict:
        if not provisions:
            raise NoSourcesFoundError("No relevant provisions found")
        prompt = SYSTEM_PROMPT.format(context=format_context(provisions), query=query)
        answer_text = self._llm.complete(prompt)
        citations = extract_citations(answer_text, provisions)
        translation_warning = any(
            p.get("metadata", {}).get("is_translation", False) for p in provisions)
        return {
            "answer": answer_text,
            "model_used": self._llm.name,
            "citations": citations,
            "language_detected": detect_language(query),
            "translation_warning": translation_warning,
            "disclaimer": DISCLAIMER,
        }
