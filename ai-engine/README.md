# AI Engine — BidGuard (SIH26100)

The `ai-engine` module houses the intelligence extraction, vector indexing, retrieval-augmented generation (RAG), and semantic matching components of BidGuard.

## Core Architectural Principle: Hybrid Deterministic AI

```
Tender PDF ──> PyMuPDF / OCR ──> Requirement Extractor ──┐
                                                         ├──> Semantic Matcher + Deterministic Rule Engine ──> Structured Output
Bidder Docs ──> PyMuPDF / OCR ──> Evidence Extractor ────┘     (Hybrid Decision Support)                       (PASS / FAIL / REVIEW)
```

1. **Extraction**: LLMs and PyMuPDF convert unstructured tender and bidder PDFs into typed requirements and evidence snippets.
2. **Retrieval (RAG)**: ChromaDB indexes chunks with dense vector embeddings to locate exact supporting bidder clauses.
3. **Matching**: Semantic matching calculates similarity, but **deterministic rules** govern objective compliance thresholds (e.g., turnover numbers, date validity, debarment status).
4. **Output Contract**: All AI output must conform strictly to Pydantic schemas returning JSON with explicit page citations. Uncontrolled, free-form text output is rejected.

## Directory Structure

```
ai-engine/
├── extractors/
│   ├── pdf_extractor.py          # PyMuPDF parser with OCR fallback
│   ├── requirement_extractor.py  # Structured clause extraction from tender
│   └── evidence_extractor.py     # Certificate & credential extraction from bidder docs
├── rag/
│   ├── vector_store.py           # ChromaDB / pgvector collection manager
│   └── retriever.py              # Semantic similarity retriever
├── matcher/
│   ├── semantic_matcher.py       # LLM semantic matching prompt & schema
│   └── rule_validator.py         # Deterministic validation rules (dates, thresholds)
├── schemas.py                    # AI Output JSON contracts (PASS, FAIL, REVIEW)
└── requirements.txt              # Isolated AI dependencies
```

## AI Output Contract

Every compliance match must adhere to:

```json
{
  "requirement": "Bidder must possess minimum 3 years experience in similar works.",
  "evidence": "Work completion certificate dated 12-04-2021 showing 4 years continuous execution.",
  "source_document": "experience_certificate_2021.pdf",
  "page": 5,
  "status": "PASS",
  "confidence": 0.94,
  "reason": "Document confirms 4 years experience which satisfies the >= 3 years requirement."
}
```
