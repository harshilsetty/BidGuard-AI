"""
Vector storage adapter supporting ChromaDB and in-memory fallback.
"""

from typing import List, Dict, Any, Optional
import os


class VectorStoreManager:
    """
    Manages vector collections for tender requirements and bidder evidence.
    """

    def __init__(self, collection_name: str = "gem_procurement_chunks", host: Optional[str] = None):
        self.collection_name = collection_name
        self.host = host or os.getenv("CHROMA_HOST", "localhost")
        self.client = None
        self.collection = None
        self._initialize()

    def _initialize(self):
        try:
            import chromadb
            if self.host in ["localhost", "127.0.0.1"]:
                self.client = chromadb.Client()
            else:
                port = int(os.getenv("CHROMA_PORT", 8000))
                self.client = chromadb.HttpClient(host=self.host, port=port)
            self.collection = self.client.get_or_create_collection(self.collection_name)
        except Exception:
            # Fallback for environments where ChromaDB daemon is not yet booted
            self.client = None
            self.collection = None

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        if self.collection:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def query(self, query_text: str, n_results: int = 3) -> Dict[str, Any]:
        if self.collection:
            return self.collection.query(query_texts=[query_text], n_results=n_results)
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
