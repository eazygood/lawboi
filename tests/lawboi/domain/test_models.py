from datetime import date
from lawboi.domain.models import Act, ActVersion, Provision, Chunk


def test_provision_holds_hierarchy_fields():
    p = Provision(id=1, act_version_id=2, section_num="5", level="section",
                  text_et="tekst", text_en=None, parent_id=None)
    assert p.section_num == "5"
    assert p.level == "section"


def test_chunk_carries_metadata_dict():
    c = Chunk(provision_id=1, act_version_id=2, section_num="5",
              text="t", metadata={"eli": "RT I 2009, 5, 35"})
    assert c.metadata["eli"] == "RT I 2009, 5, 35"


def test_act_version_optional_end_date():
    v = ActVersion(id=None, act_id=1, effective_from=date(2020, 1, 1),
                   effective_to=None, source_url="u", source_hash="h")
    assert v.effective_to is None
