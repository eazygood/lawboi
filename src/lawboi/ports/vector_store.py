from typing import Protocol, runtime_checkable
from lawboi.domain.dto import VectorHit


@runtime_checkable
class VectorStore(Protocol):
    def query(self, embedding: list[float], n_results: int) -> list[VectorHit]: ...

    def upsert(self, provision_id: int, embedding: list[float]) -> None: ...
