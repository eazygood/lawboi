from lawboi.answer.citations import extract_citations, detect_language, format_context


def _prov(section, eli, title):
    return {"section_num": section, "text": "t",
            "metadata": {"act_title": title, "eli": eli, "subsection": ""}}


def test_extract_citations_matches_section_in_answer():
    provs = [_prov("97", "RT I 2009, 5, 35", "TLS")]
    cites = extract_citations("Per § 97 the notice period applies.", provs)
    assert len(cites) == 1
    assert cites[0]["section"] == "§ 97"
    assert cites[0]["eli"] == "RT I 2009, 5, 35"


def test_extract_citations_ignores_unmentioned():
    provs = [_prov("5", "RT I 2009, 5, 35", "TLS")]
    assert extract_citations("No section here.", provs) == []


def test_detect_language():
    assert detect_language("Mis on tööõigus ja töötaja õigused?") == "et"
    assert detect_language("What is the rate?") == "en"


def test_format_context_includes_section_and_eli():
    out = format_context([_prov("97", "RT I 2009, 5, 35", "TLS")])
    assert "§ 97" in out and "RT I 2009, 5, 35" in out
