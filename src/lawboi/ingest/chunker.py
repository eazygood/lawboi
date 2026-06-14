from lawboi.domain.models import Provision, Chunk


def chunk_provisions(
    provisions: list[Provision],
    act_title: str,
    eli: str,
) -> list[Chunk]:
    """Create one Chunk per provision, with ±1 neighbour as context."""
    chunks = []
    for i, provision in enumerate(provisions):
        neighbours = []
        if i > 0:
            neighbours.append(provisions[i - 1].text_et)
        if i < len(provisions) - 1:
            neighbours.append(provisions[i + 1].text_et)

        context = "\n\n".join(neighbours)

        chunk = Chunk(
            provision_id=provision.id,
            act_version_id=provision.act_version_id,
            section_num=provision.section_num,
            text=provision.text_et,
            metadata={
                "act_title": act_title,
                "eli": eli,
                "section_num": provision.section_num,
                "level": provision.level,
                "act_version_id": provision.act_version_id,
                "context": context,
                "is_translation": False,
            },
        )
        chunks.append(chunk)

    return chunks
