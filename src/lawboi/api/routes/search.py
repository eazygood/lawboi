from fastapi import APIRouter, Depends, Request

from lawboi.api.limiter import limiter
from lawboi.api.schemas import ProvisionResult, SearchRequest
from lawboi.api.deps import get_retrieval

router = APIRouter()


@router.post("/search", response_model=list[ProvisionResult])
@limiter.limit("30/minute")
async def search(request: Request, req: SearchRequest, retrieval=Depends(get_retrieval)):
    provisions = await retrieval.retrieve(req.query, as_of=req.as_of_date, limit=req.limit)
    return [
        ProvisionResult(
            provision_id=p["provision_id"],
            section_num=p["section_num"],
            text_et=p["text"],
            act_title=p.get("metadata", {}).get("act_title", ""),
            eli=p.get("metadata", {}).get("eli", ""),
        )
        for p in provisions
    ]
