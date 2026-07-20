import asyncio

import pytest
from lawboi.answer.service import AnswerService
from lawboi.answer.citations import AnswerPayload, CitationOut
from lawboi.domain.errors import NoSourcesFoundError, LLMTimeoutError
from tests.lawboi.fakes import FakeLLMProvider


class SlowLLM:
    name = "slow"

    async def complete(self, prompt: str) -> str:
        await asyncio.sleep(10)
        return "never"

    async def complete_structured(self, prompt: str, output_cls):
        await asyncio.sleep(10)
        return None


def _prov(section="97", eli="RT I 2009, 5, 35", title="TLS", is_translation=False):
    return {"section_num": section, "text": "tekst",
            "metadata": {"act_title": title, "eli": eli, "subsection": "",
                         "is_translation": is_translation}}


async def test_raises_when_no_provisions():
    svc = AnswerService(FakeLLMProvider())
    with pytest.raises(NoSourcesFoundError):
        await svc.answer("query", provisions=[])


async def test_returns_answer_dict_with_citations():
    payload = AnswerPayload(
        answer="Under § 97 notice applies.",
        citations=[CitationOut(section="97", act_title="TLS")])
    llm = FakeLLMProvider(structured_response=payload)
    svc = AnswerService(llm)
    result = await svc.answer("notice period?", provisions=[_prov()])
    assert result["answer"] == "Under § 97 notice applies."
    assert result["model_used"] == "fake"
    assert result["citations"][0]["section"] == "§ 97"
    assert result["language_detected"] == "en"
    assert result["disclaimer"]


async def test_hallucinated_citation_is_dropped():
    payload = AnswerPayload(
        answer="Under § 5 something applies.",
        citations=[CitationOut(section="5", act_title="Nonexistent Act")])
    llm = FakeLLMProvider(structured_response=payload)
    svc = AnswerService(llm)
    result = await svc.answer("q", provisions=[_prov()])
    assert result["citations"] == []


async def test_history_is_rendered_into_prompt():
    payload = AnswerPayload(
        answer="Under § 97 notice applies.",
        citations=[CitationOut(section="97", act_title="TLS")])
    llm = FakeLLMProvider(structured_response=payload)
    svc = AnswerService(llm)
    history = [{"role": "user", "content": "what is the notice period?"},
               {"role": "assistant", "content": "It is 30 days."}]
    await svc.answer("and what about severance?", provisions=[_prov()], history=history)
    assert "what is the notice period?" in llm.calls[0]
    assert "It is 30 days." in llm.calls[0]


async def test_translation_warning_flag():
    payload = AnswerPayload(
        answer="§ 97 ...", citations=[CitationOut(section="97", act_title="TLS")])
    llm = FakeLLMProvider(structured_response=payload)
    svc = AnswerService(llm)
    result = await svc.answer("q", provisions=[_prov(is_translation=True)])
    assert result["translation_warning"] is True


async def test_answer_times_out():
    svc = AnswerService(SlowLLM(), timeout_s=0.01)
    with pytest.raises(LLMTimeoutError):
        await svc.answer("q", provisions=[_prov()])
