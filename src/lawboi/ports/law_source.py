from typing import Iterable, Iterator, Protocol, runtime_checkable

from lawboi.domain.dto import ActMeta, RawAct


@runtime_checkable
class LawSource(Protocol):
    def search(self, query: str, limit: int = 10) -> list[ActMeta]: ...

    def fetch(self, global_id: int) -> RawAct: ...

    def iter_corpus(
        self, doc_types: Iterable[str], page_size: int = 200
    ) -> Iterator[ActMeta]: ...
