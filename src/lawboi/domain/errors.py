class LawboiError(Exception):
    """Base for all domain errors."""


class NoSourcesFoundError(LawboiError):
    """Retrieval returned no provisions; an answer must not be produced."""


class UnsupportedModelError(LawboiError):
    def __init__(self, model: str):
        super().__init__(f"Unsupported model: {model}")
        self.model = model


class NoModelConfiguredError(LawboiError):
    """No LLM provider key is configured in the environment."""


class SourceFetchError(LawboiError):
    """A law source failed to fetch or search."""


class ContentBlockedError(LawboiError):
    """Input failed the content-safety moderation check."""


class ParseError(LawboiError):
    """Source content could not be parsed into provisions."""
