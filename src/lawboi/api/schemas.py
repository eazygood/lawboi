from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of_date: Optional[date] = None
    conversation_id: Optional[int] = None


class Citation(BaseModel):
    act_title: str
    section: str
    subsection: str
    eli: str
    url: str


class AnswerResponse(BaseModel):
    answer: str
    model_used: str
    citations: list[Citation]
    language_detected: str
    translation_warning: bool
    disclaimer: str
    conversation_id: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    domain: Optional[str] = None
    as_of_date: Optional[date] = None
    limit: int = Field(default=10, ge=1, le=100)


class ProvisionResult(BaseModel):
    provision_id: int
    section_num: str
    text_et: str
    act_title: str
    eli: str


class ActResponse(BaseModel):
    id: int
    eli: str
    title_et: str
    title_en: Optional[str]
    domain: str
    act_type: str


class ActVersionResponse(BaseModel):
    id: int
    effective_from: date
    effective_to: Optional[date]
    source_url: str


class ProvisionResponse(BaseModel):
    id: int
    section_num: str
    text_et: str
    text_en: Optional[str]
    level: str
