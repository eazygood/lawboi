import pytest
from lawboi.answer.service import AnswerService
from lawboi.domain.errors import NoSourcesFoundError
from tests.lawboi.fakes import FakeLLMProvider


def _prov(section="97", eli="RT I 2009, 5, 35", title="TLS", is_translation=False):
    return {"section_num": section, "text": "tekst",
            "metadata": {"act_title": title, "eli": eli, "subsection": "",
                         "is_translation": is_translation}}


def test_raises_when_no_provisions():
    svc = AnswerService(FakeLLMProvider())
    with pytest.raises(NoSourcesFoundError):
        svc.answer("query", provisions=[])


def test_returns_answer_dict_with_citations():
    llm = FakeLLMProvider(responses=["Under § 97 notice applies."])
    svc = AnswerService(llm)
    result = svc.answer("notice period?", provisions=[_prov()])
    assert result["answer"] == "Under § 97 notice applies."
    assert result["model_used"] == "fake"
    assert result["citations"][0]["section"] == "§ 97"
    assert result["language_detected"] == "en"
    assert result["disclaimer"]


def test_translation_warning_flag():
    llm = FakeLLMProvider(responses=["§ 97 ..."])
    svc = AnswerService(llm)
    result = svc.answer("q", provisions=[_prov(is_translation=True)])
    assert result["translation_warning"] is True
