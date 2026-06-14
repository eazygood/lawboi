from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-large"


def _to_list(arr):
    return arr.tolist() if hasattr(arr, "tolist") else arr


class Embedder:
    def __init__(self):
        self._model = SentenceTransformer(MODEL_NAME)

    def embed_query(self, text: str) -> list[float]:
        return _to_list(self._model.encode(f"query: {text}"))

    def embed_passage(self, text: str) -> list[float]:
        return _to_list(self._model.encode(f"passage: {text}"))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts]
        return _to_list(self._model.encode(prefixed))
