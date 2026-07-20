from lawboi.ingest.chunker import chunk_provisions
from lawboi.domain.models import Provision


def test_chunk_includes_neighbour_context():
    provs = [
        Provision(1, 10, "1", "section", "esimene", None, None),
        Provision(2, 10, "2", "section", "teine", None, None),
        Provision(3, 10, "3", "section", "kolmas", None, None),
    ]
    chunks = chunk_provisions(provs, act_title="TLS", eli="RT I 2009, 5, 35",
                              source_global_id=331584)
    assert len(chunks) == 3
    assert "esimene" in chunks[1].metadata["context"]
    assert "kolmas" in chunks[1].metadata["context"]
    assert chunks[1].metadata["eli"] == "RT I 2009, 5, 35"
    assert chunks[1].metadata["source_global_id"] == 331584
