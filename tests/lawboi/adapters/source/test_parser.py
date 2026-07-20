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


SAMPLE_XML_WITH_HEADING = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <paragrahvPealkiri>Katseaeg</paragrahvPealkiri>
      <loige nr="1">
        <tekst>Katseaja pikkus on neli kuud.</tekst>
      </loige>
    </paragrahv>
    <paragrahv nr="2">
      <loige nr="1">
        <tekst>Toolepingut ei saa sulgeda suuliselt.</tekst>
      </loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_section_heading_present_and_absent():
    provisions = parse_act_xml(SAMPLE_XML_WITH_HEADING, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    by_section = {p.section_num: p for p in provisions}
    assert by_section["1"].heading == "Katseaeg"
    assert by_section["2"].heading is None


OSA_PEATYKK_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Volaoigusseadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <osa nr="1">
      <osaPealkiri>Uldosa</osaPealkiri>
      <peatykk nr="1">
        <peatykkPealkiri>Uldsatted</peatykkPealkiri>
        <paragrahv nr="1">
          <loige nr="1">
            <tekst>Volaoigusseadus reguleerib volasuhteid.</tekst>
          </loige>
        </paragrahv>
      </peatykk>
    </osa>
  </sisu>
</akt>"""


def test_parse_section_nested_under_osa_and_peatykk():
    provisions = parse_act_xml(OSA_PEATYKK_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "1" in section_nums


OSA_PEATYKK_JAGU_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Volaoigusseadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <osa nr="2">
      <osaPealkiri>Lepingud</osaPealkiri>
      <peatykk nr="1">
        <peatykkPealkiri>Uurileping</peatykkPealkiri>
        <jagu nr="1">
          <jaguPealkiri>Uldsatted</jaguPealkiri>
          <paragrahv nr="272">
            <loige nr="1">
              <tekst>Uurilepingu alusel kohustub uurileandja andma asja kasutamiseks.</tekst>
            </loige>
          </paragrahv>
        </jagu>
      </peatykk>
    </osa>
  </sisu>
</akt>"""


def test_parse_section_nested_under_osa_peatykk_jagu():
    provisions = parse_act_xml(OSA_PEATYKK_JAGU_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "272" in section_nums


MIXED_PEATYKK_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <peatykk nr="2">
      <peatykkPealkiri>Toolepingu solmimine</peatykkPealkiri>
      <paragrahv nr="9">
        <loige nr="1">
          <tekst>Tooleping solmitakse kirjalikult.</tekst>
        </loige>
      </paragrahv>
      <jagu nr="1">
        <jaguPealkiri>Katseaeg</jaguPealkiri>
        <paragrahv nr="10">
          <paragrahvPealkiri>Katseaeg</paragrahvPealkiri>
          <loige nr="1">
            <tekst>Katseaja pikkus on neli kuud.</tekst>
          </loige>
        </paragrahv>
      </jagu>
    </peatykk>
  </sisu>
</akt>"""


def test_parse_section_mixed_direct_and_jagu_wrapped_under_peatykk():
    provisions = parse_act_xml(MIXED_PEATYKK_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "9" in section_nums
    assert "10" in section_nums


UNRECOGNIZED_ELEMENT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
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
    </paragrahv>
    <lisa nr="1">
      <lisaTekst>Lisa tekst, mida parser ei tunne.</lisaTekst>
    </lisa>
  </sisu>
</akt>"""


def test_parse_warns_on_unrecognized_element(capsys):
    provisions = parse_act_xml(UNRECOGNIZED_ELEMENT_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    captured = capsys.readouterr()
    assert "Warning" in captured.out
    assert "lisa" in captured.out
    section_nums = {p.section_num for p in provisions}
    assert "1" in section_nums


def test_parse_does_not_warn_on_metadata_tags(capsys):
    provisions = parse_act_xml(OSA_PEATYKK_JAGU_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    captured = capsys.readouterr()
    assert "Warning" not in captured.out


ORDER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <jagu nr="1">
      <jaguPealkiri>Esimene jagu</jaguPealkiri>
      <paragrahv nr="5">
        <loige nr="1"><tekst>Jagu alusel paragrahv viis.</tekst></loige>
      </paragrahv>
    </jagu>
    <paragrahv nr="6">
      <loige nr="1"><tekst>Otse sisu all paragrahv kuus.</tekst></loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_returns_sections_in_document_order():
    provisions = parse_act_xml(ORDER_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = [p.section_num for p in provisions]
    assert section_nums == ["5", "6"]


OSA_PEATYKK_JAGU_JAOTIS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Volaoigusseadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <osa nr="2">
      <osaPealkiri>Lepingud</osaPealkiri>
      <peatykk nr="1">
        <peatykkPealkiri>Uurileping</peatykkPealkiri>
        <jagu nr="1">
          <jaguPealkiri>Uldsatted</jaguPealkiri>
          <jaotis id="jaotis1">
            <jaotisNr>1</jaotisNr>
            <kuvatavNr>1</kuvatavNr>
            <jaotisPealkiri>Uurileandja kohustused</jaotisPealkiri>
            <paragrahv nr="278">
              <loige nr="1">
                <tekst>Uurileandja on kohustatud andma asja korras seisundis.</tekst>
              </loige>
            </paragrahv>
          </jaotis>
        </jagu>
      </peatykk>
    </osa>
  </sisu>
</akt>"""


def test_parse_section_nested_under_osa_peatykk_jagu_jaotis():
    provisions = parse_act_xml(OSA_PEATYKK_JAGU_JAOTIS_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "278" in section_nums


OSA_PEATYKK_JAGU_JAOTIS_ALLJAOTIS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Asjaoigusseadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <osa nr="1">
      <osaPealkiri>Uldsatted</osaPealkiri>
      <peatykk nr="1">
        <peatykkPealkiri>Asjaoigus ja asi</peatykkPealkiri>
        <jagu nr="1">
          <jaguPealkiri>Uldsatted</jaguPealkiri>
          <jaotis id="jaotis1">
            <jaotisNr>1</jaotisNr>
            <kuvatavNr>1</kuvatavNr>
            <jaotisPealkiri>Asjaoiguse moiste</jaotisPealkiri>
            <alljaotis id="alljaotis1">
              <alljaotisNr>1</alljaotisNr>
              <kuvatavNr>1</kuvatavNr>
              <alljaotisPealkiri>Asja moiste</alljaotisPealkiri>
              <paragrahv nr="50">
                <loige nr="1">
                  <tekst>Asi on kehaline ese.</tekst>
                </loige>
              </paragrahv>
            </alljaotis>
          </jaotis>
        </jagu>
      </peatykk>
    </osa>
  </sisu>
</akt>"""


def test_parse_section_nested_under_osa_peatykk_jagu_jaotis_alljaotis():
    provisions = parse_act_xml(OSA_PEATYKK_JAGU_JAOTIS_ALLJAOTIS_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "50" in section_nums
