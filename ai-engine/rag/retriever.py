"""
Retrieves top candidate evidence chunks matching specific tender requirements.
"""

from typing import List, Dict, Any
from .vector_store import VectorStoreManager


class EvidenceRetriever:
    def __init__(self, vector_store: VectorStoreManager):
        self.vector_store = vector_store

    def retrieve_relevant_evidence(self, requirement_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        results = self.vector_store.query(requirement_text, n_results=top_k)
        candidates = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0] if "distances" in results else [0.0] * len(docs)

            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) else {}
                candidates.append({
                    "evidence_text": doc,
                    "metadata": meta,
                    "score": 1.0 - (distances[i] if i < len(distances) else 0.0)
                })
        return candidates
