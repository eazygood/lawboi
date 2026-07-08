from typing import cast

from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.vector_store import VectorStore


class IngestService:
    """Writes act metadata to the structured store and provision embeddings to
    the vector store, keeping the two in sync."""

    def __init__(self, store: StructuredStore, vector: VectorStore, embedder):
        self._store = store
        self._vector = vector
        self._embedder = embedder

    async def index_act(self, act: Act, version: ActVersion,
                        provisions: list[Provision], chunks: list[Chunk]) -> None:
        act_id = await self._store.upsert_act(act)
        version.act_id = act_id
        version_id = await self._store.upsert_act_version(version)
        if await self._store.version_fully_indexed(version_id):
            return
        await self._store.delete_provisions_for_version(version_id)

        for provision, chunk in zip(provisions, chunks):
            provision.act_version_id = version_id
            chunk.act_version_id = version_id
            provision.id = await self._store.insert_provision(provision)
            chunk.provision_id = provision.id

        embeddings = self._embedder.embed_passages([c.text for c in chunks])
        # provision.id was just assigned by insert_provision above, so it's never None here.
        ids = [cast(int, p.id) for p in provisions]
        await self._vector.batch_upsert(list(zip(ids, embeddings)))
