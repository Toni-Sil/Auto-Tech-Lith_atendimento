"""
Knowledge Base Service — RAG (Retrieval Augmented Generation)

Each tenant can upload their business knowledge:
  - Product/service catalog
  - FAQ
  - Business policies
  - Pricing tables

The customer service agent queries this knowledge BEFORE
calling the LLM, grounding answers in tenant-specific context.

Architecture:
  Upload → Chunk → Embed (OpenAI) → Store (pgvector or in-memory fallback)
  Query  → Embed query → Find top-K chunks → Inject into LLM prompt
"""

import hashlib
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Chunk size in characters
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5  # Number of chunks to return per query
MIN_SIMILARITY = 0.72  # Minimum cosine similarity threshold


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for better retrieval coverage."""
    chunks = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return [c for c in chunks if len(c) > 50]  # Filter very short chunks


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure Python cosine similarity (no numpy dependency)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x ** 2 for x in a) ** 0.5
    norm_b = sum(x ** 2 for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class KnowledgeEntry:
    """In-memory representation of a knowledge chunk."""
    def __init__(self, tenant_id: int, doc_id: str, chunk_index: int, text: str, embedding: list[float], metadata: dict):
        self.tenant_id = tenant_id
        self.doc_id = doc_id
        self.chunk_index = chunk_index
        self.text = text
        self.embedding = embedding
        self.metadata = metadata
        self.created_at = datetime.utcnow()


class KnowledgeService:
    """
    Manages tenant knowledge bases with embedding-based retrieval.

    Storage strategy:
      - Primary: in-memory per-tenant index (fast, simple)
      - Future: pgvector extension for persistence across restarts
    """

    def __init__(self):
        # { tenant_id -> [KnowledgeEntry, ...] }
        self._index: dict[int, list[KnowledgeEntry]] = {}

    # ── Document ingestion ────────────────────────────────────────────

    async def ingest_document(
        self,
        tenant_id: int,
        content: str,
        doc_name: str,
        doc_type: str = "general",  # general | faq | pricing | policy | catalog
        replace_existing: bool = False,
    ) -> dict:
        """
        Chunk, embed and index a document for a tenant.
        Returns ingestion stats.
        """
        doc_id = hashlib.md5(f"{tenant_id}:{doc_name}".encode()).hexdigest()[:12]

        # Remove existing doc if replace requested
        if replace_existing:
            self._remove_document(tenant_id, doc_id)

        # Chunk
        chunks = _chunk_text(content)
        if not chunks:
            return {"status": "error", "detail": "Document produced no valid chunks"}

        # Embed all chunks
        embeddings = await self._embed_batch(chunks)
        if not embeddings:
            return {"status": "error", "detail": "Embedding service unavailable"}

        # Index
        if tenant_id not in self._index:
            self._index[tenant_id] = []

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            entry = KnowledgeEntry(
                tenant_id=tenant_id,
                doc_id=doc_id,
                chunk_index=i,
                text=chunk,
                embedding=emb,
                metadata={"doc_name": doc_name, "doc_type": doc_type},
            )
            self._index[tenant_id].append(entry)

        logger.info(
            f"[Knowledge] Tenant {tenant_id}: ingested '{doc_name}' "
            f"({len(chunks)} chunks, doc_id={doc_id})"
        )
        return {
            "status": "ok",
            "doc_id": doc_id,
            "doc_name": doc_name,
            "chunks_indexed": len(chunks),
            "tenant_id": tenant_id,
        }

    # ── Query ─────────────────────────────────────────────────────────

    async def query(
        self,
        tenant_id: int,
        question: str,
        top_k: int = TOP_K,
        doc_type_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Retrieve top-K relevant chunks for a tenant query.
        Returns list of {text, score, doc_name, doc_type}.
        """
        entries = self._index.get(tenant_id, [])
        if not entries:
            return []

        # Filter by doc type if requested
        if doc_type_filter:
            entries = [e for e in entries if e.metadata.get("doc_type") == doc_type_filter]

        # Embed query
        query_emb = await self._embed_single(question)
        if not query_emb:
            return []

        # Score all chunks
        scored = [
            {
                "text": entry.text,
                "score": _cosine_similarity(query_emb, entry.embedding),
                "doc_name": entry.metadata.get("doc_name"),
                "doc_type": entry.metadata.get("doc_type"),
                "chunk_index": entry.chunk_index,
            }
            for entry in entries
        ]

        # Filter by min similarity and return top-K
        results = sorted(
            [r for r in scored if r["score"] >= MIN_SIMILARITY],
            key=lambda x: x["score"],
            reverse=True,
        )[:top_k]

        return results

    async def build_context_prompt(
        self,
        tenant_id: int,
        question: str,
        doc_type_filter: Optional[str] = None,
    ) -> str:
        """
        Build a RAG context string to inject into the LLM prompt.
        Returns empty string if no relevant knowledge found.
        """
        results = await self.query(tenant_id, question, doc_type_filter=doc_type_filter)
        if not results:
            return ""

        context_parts = []
        for r in results:
            context_parts.append(
                f"[{r['doc_name']} | score: {r['score']:.2f}]\n{r['text']}"
            )

        return (
            "### Conhecimento da Empresa (use como referência para responder):\n"
            + "\n\n".join(context_parts)
            + "\n###"
        )

    # ── Management ────────────────────────────────────────────────────

    def list_documents(self, tenant_id: int) -> list[dict]:
        """List all indexed documents for a tenant."""
        entries = self._index.get(tenant_id, [])
        seen = {}
        for e in entries:
            if e.doc_id not in seen:
                seen[e.doc_id] = {
                    "doc_id": e.doc_id,
                    "doc_name": e.metadata.get("doc_name"),
                    "doc_type": e.metadata.get("doc_type"),
                    "chunks": 0,
                    "created_at": e.created_at.isoformat(),
                }
            seen[e.doc_id]["chunks"] += 1
        return list(seen.values())

    def remove_document(self, tenant_id: int, doc_id: str) -> int:
        """Remove all chunks for a specific document. Returns count removed."""
        return self._remove_document(tenant_id, doc_id)

    def get_stats(self, tenant_id: int) -> dict:
        """Return index stats for a tenant."""
        entries = self._index.get(tenant_id, [])
        doc_ids = {e.doc_id for e in entries}
        return {
            "tenant_id": tenant_id,
            "total_chunks": len(entries),
            "total_documents": len(doc_ids),
        }

    # ── Private ───────────────────────────────────────────────────────

    def _remove_document(self, tenant_id: int, doc_id: str) -> int:
        if tenant_id not in self._index:
            return 0
        before = len(self._index[tenant_id])
        self._index[tenant_id] = [
            e for e in self._index[tenant_id] if e.doc_id != doc_id
        ]
        return before - len(self._index[tenant_id])

    async def _embed_batch(self, texts: list[str]) -> Optional[list[list[float]]]:
        """Embed a batch of texts using OpenAI embeddings."""
        try:
            from openai import AsyncOpenAI
            from src.config import settings

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"[Knowledge] Embedding batch failed: {e}")
            return None

    async def _embed_single(self, text: str) -> Optional[list[float]]:
        """Embed a single query text."""
        results = await self._embed_batch([text])
        return results[0] if results else None


# Singleton
knowledge_service = KnowledgeService()
