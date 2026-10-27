# VAIDYA AI — 7-minute full multi-agent leadership demonstration

**Appropriate framing:** A working **synthetic-data LangGraph architecture prototype** — not clinically validated medical software. The packaged LangGraph implementation MUST pass `python scripts/validate_complete.py` on the presentation laptop before being called live-validated.

| Time | Demonstration | What is actually happening |
|---|---|---|
| 0:00–1:00 | Open doctor dashboard | Protected Flask session, existing synthetic fixtures |
| 1:00–2:00 | New report → Load synthetic sample → Generate | Real orchestrator authorizes request and invokes Pathology Agent subgraph (rules-based extraction by default) |
| 2:00–3:00 | DOCX download and execution trace | Pathology nodes produce draft; SQLite LangGraph checkpoint holds a **pending doctor interrupt** |
| 3:00–4:00 | Doctor adds signature and approves | Human sign-off stored in DB, LangGraph resumes from the interrupted Pathology node |
| 4:00–5:00 | Admin sees learner corrections | Learner subgraph analyses doctor-approved synthetic corrections; historical seeded evidence supports signature pattern |
| 5:00–6:00 | Admin presses Approve (if status suggested) | Administrator response resumes persisted Learner interrupt; skill v1 → v2, approval audited |
| 6:00–7:00 | Explain Bedrock adapter and future roadmap | Real model calling is opt-in and **not part of this default demo**; Whisper/translations, cloud worker and clinical evaluation are pending |

Important: The original historical five-report fixture is synthetic and was pre-seeded outside LangGraph. Present the **new report**'s trace as proof of LangGraph execution, not the history fixture. Reset any deferred/rejected suggestion by moving the synthetic-only `instance` directory to a timestamped backup while Flask is stopped.

On Windows, use port 5055:

```powershell
$env:PORT="5055"
python scripts\preflight.py
python scripts\validate_complete.py
python scripts\run_demo.py
```

For a leader who asks whether the application is clinically usable: **No.** It is a transparent engineering demo with required human approval, but does not validate medical content or handle real patient data.
