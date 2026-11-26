# BIDGUARD AI — EMBEDDING RE-INDEXING MIGRATION PLAN
**Target Model**: `nvidia/nemotron-3.5-embed-1b` (`2048` dimensions, asymmetric `input_type="passage"` / `"query"`)  
**Status**: Planned (Do NOT execute in Phase 1.0.2)

---

## 1. Objective & Rationale

Historical `document_chunks.embedding` vectors in BidGuard AI may have been generated using:
- `stub-deterministic-2048` (hash-based pseudo-embeddings during development/testing), or
- `nvidia/nemotron-3-embed-1b` (prior model version), or
- `nvidia/nemotron-3.5-embed-1b` without explicit `input_type="passage"`.

Even though all of these produce 2048-dimensional vectors, **cosine similarity across different embedding models or missing `input_type` parameters is mathematically invalid**. Mixing vector spaces degrades evidence retrieval accuracy.

---

## 2. Existing Vector Inventory (Pre-Migration Check)

Before executing re-indexing, run a read-only inventory query against PostgreSQL / SQLite:
```sql
SELECT
    COALESCE(embedding_model, 'UNKNOWN_LEGACY') AS model_identity,
    COUNT(*) AS chunk_count,
    COUNT(embedding) AS populated_vectors
FROM document_chunks
GROUP BY COALESCE(embedding_model, 'UNKNOWN_LEGACY');
```

---

## 3. Source Document Availability Verification

Verify that all referenced `bid_documents.file_path` PDFs exist on disk (or object storage) if chunk reconstruction is needed, OR verify `document_chunks.content` is intact:
- Note: `document_chunks.content` already stores the exact page-aware chunk text (`chunk_index`, `page_number`, `start_char`, `end_char`, `extraction_method`, `ocr_confidence`).
- Re-embedding directly from `document_chunks.content` preserves exact chunk IDs (`compliance_evaluations.evidence_chunk_id`) and page provenance without breaking existing audit references.

---

## 4. Chunk Reconstruction vs. In-Place Vector Replacement

- **Preferred Strategy (In-Place Staged Vector Replacement)**:
  - Keep existing `document_chunks.id`, `content`, `page_number`, `start_char`, `end_char` intact so `compliance_evaluations.evidence_chunk_id` foreign/string references remain 100% valid.
  - Add temporary staging columns (`embedding_v2 vector(2048)`, `embedding_model_v2 varchar(100)`) or update rows where `embedding_model IS DISTINCT FROM 'nvidia/nemotron-3.5-embed-1b'` in batches.

---

## 5. New Embedding Generation Procedure

1. **Preconditions**:
   - `ENVIRONMENT=production`
   - `NVIDIA_API_KEY` configured and verified against `https://integrate.api.nvidia.com/v1`
   - `NVIDIA_EMBEDDING_MODEL=nvidia/nemotron-3.5-embed-1b`
   - `EMBEDDING_DIM=2048`
2. **Batch Processing**:
   - Query `document_chunks` ordered by `id` in batches of 16 (`batch_size=16`).
   - Call `NvidiaEmbeddingProvider.embed_texts(batch_texts)` which enforces `extra_body={"input_type": "passage"}`.
   - Validate every returned vector has `len(vec) == 2048` and non-zero L2 norm before staging.
   - Rate-limit / exponential backoff on transient HTTP 429/5xx errors.
   - Write `embedding_v2 = vec` and `embedding_model_v2 = 'nvidia/nemotron-3.5-embed-1b'`.

---

## 6. Transactional Swap & Validation

1. Verify 100% coverage:
   ```sql
   SELECT COUNT(*) FROM document_chunks WHERE embedding_v2 IS NULL;
   ```
   Must equal `0`.
2. Within a single PostgreSQL transaction:
   - Swap `embedding` <- `embedding_v2` and `embedding_model` <- `embedding_model_v2`.
   - Rebuild `pgvector` HNSW/IVFFlat index (`REINDEX INDEX CONCURRENTLY ...` if present).
3. Run retrieval smoke checks using `embed_query(..., input_type="query")` on known clauses and verify top-k cosine similarity > threshold.

---

## 7. Rollback Plan

- Retain `embedding_backup` (or snapshot via `pg_dump` prior to swap) for 7 days.
- If retrieval regressions are detected post-swap, restore `embedding` and `embedding_model` from backup in a single transaction and drop staging columns.

---

## 8. Downtime Implications

- **Zero-downtime staging**: Generating `embedding_v2` runs online in the background without locking reads.
- **Swap window**: < 1 second metadata/column swap (or brief write-lock during `ALTER TABLE` / batch `UPDATE`).
- **Golden Demo Preservation**: Do not re-evaluate historical `compliance_evaluations` automatically during vector migration unless explicitly authorized.
