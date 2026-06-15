from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Act:
    id: Optional[int]
    eli: str
    title_et: str
    title_en: Optional[str]
    domain: str
    act_type: str


@dataclass
class ActVersion:
    id: Optional[int]
    act_id: int
    effective_from: date
    effective_to: Optional[date]
    source_url: str
    source_hash: str
    source_global_id: Optional[int] = None


@dataclass
class Provision:
    id: Optional[int]
    act_version_id: int
    section_num: str
    level: str  # part | chapter | section | subsection | clause
    text_et: str
    text_en: Optional[str] = None
    parent_id: Optional[int] = None


@dataclass
class Chunk:
    provision_id: int
    act_version_id: int
    section_num: str
    text: str
    metadata: dict
