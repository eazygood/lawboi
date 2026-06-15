from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RetrievedProvision:
    provision_id: int
    section_num: str
    text: str
    metadata: dict = field(default_factory=dict)


# VectorHit is the vector-store's view of a result; structurally identical to
# RetrievedProvision but kept distinct so the port contract is explicit.
@dataclass
class VectorHit:
    provision_id: int
    section_num: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ActMeta:
    global_id: int
    title: str
    effective_from: Optional[date]
    effective_to: Optional[date]
    # Populated by the corpus crawl; left None on plain search results.
    tervik_id: Optional[int] = None  # stable act identity (across versions)
    liik: Optional[str] = None       # document type: seadus | määrus
    lyhend: Optional[str] = None     # abbreviation, when the act has one
    modified: Optional[int] = None   # `muudetud` epoch-millis change signal


@dataclass
class RawAct:
    global_id: int
    xml: bytes
    source_url: str
