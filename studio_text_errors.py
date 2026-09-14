"""Provider-neutral text generation/pricing error contract."""


class TextGenerationError(RuntimeError):
    pass


__all__ = ["TextGenerationError"]
