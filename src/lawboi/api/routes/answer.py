import asyncio
import logging

from fastapi import APIRouter, Depends, Request

from lawboi.api.limiter import limiter
from lawboi.api.schemas import AnswerRequest, AnswerResponse
from lawboi.api.deps import get_retrieval, get_answer, get_store, get_moderation
from lawboi.adapters.llm.factory import available_models
from lawboi.domain.errors import ContentBlockedError

router = APIRouter()
log = logging.getLogger(__name__)

_HISTORY_LIMIT = 10  # last 5 turns, verbatim
_REFUSAL_MESSAGE = (
    "I can't provide that response. Please rephrase your question about Estonian law."
)


@router.post("/answer", response_model=AnswerResponse)
@limiter.limit("10/minute")
async def answer(request: Request, req: AnswerRequest, retrieval=Depends(get_retrieval),
                  answerer=Depends(get_answer), store=Depends(get_store),
                  moderation=Depends(get_moderation)):
    conversation_id = req.conversation_id
    if conversation_id is None:
        conversation_id = await store.create_conversation()

    history, provisions, input_check = await asyncio.gather(
        store.recent_messages(conversation_id, limit=_HISTORY_LIMIT),
        retrieval.retrieve(req.query, as_of=req.as_of_date),
        moderation.check(req.query),
    )
    if input_check.flagged:
        log.warning("Input blocked by moderation: %s", input_check.reason)
        raise ContentBlockedError(input_check.reason or "Input flagged by moderation")

    result = await answerer.answer(
        req.query, provisions, history=history)  # raises NoSourcesFoundError -> 422

    output_check = await moderation.check(result["answer"])
    if output_check.flagged:
        log.warning("Output blocked by moderation: %s", output_check.reason)
        result["answer"] = _REFUSAL_MESSAGE

    await store.append_message(conversation_id, "user", req.query)
    await store.append_message(conversation_id, "assistant", result["answer"])
    return AnswerResponse(**result, conversation_id=conversation_id)


@router.get("/models")
def models():
    return {"models": available_models()}
