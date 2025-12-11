# FILE: src/tools/rag_store.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings
import numpy as np


@dataclass
class ChromaStoreConfig:
    """Configuration for Chroma persistent collection."""

    persist_dir: Path
    collection_name: str = "manual"


class ChromaStore:
    """Thin wrapper around a Chroma persistent collection."""

    def __init__(self, config: ChromaStoreConfig):
        self.config = config
        self.config.persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self.config.persist_dir),
            settings=ChromaSettings(allow_reset=True),
        )
        self._col = self._client.get_or_create_collection(
            name=self.config.collection_name
        )

    def add(self, ids: List[str], texts: List[str], embs: np.ndarray) -> None:
        """Add new documents and embeddings to the collection."""
        if not (len(ids) == len(texts) == len(embs)):
            raise ValueError("ids, texts and embs must have the same length.")
        self._col.add(
            ids=ids,
            documents=texts,
            embeddings=embs.tolist(),
        )

    def query_by_embedding(
        self,
        query_emb: np.ndarray,
        k: int = 5,
    ) -> Tuple[List[str], List[float], List[str], List[Dict[str, Any]]]:
        """Query top-k documents for a given embedding."""
        res = self._col.query(
            query_embeddings=[query_emb.tolist()],
            n_results=k,
        )

        docs = res.get("documents", [[]])[0]
        dists = res.get("distances", [[]])[0]
        ids = res.get("ids", [[]])[0]
        metas = res.get("metadatas", [[]])[0] or [{}] * len(docs)

        if not dists:
            return [], [], [], []

        maxd = max(dists) or 1.0
        scores = [1.0 - (d / maxd) for d in dists]

        return docs, scores, ids, metas

    def count(self) -> int:
        """Return number of records in the collection."""
        return self._col.count()
