from lawboi.domain.dto import VectorHit, ActMeta, RawAct, RetrievedProvision


def test_retrieved_provision_shape():
    rp = RetrievedProvision(provision_id=1, section_num="5", text="t",
                            metadata={"eli": "RT I 2009, 5, 35", "act_title": "TLS"})
    assert rp.provision_id == 1
    assert rp.metadata["act_title"] == "TLS"


def test_vector_hit():
    h = VectorHit(provision_id=1, section_num="5", text="t", metadata={})
    assert h.provision_id == 1


def test_act_meta_and_raw_act():
    m = ActMeta(global_id=123, title="TLS", effective_from=None, effective_to=None)
    r = RawAct(global_id=123, xml=b"<x/>", source_url="u")
    assert m.global_id == 123 and r.xml == b"<x/>"
