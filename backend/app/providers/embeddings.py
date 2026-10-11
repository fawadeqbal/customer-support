"""Text -> vector providers."""
import numpy as np
import requests


class SentenceTransformerEmbeddings:
    """Local model, runs on the CPU (via LangChain's HuggingFace wrapper)."""

    def __init__(self, model):
        from langchain_huggingface import HuggingFaceEmbeddings
        self._model = HuggingFaceEmbeddings(model_name=model, encode_kwargs={"normalize_embeddings": True})
        self.name = f"sentence_transformers:{model}"

    def embed_documents(self, texts):
        return self._model.embed_documents(texts)

    def embed_query(self, text):
        return self._model.embed_query(text)


class OpenAICompatibleEmbeddings:
    """Any /embeddings endpoint: Ollama (e.g. nomic-embed-text), OpenAI, vLLM, ..."""

    def __init__(self, model, base_url, api_key="", batch_size=64, timeout=120, label="openai_compatible"):
        self.model = model
        self.url = base_url.rstrip("/") + "/embeddings"
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.batch_size = batch_size
        self.timeout = timeout
        self.name = f"{label}:{model}"

    def _embed(self, texts):
        out = []
        for i in range(0, len(texts), self.batch_size):
            r = requests.post(self.url, json={"model": self.model, "input": texts[i:i + self.batch_size]},
                              headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            rows = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
            for row in rows:
                v = np.asarray(row["embedding"], dtype=np.float32)
                out.append((v / (np.linalg.norm(v) or 1.0)).tolist())   # normalise for cosine search
        return out

    def embed_documents(self, texts):
        return self._embed(list(texts))

    def embed_query(self, text):
        return self._embed([text])[0]
