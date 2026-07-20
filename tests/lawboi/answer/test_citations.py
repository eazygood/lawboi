from lawboi.answer.citations import CitationOut, detect_language, format_context, validate_citations


def _prov(section, eli, title, source_global_id=331584, heading=""):
    return {"section_num": section, "text": "t",
            "metadata": {"act_title": title, "eli": eli, "subsection": "",
                        "source_global_id": source_global_id, "heading": heading}}


def test_validate_citations_keeps_matching_section():
    provs = [_prov("97", "RT I 2009, 5, 35", "TLS")]
    cites = validate_citations([CitationOut(section="97", act_title="TLS")], provs)
    assert len(cites) == 1
    assert cites[0]["section"] == "§ 97"
    assert cites[0]["eli"] == "RT I 2009, 5, 35"
    assert cites[0]["url"] == "https://www.riigiteataja.ee/akt/331584"


def test_validate_citations_drops_hallucinated():
    provs = [_prov("5", "RT I 2009, 5, 35", "TLS")]
    assert validate_citations([CitationOut(section="97", act_title="TLS")], provs) == []


def test_detect_language():
    assert detect_language("Mis on tööõigus ja töötaja õigused?") == "et"
    assert detect_language("What is the rate?") == "en"


def test_detect_language_short_query_with_few_diacritics():
    assert detect_language("Mis on katseaja kestus töölepingus?") == "et"


def test_detect_language_estonian_with_no_diacritics():
    assert detect_language("Kui kaua on mul aega vaidlustada?") == "et"


def test_format_context_includes_section_and_eli():
    out = format_context([_prov("97", "RT I 2009, 5, 35", "TLS")])
    assert "§ 97" in out and "RT I 2009, 5, 35" in out


def test_format_context_truncates_long_text():
    prov = _prov("97", "RT I 2009, 5, 35", "TLS")
    prov["text"] = "x" * 100
    out = format_context([prov], max_chars=10)
    assert "x" * 11 not in out
    assert "[…truncated]" in out


def test_validate_citations_includes_heading_when_present():
    provs = [_prov("10", "RT I 2009, 5, 35", "TLS", heading="Katseaeg")]
    cites = validate_citations([CitationOut(section="10", act_title="TLS")], provs)
    assert cites[0]["heading"] == "Katseaeg"


def test_validate_citations_defaults_heading_to_empty():
    provs = [_prov("97", "RT I 2009, 5, 35", "TLS")]  # heading defaults to ""
    cites = validate_citations([CitationOut(section="97", act_title="TLS")], provs)
    assert cites[0]["heading"] == ""
