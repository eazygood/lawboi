from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.vector_store import VectorStore


class IngestService:
    """Writes act metadata to the structured store and provision embeddings to
    the vector store, keeping the two in sync (mirrors index_act in indexer.py)."""

    def __init__(self, store: StructuredStore, vector: VectorStore, embedder):
        self._store = store
        self._vector = vector
        self._embedder = embedder

    def index_act(self, act: Act, version: ActVersion,
                  provisions: list[Provision], chunks: list[Chunk]) -> None:
        act_id = self._store.upsert_act(act)
        version.act_id = act_id
        version_id = self._store.upsert_act_version(version)
        if self._store.version_has_provisions(version_id):
            return
        for provision, chunk in zip(provisions, chunks):
            provision.act_version_id = version_id
            chunk.act_version_id = version_id
            provision.id = self._store.insert_provision(provision)
            chunk.provision_id = provision.id
            embedding = self._embedder.embed_passage(chunk.text)
            self._vector.upsert(provision.id, embedding)
