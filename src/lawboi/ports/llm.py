from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

Model = TypeVar("Model", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, prompt: str) -> str: ...

    async def complete_structured(self, prompt: str, output_cls: type[Model]) -> Model: ...
