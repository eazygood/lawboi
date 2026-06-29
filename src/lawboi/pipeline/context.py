from dataclasses import dataclass, field
from datetime import date

_PROCEDURAL_TERMS = "vaidlustamine tähtaeg kaebus kohus hüvitis õiguskaitsevahend"


@dataclass
class RetrievalConfig:
    limit: int = 5
    procedural_terms: str = _PROCEDURAL_TERMS
    step_back_enabled: bool = True


@dataclass
class RetrievalContext:
    query: str
    as_of: date
    candidates: list[dict] = field(default_factory=list)
    config: RetrievalConfig = field(default_factory=RetrievalConfig)
    done: bool = False
    _seen: set[int] = field(default_factory=set)

    def add(self, provision: dict) -> None:
        pid = provision["provision_id"]
        if pid not in self._seen:
            self._seen.add(pid)
            self.candidates.append(provision)

    def add_all(self, provisions: list[dict]) -> None:
        for p in provisions:
            self.add(p)
