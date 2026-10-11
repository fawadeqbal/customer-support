"""Re-scoring of (question, passage) pairs after the first search."""


class CrossEncoderReranker:
    """Local cross-encoder: reads question and passage together, more accurate than vectors alone."""

    def __init__(self, model):
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(model)
        self.name = f"cross_encoder:{model}"

    def score(self, query, passages):
        if len(passages) < 2:
            return None
        return [float(s) for s in self._model.predict([(query, p) for p in passages])]


class NoReranker:
    name = "none"

    def score(self, query, passages):
        return None
