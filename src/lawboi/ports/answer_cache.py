from datetime import date
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AnswerCache(Protocol):
    async def find(self, embedding: list[float], as_of: date) -> Optional[dict]: ...

    async def store(self, embedding: list[float], as_of: date, query_text: str,
                     cache_key_text: str, answer_payload: dict) -> None: ...

    async def clear(self) -> None: ...
