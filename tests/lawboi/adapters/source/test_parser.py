from datetime import date
from lawboi.adapters.source.parser import parse_act_xml, parse_act
from lawboi.domain.models import Provision

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <loige nr="1">
        <tekst>Kaeesolev seadus reguleerib toolepingu.</tekst>
      </loige>
      <loige nr="2">
        <tekst>Seadus ei kehti ametnike kohta.</tekst>
      </loige>
    </paragrahv>
    <paragrahv nr="2">
      <loige nr="1">
        <tekst>Toolepingut ei saa sulgeda suuliselt.</tekst>
      </loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_returns_provisions():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    assert len(provisions) > 0
    assert all(isinstance(p, Provision) for p in provisions)


def test_parse_section_numbers():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "1" in section_nums
    assert "2" in section_nums


def test_parse_preserves_text():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    all_text = " ".join(p.text_et for p in provisions)
    assert "toolepingu" in all_text.lower()


def test_parse_sets_act_version_id():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=42,
                                effective_from=date(2009, 7, 1), effective_to=None)
    assert all(p.act_version_id == 42 for p in provisions)


def test_parse_levels():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    levels = {p.level for p in provisions}
    assert "section" in levels


FULL_SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <kehtivus>
      <kehtivuseAlgus>2009-07-01</kehtivuseAlgus>
    </kehtivus>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <loige nr="1"><tekst>Kaeesolev seadus reguleerib toolepingu.</tekst></loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_act_returns_all_fields():
    result = parse_act(FULL_SAMPLE_XML, act_version_id=7)
    assert result.title == "Toolepingu seadus"
    assert result.effective_from is not None
    assert result.effective_to is None
    assert len(result.provisions) == 1
    assert result.provisions[0].act_version_id == 7
