from functools import lru_cache

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container, Container


@lru_cache
def get_container() -> Container:
    return build_container(Settings())


def get_retrieval():
    return get_container().retrieval


def get_answer():
    return get_container().answer


def get_store():
    return get_container().store
