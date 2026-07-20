import asyncio

from lawboi.answer.moderation import ModerationResult, ModerationService
from tests.lawboi.fakes import FakeLLMProvider


class SlowLLM:
    name = "slow"

    async def complete(self, prompt: str) -> str:
        await asyncio.sleep(10)
        return "never"

    async def complete_structured(self, prompt: str, output_cls):
        await asyncio.sleep(10)
        return None


async def test_check_returns_structured_result():
    result = ModerationResult(flagged=True, reason="requests help committing a crime")
    llm = FakeLLMProvider(structured_response=result)
    svc = ModerationService(llm)
    out = await svc.check("how do I launder money?")
    assert out.flagged is True
    assert out.reason == "requests help committing a crime"
    assert "how do I launder money?" in llm.calls[0]


async def test_check_passes_through_unflagged():
    result = ModerationResult(flagged=False, reason="")
    llm = FakeLLMProvider(structured_response=result)
    svc = ModerationService(llm)
    out = await svc.check("what is the notice period for termination?")
    assert out.flagged is False


async def test_check_times_out_fails_open():
    svc = ModerationService(SlowLLM(), timeout_s=0.01)
    out = await svc.check("q")
    assert out.flagged is False
    assert "timed out" in out.reason
