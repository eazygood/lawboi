from datetime import date, timedelta
from typing import Optional

from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct, RetrievedProvision


class FakeLLMProvider:
    name = "fake"

    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = list(responses or ["FAKE ANSWER"])
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class InMemoryVectorStore:
    def __init__(self):
        self._embeddings: dict[int, list[float]] = {}

    def upsert(self, provision_id: int, embedding: list[float]) -> None:
        self._embeddings[provision_id] = embedding

    def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]:
        return [
            VectorHit(provision_id=pid, section_num="", text="", metadata={})
            for pid in list(self._embeddings.keys())[:n_results]
        ]

    def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None:
        for pid, emb in pairs:
            self._embeddings[pid] = emb


class InMemoryStructuredStore:
    def __init__(self):
        self._acts: dict[str, int] = {}
        self._act_objs: dict[str, Act] = {}
        self._versions: dict[int, ActVersion] = {}
        # maps (act_id, effective_from) -> version_id for idempotency
        self._version_keys: dict[tuple, int] = {}
        self._provisions: list[Provision] = []
        self._next = 1

    def _id(self):
        n = self._next
        self._next += 1
        return n

    def upsert_act(self, act: Act) -> int:
        if act.eli not in self._acts:
            self._acts[act.eli] = self._id()
        act.id = self._acts[act.eli]
        self._act_objs[act.eli] = act
        return self._acts[act.eli]

    def upsert_act_version(self, version: ActVersion) -> int:
        # Idempotent on (act_id, effective_from), mirroring the real Postgres upsert.
        key = (version.act_id, version.effective_from)
        if key in self._version_keys:
            return self._version_keys[key]
        vid = self._id()
        version.id = vid
        self._versions[vid] = version
        self._version_keys[key] = vid
        # Close prior open versions of the same act, mirroring the Postgres upsert.
        for v in self._versions.values():
            if (v.id != vid and v.act_id == version.act_id
                    and v.effective_to is None
                    and v.effective_from < version.effective_from):
                v.effective_to = version.effective_from - timedelta(days=1)
        return vid

    def ingested_global_ids(self) -> set[int]:
        return {v.source_global_id for v in self._versions.values()
                if v.source_global_id is not None}

    def insert_provision(self, provision: Provision) -> int:
        pid = self._id()
        provision.id = pid
        self._provisions.append(provision)
        return pid

    def version_has_provisions(self, act_version_id: int) -> bool:
        return any(p.act_version_id == act_version_id for p in self._provisions)

    def _to_rp(self, p: Provision) -> RetrievedProvision:
        return RetrievedProvision(
            provision_id=p.id, section_num=p.section_num, text=p.text_et,
            metadata={"section_num": p.section_num, "act_version_id": p.act_version_id,
                      "is_translation": False, "context": ""},
        )

    def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]:
        terms = query.lower().split()
        return [self._to_rp(p) for p in self._provisions
                if any(t in p.text_et.lower() for t in terms)]

    def exact_lookup(self, section_num, as_of, limit, eli, title_query):
        return [self._to_rp(p) for p in self._provisions
                if p.section_num == section_num][:limit]

    def get_act(self, eli: str) -> Optional[Act]:
        return self._act_objs.get(eli)

    def list_act_versions(self, eli: str) -> list[ActVersion]:
        act_id = self._acts.get(eli)
        versions = [v for v in self._versions.values() if v.act_id == act_id]
        return sorted(versions, key=lambda v: v.effective_from, reverse=True)

    def provisions_as_of(self, eli: str, on: date) -> list[Provision]:
        act_id = self._acts.get(eli)
        version_ids = {
            vid for vid, v in self._versions.items()
            if v.act_id == act_id
            and v.effective_from <= on
            and (v.effective_to is None or v.effective_to >= on)
        }
        return [p for p in self._provisions if p.act_version_id in version_ids]


class FakeLawSource:
    def __init__(self, acts: list[ActMeta], raw: dict[int, RawAct]):
        self._acts = acts
        self._raw = raw

    def search(self, query: str, limit: int = 10) -> list[ActMeta]:
        return self._acts[:limit]

    def fetch(self, global_id: int) -> RawAct:
        return self._raw[global_id]

    def iter_corpus(self, doc_types=(), page_size: int = 200):
        yield from self._acts
