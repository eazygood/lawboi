from functools import lru_cache

from lawboi.config.settings import load_settings
from lawboi.config.composition import build_container, Container


@lru_cache
def get_container() -> Container:
    return build_container(load_settings())


def get_retrieval():
    return get_container().retrieval


def get_answer():
    return get_container().answer


def get_store():
    return get_container().store
