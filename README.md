# BRD Interpretation Pipeline (PO + QA Critique Loop)

A lean FastAPI service that scaffolds a controlled BRD interpretation flow:

1. BRD ingestion
2. Product Owner agent framing (PDP contract)
3. QA validation and critique (TDP contract)
4. traceability enforcement
5. mandatory human approval gate
6. Jira action preview (backend-only execution)

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Key endpoints

- `POST /ingest`
- `GET /prompts/po`
- `GET /prompts/qa`
- `POST /critique-loop`
- `POST /approve-sync`
- `GET /health`

## Guardrails

- BRD is source of truth.
- Missing source evidence should be marked `INSUFFICIENT SOURCE EVIDENCE` by agents.
- Jira writes are blocked unless human approval is true and traceability checks pass.
