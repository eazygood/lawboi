def build_provision_metadata(
    act_title: str, eli: str, section_num: str, act_version_id: int,
    source_global_id: "int | None" = None, heading: "str | None" = None,
) -> dict:
    return {
        "act_title": act_title,
        "eli": eli,
        "section_num": section_num,
        "act_version_id": act_version_id,
        "source_global_id": source_global_id,
        "is_translation": False,
        "context": "",
        "heading": heading or "",
    }
