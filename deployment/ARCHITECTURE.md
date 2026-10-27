# Vaidya AI production-engineering architecture

```mermaid
flowchart TD
  DOCTOR[Clinician portal] --> FLASK[Authenticated Flask API]
  FLASK --> RBAC[Hospital-scoped RBAC + CSRF]
  RBAC --> RDS[(PostgreSQL: jobs + audit + work queue)]
  RBAC --> S3[(S3 SSE-KMS artifacts)]
  RDS --> WORKER[Durable worker with expiring leases]
  WORKER --> LG[LangGraph parent Orchestrator]
  LG --> PATH[Pathology subgraph]
  LG --> LEARN[Learner subgraph]
  PATH --> ASR[CPU faster-whisper in worker]
  PATH --> TRANS[Bedrock translation when configured]
  PATH --> LLM[Bedrock model-agnostic extraction]
  PATH --> DOCX[Deterministic DOCX + S3]
  LG <--> CP[(PostgresSaver checkpoints)]
  PATH --> GATE[Doctor review interrupt]
  GATE --> DOCTOR
  LEARN --> ADMIN[Admin learning approval interrupt]
  ADMIN --> LG
```

In the new code, `production_app.py` serves the authenticated Flask interface, `production.worker` executes work outside the request, and `production.graph.ProductionGraph` compiles one parent graph with Pathology/Learner subgraphs and PostgresSaver. The original `app.py` remains a synthetic local-demo program. Do not deploy both under the same URL without explicit routing/isolation.

Production reports use versioned S3 references and stored SHA-256 checksums. Stage memory carries references instead of raw patient content; model prompts are transient. Clinical data may be stored in protected checkpoint data structures by framework internals, so checkpoint retention and DB encryption remain mandatory.
