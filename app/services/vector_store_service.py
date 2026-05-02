from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from app.config import settings
from app.services.embedding_service import EmbeddingService


class VectorStoreService:
    """Manages ChromaDB collection for RAG chunks."""

    def __init__(self) -> None:
        # Persistent ChromaDB directory inside storage
        self.persist_dir = settings.storage_dir / "chroma"
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="omniscribe_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self.embedding_service = EmbeddingService()

    def _generate_chunk_id(self, source_label: str, chunk_index: int) -> str:
        # Use a deterministic but unique ID based on source and index
        return f"{source_label}::{chunk_index}"

    def add_chunks(
        self, chunks: list[tuple[str, str, str]]  # (chunk_text, source_label, kind)
    ) -> None:
        """
        Add or update chunks in the vector store.
        Each chunk is a tuple: (text, source_label, kind).
        """
        if not chunks:
            return
        
        print(f"\n[VectorStore] Adding {len(chunks)} chunks to index:")


        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        # Simple approach: delete existing chunks with same source_label? For MVP,
        # we just add new and rely on checking duplicates by ID.
        # Better: we can delete all chunks belonging to a source before re-adding.
        # For incremental updates, we will receive only new chunks from the caller.
        for i, (text, source_label, kind) in enumerate(chunks):
            chunk_id = self._generate_chunk_id(source_label, i)
            ids.append(chunk_id)
            texts.append(text)
            metadatas.append({"source_label": source_label, "kind": kind})

        # Compute embeddings
        embeddings = self.embedding_service.embed_documents(texts)

        # Upsert
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def delete_by_source(self, source_label: str) -> None:
        """Remove all chunks belonging to a specific source (e.g., 'Transcript - ...')."""
        # ChromaDB does not support efficient delete by metadata directly,
        # but we can iterate over IDs? For MVP, we skip deletion; we will rebuild
        # the whole index on startup, or we can tolerate duplicates.
        # More robust: when updating a transcript, we can query for ids containing
        # the source_label and delete them. For simplicity, we will delete the whole
        # collection and rebuild on startup. This is acceptable for small data.
        pass

    def similarity_search(
        self, query: str, top_k: int = 6
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return list of (chunk_text, metadata) sorted by relevance."""
        query_embedding = self.embedding_service.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        # Flatten results
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        # distances = results.get("distances", [[]])[0]

        return [(doc, meta) for doc, meta in zip(documents, metadatas)]

    def clear_collection(self) -> None:
        """Drop and recreate the collection – used when rebuilding the entire index."""
        self.client.delete_collection("omniscribe_chunks")
        self.collection = self.client.create_collection(
            name="omniscribe_chunks",
            metadata={"hnsw:space": "cosine"},
        )
