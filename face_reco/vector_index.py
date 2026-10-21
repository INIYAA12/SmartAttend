"""
Face-embedding vector index.

Exact cosine-similarity search over L2-normalised embeddings, with two
interchangeable backends:
  - "faiss": FAISS IndexFlatIP -- scales to very large galleries
  - "numpy": one matrix-vector product -- zero extra dependencies, plenty
             fast for classroom/school-sized galleries
"auto" picks FAISS when it's installed, otherwise NumPy. The gallery is
saved as a plain .npz (embeddings + labels), never a pickle, and the
search structure is rebuilt on load.
"""

import numpy as np

try:  # optional dependency
    import faiss
except Exception:  # pragma: no cover - depends on the environment
    faiss = None


def faiss_available():
    return faiss is not None


def _normalize(x):
    x = np.asarray(x, dtype="float32")
    if x.ndim == 1:
        x = x[None, :]
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return np.ascontiguousarray(x / norms)


class VectorIndex:
    def __init__(self, backend="auto"):
        if backend == "faiss" and faiss is None:
            raise RuntimeError("VECTOR_BACKEND=faiss but faiss isn't installed (pip install faiss-cpu).")
        if backend not in ("auto", "faiss", "numpy"):
            raise ValueError(f"Unknown vector backend: {backend}")
        self.backend = "faiss" if (backend == "faiss" or (backend == "auto" and faiss is not None)) else "numpy"
        self.labels = []
        self.embeddings = None
        self._index = None

    def build(self, embeddings, labels):
        emb = _normalize(embeddings)
        if len(emb) != len(labels):
            raise ValueError("embeddings and labels must have the same length")
        self.embeddings = emb
        self.labels = list(labels)
        if self.backend == "faiss":
            self._index = faiss.IndexFlatIP(emb.shape[1])
            self._index.add(emb)
        return self

    def __len__(self):
        return len(self.labels)

    def search(self, vector):
        """Returns (label, cosine_similarity) of the single nearest gallery entry."""
        if not self.labels:
            raise ValueError("Index is empty")
        q = _normalize(vector)
        if self.backend == "faiss":
            sims, idx = self._index.search(q, 1)
            return self.labels[int(idx[0][0])], float(sims[0][0])
        sims = self.embeddings @ q[0]
        i = int(np.argmax(sims))
        return self.labels[i], float(sims[i])

    def save(self, path):
        np.savez_compressed(path, embeddings=self.embeddings, labels=np.array(self.labels, dtype=str))

    @classmethod
    def load(cls, path, backend="auto"):
        with np.load(path, allow_pickle=False) as data:
            return cls(backend).build(data["embeddings"], [str(x) for x in data["labels"]])
