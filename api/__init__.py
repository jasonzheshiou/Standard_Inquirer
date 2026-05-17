"""TODO: FastAPI integration (Phase 2)

Endpoints to implement:
    - POST /analyze — receives a set of answers, returns gap report JSON
    - GET /standards/search?q=... — semantic search over standards in ChromaDB
    - POST /async_analyze — accepts uploaded documents, triggers LLM-powered analysis

Shared dependencies:
    - engine.gap_analyzer (analyze function)
    - standards_ingestion.embedder (ChromaDB client)
    - engine.questionnaire (question loading)

Not yet implemented. This directory is a placeholder for future REST API.
"""
