from datetime import date, timedelta
from typing import Optional, TypeVar

from pydantic import BaseModel

from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct, RetrievedProvision

Model = TypeVar("Model", bound=BaseModel)


class FakeLLMProvider:
    name = "fake"

    def __init__(self, responses: Optional[list[str]] = None,
                 structured_response: Optional[BaseModel] = None):
        self._responses = list(responses or ["FAKE ANSWER"])
        self._structured_response = structured_response
        self.calls: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    async def complete_structured(self, prompt: str, output_cls: type[Model]) -> Model:
        self.calls.append(prompt)
        return self._structured_response  # type: ignore[return-value]


class InMemoryAnswerCache:
    def __init__(self):
        self._rows: list[tuple] = []
        self.find_calls = 0
        self.store_calls = 0

    async def find(self, embedding, as_of):
        self.find_calls += 1
        for emb, row_as_of, payload in self._rows:
            if row_as_of == as_of and emb == embedding:
                return payload
        return None

    async def store(self, embedding, as_of, query_text, cache_key_text, answer_payload):
        self.store_calls += 1
        self._rows.append((embedding, as_of, answer_payload))

    async def clear(self):
        self._rows = []


class InMemoryVectorStore:
    def __init__(self):
        self._embeddings: dict[int, list[float]] = {}

    async def upsert(self, provision_id: int, embedding: list[float]) -> None:
        self._embeddings[provision_id] = embedding

    async def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]:
        return [
            VectorHit(provision_id=pid, section_num="", text="", metadata={})
            for pid in list(self._embeddings.keys())[:n_results]
        ]

    async def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None:
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
        self._conversations: set[int] = set()
        self._messages: list[dict] = []
        self._next = 1

    def _id(self):
        n = self._next
        self._next += 1
        return n

    async def upsert_act(self, act: Act) -> int:
        if act.eli not in self._acts:
            self._acts[act.eli] = self._id()
        act.id = self._acts[act.eli]
        self._act_objs[act.eli] = act
        return self._acts[act.eli]

    async def upsert_act_version(self, version: ActVersion) -> int:
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

    async def ingested_global_ids(self) -> set[int]:
        indexed_version_ids = {p.act_version_id for p in self._provisions}
        return {v.source_global_id for v in self._versions.values()
                if v.source_global_id is not None and v.id in indexed_version_ids}

    async def insert_provision(self, provision: Provision) -> int:
        pid = self._id()
        provision.id = pid
        self._provisions.append(provision)
        return pid

    async def version_fully_indexed(self, act_version_id: int) -> bool:
        # This fake has no notion of embeddings (InMemoryVectorStore is a
        # separate object), so "fully indexed" here means "has provisions" —
        # the embedding-aware half of this check only exists in PostgresStore.
        return any(p.act_version_id == act_version_id for p in self._provisions)

    async def delete_provisions_for_version(self, act_version_id: int) -> None:
        self._provisions = [p for p in self._provisions
                            if p.act_version_id != act_version_id]

    def _to_rp(self, p: Provision) -> RetrievedProvision:
        assert p.id is not None  # already inserted, so always set on stored provisions
        return RetrievedProvision(
            provision_id=p.id, section_num=p.section_num, text=p.text_et,
            metadata={"section_num": p.section_num, "act_version_id": p.act_version_id,
                      "is_translation": False, "context": ""},
        )

    async def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]:
        terms = query.lower().split()
        return [self._to_rp(p) for p in self._provisions
                if any(t in p.text_et.lower() for t in terms)]

    async def exact_lookup(self, section_num, as_of, limit, eli, title_query):
        return [self._to_rp(p) for p in self._provisions
                if p.section_num == section_num][:limit]

    async def get_act(self, eli: str) -> Optional[Act]:
        return self._act_objs.get(eli)

    async def list_act_versions(self, eli: str) -> list[ActVersion]:
        act_id = self._acts.get(eli)
        versions = [v for v in self._versions.values() if v.act_id == act_id]
        return sorted(versions, key=lambda v: v.effective_from, reverse=True)

    async def provisions_as_of(self, eli: str, on: date) -> list[Provision]:
        act_id = self._acts.get(eli)
        version_ids = {
            vid for vid, v in self._versions.items()
            if v.act_id == act_id
            and v.effective_from <= on
            and (v.effective_to is None or v.effective_to >= on)
        }
        return [p for p in self._provisions if p.act_version_id in version_ids]

    async def create_conversation(self) -> int:
        cid = self._id()
        self._conversations.add(cid)
        return cid

    async def append_message(self, conversation_id: int, role: str, content: str) -> None:
        self._messages.append(
            {"conversation_id": conversation_id, "role": role, "content": content})

    async def recent_messages(self, conversation_id: int, limit: int = 10) -> list[dict]:
        msgs = [m for m in self._messages if m["conversation_id"] == conversation_id]
        return [{"role": m["role"], "content": m["content"]} for m in msgs[-limit:]]


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
