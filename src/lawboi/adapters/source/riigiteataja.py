from datetime import date
from typing import Iterable, Iterator, Optional

from lawboi.domain.dto import ActMeta, RawAct
from lawboi.domain.errors import SourceFetchError
from lawboi.adapters.source.riigiteataja_client import (
    CORPUS_DOC_TYPES, search_acts, fetch_act_xml, iter_corpus,
)


def _to_date(v: Optional[str]) -> Optional[date]:
    return date.fromisoformat(v) if v else None


def _to_meta(m: dict) -> ActMeta:
    k = m.get("kehtivus", {})
    return ActMeta(
        global_id=m["globaalID"],
        title=m.get("pealkiri", str(m["globaalID"])),
        effective_from=_to_date(k.get("algus")),
        effective_to=_to_date(k.get("lopp")),
        tervik_id=m.get("terviktekstID"),
        liik=m.get("liik"),
        lyhend=m.get("lyhend") or None,
        modified=m.get("muudetud"),
    )


class RiigiTeatajaSource:
    def search(self, query: str, limit: int = 10) -> list[ActMeta]:
        try:
            raw = search_acts(query, limit=limit)
        except Exception as e:
            raise SourceFetchError(f"search failed: {e}") from e
        return [_to_meta(m) for m in raw]

    def iter_corpus(
        self, doc_types: Iterable[str] = CORPUS_DOC_TYPES, page_size: int = 200
    ) -> Iterator[ActMeta]:
        try:
            for m in iter_corpus(doc_types, page_size=page_size):
                yield _to_meta(m)
        except Exception as e:
            raise SourceFetchError(f"corpus crawl failed: {e}") from e

    def fetch(self, global_id: int) -> RawAct:
        try:
            xml_bytes, source_url = fetch_act_xml(str(global_id))
        except Exception as e:
            raise SourceFetchError(f"fetch failed for {global_id}: {e}") from e
        return RawAct(global_id=global_id, xml=xml_bytes, source_url=source_url)
