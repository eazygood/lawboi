import asyncio
from typing import Optional

from lawboi.ports.llm import LLMProvider
from lawboi.domain.errors import NoSourcesFoundError, LLMTimeoutError
from lawboi.answer.prompts import SYSTEM_PROMPT, DISCLAIMER, format_history
from lawboi.answer.citations import AnswerPayload, format_context, validate_citations, detect_language


class AnswerService:
    def __init__(self, llm: LLMProvider, timeout_s: float = 20.0,
                 max_provision_chars: Optional[int] = None,
                 max_history_chars: Optional[int] = None):
        self._llm = llm
        self._timeout_s = timeout_s
        self._max_provision_chars = max_provision_chars
        self._max_history_chars = max_history_chars

    async def answer(self, query: str, provisions: list[dict],
                      history: Optional[list[dict]] = None) -> dict:
        if not provisions:
            raise NoSourcesFoundError("No relevant provisions found")
        prompt = SYSTEM_PROMPT.format(
            context=format_context(provisions, max_chars=self._max_provision_chars),
            history=format_history(history, max_chars=self._max_history_chars),
            query=query)
        try:
            payload = await asyncio.wait_for(
                self._llm.complete_structured(prompt, AnswerPayload), timeout=self._timeout_s)
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Answer generation timed out after {self._timeout_s:.1f}s") from exc
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
