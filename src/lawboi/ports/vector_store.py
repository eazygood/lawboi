from datetime import date
from typing import Protocol, runtime_checkable
from lawboi.domain.dto import VectorHit


@runtime_checkable
class VectorStore(Protocol):
    def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]: ...

    def upsert(self, provision_id: int, embedding: list[float]) -> None: ...

    def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None: ...
