"""
Knowledge Base API — Tenant document management endpoints

POST /api/v1/knowledge/ingest    — Upload text content to knowledge base
GET  /api/v1/knowledge/docs      — List indexed documents
DELETE /api/v1/knowledge/{doc_id} — Remove a document
POST /api/v1/knowledge/query     — Test a query against the knowledge base
GET  /api/v1/knowledge/stats     — Index statistics
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from src.middleware.tenant_context import get_current_tenant_id
from src.services.knowledge_service import knowledge_service

knowledge_router = APIRouter()


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=10, description="Text content to index")
    doc_name: str = Field(..., min_length=1, description="Document name/identifier")
    doc_type: str = Field(
        "general",
        description="Type: general | faq | pricing | policy | catalog"
    )
    replace_existing: bool = Field(
        False,
        description="Replace existing document with same name"
    )


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(5, ge=1, le=20)
    doc_type_filter: Optional[str] = None


@knowledge_router.post("/ingest", summary="Ingest document into knowledge base")
async def ingest_document(
    body: IngestRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Upload and index a document for the tenant's knowledge base."""
    result = await knowledge_service.ingest_document(
        tenant_id=tenant_id,
        content=body.content,
        doc_name=body.doc_name,
        doc_type=body.doc_type,
        replace_existing=body.replace_existing,
    )
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return result


@knowledge_router.get("/docs", summary="List knowledge base documents")
async def list_documents(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """List all indexed documents for this tenant."""
    return {
        "tenant_id": tenant_id,
        "documents": knowledge_service.list_documents(tenant_id),
    }


@knowledge_router.delete("/{doc_id}", summary="Remove a document")
async def remove_document(
    doc_id: str,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Remove all chunks of a document from the knowledge base."""
    removed = knowledge_service.remove_document(tenant_id, doc_id)
    return {"status": "ok", "chunks_removed": removed, "doc_id": doc_id}


@knowledge_router.post("/query", summary="Test a query against knowledge base")
async def query_knowledge(
    body: QueryRequest,
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Test retrieval — useful for verifying knowledge base quality."""
    results = await knowledge_service.query(
        tenant_id=tenant_id,
        question=body.question,
        top_k=body.top_k,
        doc_type_filter=body.doc_type_filter,
    )
    return {"question": body.question, "results": results, "count": len(results)}


@knowledge_router.get("/stats", summary="Knowledge base statistics")
async def get_stats(
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Return index statistics for this tenant."""
    return knowledge_service.get_stats(tenant_id)
