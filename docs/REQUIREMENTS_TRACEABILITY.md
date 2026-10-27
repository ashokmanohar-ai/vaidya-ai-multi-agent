# Vaidya AI — requirements-to-delivery traceability

Status: **synthetic leadership MVP**. Functionality omitted here is not silently counted as complete.

| PRD requirement | Demo evidence/status |
|---|---|
| FR-1 multiple voice notes | Implemented adapters: microphone/upload, up to five ordered audio notes; live ASR requires Sarvam V4 key and opt-in or optional local Whisper dependencies/model |
| FR-2 multiple images | Done: up to 5 JPEG/PNG uploaded and embedded |
| FR-3 report type selection | Partial: fixed Histopathology MVP |
| FR-4 concat transcripts | Implemented: per-note ordered ASR results and original transcripts stored |
| FR-5 translation | Implemented: separate Bedrock translation stage, opt-in; passthrough clearly labeled |
| FR-6 configurable languages | Partial |
| FR-7 translation quality history | Partial |
| FR-8 joint content+instruction extraction | Done via demo rules; optional Bedrock provider unvalidated |
| FR-9 formatting instruction not printed as clinical text | Done in DOCX; only supported bold instruction applied, others require review |
| FR-10 conditional formatting | Partial, no full conditions engine |
| FR-11 doctor identity | Demo role login |
| FR-12 doctor-to-many-hospitals | Not implemented: one demo hospital |
| FR-13 patient linkage | Done |
| FR-14 template resolution | Partial: single template |
| FR-15 hospital/doctor branding | Partial: demo hospital branding, no override rules |
| FR-16 doctor preferences | Partial: versioned skills store, not dynamically applied |
| FR-17 contextual image placement | Partial: images grouped in reference section rather than semantic placement |
| FR-18 complete job history | Partial: original+translated transcripts, uploaded media references, stage traces, checkpoint IDs, provider usage, drafts/finals |
| FR-19 diff classification | Partial: rule-based signature/specimen/general differences |
| FR-20 pattern threshold | Done: 5 distinct jobs required |
| FR-21 learning confidence | Partial: evidence count, no calibrated confidence |
| FR-22 admin approval | Done: no auto-activation |
| FR-23 skill versioning | Implemented: approved skills loaded for extraction/rendering, version pinned per new job; audited admin rollback creates new immutable version |

Major architecture departures: Flask HTML instead of React PWA, SQLite local instead of Supabase, opt-in Bedrock models with deterministic offline demo fallback only by configuration, LangGraph example rather than full orchestrator deployment.

**Leadership position:** operational workflow demonstration, not original PRD implementation completion.
