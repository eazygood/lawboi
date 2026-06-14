import io
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional

from lawboi.domain.models import Provision

TAGS = {
    "section": "paragrahv",
    "section_num": "paragrahvNr",
    "subsection": "loige",
    "clause": "punkt",
    "subclause": "alampunkt",
    "part": "jagu",
    "chapter": "peatykk",
    "text": "sisuTekst",
    "title": "pealkiri",
}


def _parse_xml(xml_bytes: bytes) -> ET.Element:
    it = ET.iterparse(io.BytesIO(xml_bytes))
    for _, el in it:
        _, _, el.tag = el.tag.rpartition("}")
    return it.root


def _extract_text(element: ET.Element) -> str:
    parts = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        parts.append(_extract_text(child))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _section_num(el: ET.Element) -> str:
    nr_el = el.find(TAGS["section_num"])
    if nr_el is not None and nr_el.text:
        return nr_el.text.strip()
    return el.get("nr") or el.get("id", "").replace("para", "")


def _parse_section(
    el: ET.Element,
    act_version_id: int,
    parent_id: Optional[int],
    results: list[Provision],
) -> None:
    section_num = _section_num(el)
    text_parts = []
    for child in el:
        if child.tag in (TAGS["subsection"], TAGS["text"]):
            text_parts.append(_extract_text(child))
        elif child.tag == TAGS["clause"]:
            text_parts.append(_extract_text(child))

    text_et = "\n".join(text_parts).strip()
    if not text_et:
        text_et = _extract_text(el).strip()

    if text_et and section_num:
        results.append(Provision(
            id=None,
            act_version_id=act_version_id,
            section_num=section_num,
            level="section",
            text_et=text_et,
            text_en=None,
            parent_id=parent_id,
        ))


def _parse_effective_date(xml_bytes: bytes) -> tuple[Optional[date], Optional[date]]:
    root = _parse_xml(xml_bytes)
    meta = root.find("metaandmed")
    if meta is None:
        return None, None
    kehtivus = meta.find("kehtivus")
    if kehtivus is None:
        return None, None

    def _date(el: Optional[ET.Element]) -> Optional[date]:
        if el is None or not el.text:
            return None
        try:
            return datetime.fromisoformat(el.text[:10]).date()
        except ValueError:
            return None

    effective_from = _date(kehtivus.find("kehtivuseAlgus"))
    effective_to = _date(kehtivus.find("kehtivuseLopp"))
    return effective_from, effective_to


def parse_act_title(xml_bytes: bytes) -> str:
    root = _parse_xml(xml_bytes)
    el = root.find(".//pealkiri")
    return el.text.strip() if el is not None and el.text else ""


def parse_act_xml(
    xml_bytes: bytes,
    act_version_id: int,
    effective_from: date,
    effective_to: Optional[date],
) -> list[Provision]:
    root = _parse_xml(xml_bytes)
    results: list[Provision] = []

    sisu = root.find("sisu")
    if sisu is None:
        sisu = root

    # sisu > jagu > peatykk > paragrahv
    for part_el in sisu.findall(TAGS["part"]):
        for chapter_el in part_el.findall(TAGS["chapter"]):
            for section_el in chapter_el.findall(TAGS["section"]):
                _parse_section(section_el, act_version_id, None, results)
        for section_el in part_el.findall(TAGS["section"]):
            _parse_section(section_el, act_version_id, None, results)

    # sisu > peatykk > paragrahv
    for chapter_el in sisu.findall(TAGS["chapter"]):
        for section_el in chapter_el.findall(TAGS["section"]):
            _parse_section(section_el, act_version_id, None, results)

    # sisu > paragrahv
    for section_el in sisu.findall(TAGS["section"]):
        _parse_section(section_el, act_version_id, None, results)

    return results
