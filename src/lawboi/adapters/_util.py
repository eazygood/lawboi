def build_provision_metadata(
    act_title: str, eli: str, section_num: str, act_version_id: int
) -> dict:
    return {
        "act_title": act_title,
        "eli": eli,
        "section_num": section_num,
        "act_version_id": act_version_id,
        "is_translation": False,
        "context": "",
    }
