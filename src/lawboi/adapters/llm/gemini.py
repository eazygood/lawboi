import logging
import time
from typing import Optional

from lawboi.adapters.llm._util import approx_tokens

log = logging.getLogger(__name__)


class GeminiAdapter:
    def __init__(self, model: str, api_key: str, max_tokens: Optional[int] = None):
        self.name = model
        from llama_index.llms.gemini import Gemini
        kwargs = {"model": model, "api_key": api_key}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        self._llm = Gemini(**kwargs)

    async def complete(self, prompt: str) -> str:
        start = time.monotonic()
        text = str(await self._llm.acomplete(prompt))
        log.info("llm_call model=%s method=complete latency_ms=%.0f approx_tokens=%d",
                  self.name, (time.monotonic() - start) * 1000, approx_tokens(prompt, text))
        return text

    async def complete_structured(self, prompt: str, output_cls):
        from llama_index.core.prompts import PromptTemplate
        template = PromptTemplate(prompt.replace("{", "{{").replace("}", "}}"))
        start = time.monotonic()
        result = await self._llm.astructured_predict(output_cls, template)
        log.info("llm_call model=%s method=complete_structured latency_ms=%.0f approx_tokens=%d",
                  self.name, (time.monotonic() - start) * 1000,
                  approx_tokens(prompt, result.model_dump_json()))
        return result
