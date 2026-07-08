from typing import Optional

from lawboi.ports.llm import LLMProvider
from lawboi.domain.errors import NoSourcesFoundError
from lawboi.answer.prompts import SYSTEM_PROMPT, DISCLAIMER, format_history
from lawboi.answer.citations import AnswerPayload, format_context, validate_citations, detect_language


class AnswerService:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def answer(self, query: str, provisions: list[dict],
                      history: Optional[list[dict]] = None) -> dict:
        if not provisions:
            raise NoSourcesFoundError("No relevant provisions found")
        prompt = SYSTEM_PROMPT.format(
            context=format_context(provisions), history=format_history(history), query=query)
        payload = await self._llm.complete_structured(prompt, AnswerPayload)
        citations = validate_citations(payload.citations, provisions)
        translation_warning = any(
            p.get("metadata", {}).get("is_translation", False) for p in provisions)
        return {
            "answer": payload.answer,
            "model_used": self._llm.name,
            "citations": citations,
            "language_detected": detect_language(query),
            "translation_warning": translation_warning,
            "disclaimer": DISCLAIMER,
        }
