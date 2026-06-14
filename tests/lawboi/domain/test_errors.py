import pytest
from lawboi.domain.errors import (
    LawboiError, NoSourcesFoundError, UnsupportedModelError,
    NoModelConfiguredError, SourceFetchError, ParseError,
)


def test_all_inherit_base():
    for exc in (NoSourcesFoundError, UnsupportedModelError, NoModelConfiguredError,
                SourceFetchError, ParseError):
        assert issubclass(exc, LawboiError)


def test_unsupported_model_carries_name():
    err = UnsupportedModelError("gpt-5")
    assert "gpt-5" in str(err)


def test_raisable():
    with pytest.raises(NoSourcesFoundError):
        raise NoSourcesFoundError("no provisions")
