# FILE: src/tools/rag_tool.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer

from tools.rag_store import ChromaStore, ChromaStoreConfig


@dataclass
class RagToolConfig:
    """Config for RAG search based on Chroma + SentenceTransformer."""

    chroma_dir: Path
    collection_name: str = "manual"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


class RagTool:
    """
    Deterministic RAG search tool.

    Assumptions:
      - Documents have already been ingested into Chroma by tools.ingest_manuals
      - We only embed the query here and run similarity search
    """

    def __init__(self, config: RagToolConfig):
        self.config = config
        self.config.chroma_dir.mkdir(parents=True, exist_ok=True)

        print(
            f"[RagTool] Initializing. chroma_dir={self.config.chroma_dir}, "
            f"collection={self.config.collection_name}, "
            f"model={self.config.embedding_model}"
        )

        self._store = ChromaStore(
            ChromaStoreConfig(
                persist_dir=self.config.chroma_dir,
                collection_name=self.config.collection_name,
            )
        )

        # Use CPU to avoid unexpected GPU/MPS issues on macOS
        self._embed_model = SentenceTransformer(
            self.config.embedding_model,
            device="cpu",
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Embed the query and search the Chroma collection."""
        print(f"[RagTool] search() called. query={query!r}, top_k={top_k}")

        q_emb = self._embed_model.encode([query], convert_to_numpy=True)[0]
        docs, scores, ids, metadatas = self._store.query_by_embedding(
            np.array(q_emb),
            k=top_k,
        )

        results: List[Dict[str, Any]] = []
        for text, score, doc_id, meta in zip(docs, scores, ids, metadatas):
            results.append(
                {
                    "id": doc_id,
                    "text": text,
                    "score": float(score),
                    "metadata": meta or {},
                }
            )

        print(f"[RagTool] search() returning {len(results)} hits.")
        return {"status": "ok", "results": results}
