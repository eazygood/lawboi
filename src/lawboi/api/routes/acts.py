from datetime import date
from fastapi import APIRouter, Depends, HTTPException

from lawboi.api.deps import get_store
from lawboi.api.schemas import ActResponse, ActVersionResponse, ProvisionResponse

router = APIRouter()


@router.get("/acts/{eli:path}/versions", response_model=list[ActVersionResponse])
async def get_act_versions(eli: str, store=Depends(get_store)):
    return [
        ActVersionResponse(id=v.id, effective_from=v.effective_from,
                           effective_to=v.effective_to, source_url=v.source_url)
        for v in await store.list_act_versions(eli)
    ]


@router.get("/acts/{eli:path}/as-of", response_model=list[ProvisionResponse])
async def get_act_as_of(eli: str, date: date, store=Depends(get_store)):
    return [
        ProvisionResponse(id=p.id, section_num=p.section_num, text_et=p.text_et,
                          text_en=p.text_en, level=p.level)
        for p in await store.provisions_as_of(eli, date)
    ]


@router.get("/acts/{eli:path}", response_model=ActResponse)
async def get_act(eli: str, store=Depends(get_store)):
    act = await store.get_act(eli)
    if act is None:
        raise HTTPException(status_code=404, detail="Act not found")
    return ActResponse(id=act.id, eli=act.eli, title_et=act.title_et,
                       title_en=act.title_en, domain=act.domain, act_type=act.act_type)
