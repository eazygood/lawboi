from fastapi import APIRouter, Depends, Request

from lawboi.api.limiter import limiter
from lawboi.api.schemas import AnswerRequest, AnswerResponse
from lawboi.api.deps import get_retrieval, get_answer
from lawboi.adapters.llm.factory import available_models

router = APIRouter()


@router.post("/answer", response_model=AnswerResponse)
@limiter.limit("10/minute")
def answer(request: Request, req: AnswerRequest, retrieval=Depends(get_retrieval), answerer=Depends(get_answer)):
    provisions = retrieval.retrieve(req.query, as_of=req.as_of_date)
    result = answerer.answer(req.query, provisions)  # raises NoSourcesFoundError -> 422
    return AnswerResponse(**result)


@router.get("/models")
def models():
    return {"models": available_models()}
