from datetime import date
from typing import Optional, Sequence

from lawboi.pipeline.context import RetrievalContext, RetrievalConfig
from lawboi.pipeline.stages import RetrievalStage


async def run_pipeline(stages: Sequence[RetrievalStage], query: str, as_of: date,
                       config: Optional[RetrievalConfig] = None) -> RetrievalContext:
    ctx = RetrievalContext(query=query, as_of=as_of, config=config or RetrievalConfig())
    for stage in stages:
        ctx = await stage(ctx)
    return ctx


class RetrievalService:
    def __init__(self, stages: Sequence[RetrievalStage], default_limit: int = 5):
        self._stages = stages
        self._default_limit = default_limit

    async def retrieve(self, query: str, as_of: Optional[date] = None,
                       limit: Optional[int] = None) -> list[dict]:
        limit = limit or self._default_limit
        config = RetrievalConfig(limit=limit)
        ctx = await run_pipeline(self._stages, query, as_of or date.today(), config)
        return ctx.candidates[:limit]
