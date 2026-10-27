"""Vaidya AI LangGraph orchestration for a SYNTHETIC local leadership demonstration.

One durable parent StateGraph, with two real compiled specialist subgraphs:
  * Pathology Agent: intake -> model extraction -> validation -> DOCX + job persistence
  * Learner Agent: diff -> aggregate, OR interrupt -> human decision -> version skills

Checkpoint records are persisted in a distinct SQLite database. Clinical report
approval is an authenticated Flask operation; no graph may approve a medical report.
Neither the graph nor an LLM can access unrestricted external tools.
"""
from __future__ import annotations

import json
import os
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import TypedDict, Any

from .database import Database, utcnow
from .learning import record_learning
from .providers import get_provider
from .reports import report_text, render_docx
from .audio import transcriber
from .translation import translator
from .fidelity import clinical_fidelity_warnings
from .clinical_review import assess_report
from .audio_patient import attach_patient_candidate


class VaidyaState(TypedDict, total=False):
    workflow_type: str
    workflow_id: str
    job_id: str
    actor_id: int
    doctor_id: int
    hospital_id: int
    patient_id: int
    specialty: str
    transcript: str
    original_transcript: str
    translated_transcript: str
    audio_refs: list[str]
    language_config: str
    transcript_segments: list[dict]
    detected_languages: list[str]
    asr_model: str
    asr_provider: str
    asr_mode: str
    asr_job_ids: list[str]
    audio_sha256: list[str]
    transcript_sha256: str
    skills_version: int
    approved_skills: str
    translation_provider: str
    translation_model: str
    image_refs: list[str]
    stage: str
    provider: str
    model: str
    findings: list[dict]
    instructions: list[dict]
    review_flags: list[str]
    assessment: dict
    draft_text: str
    draft_filename: str
    learning_id: int
    learning_outcome: dict
    approval_response: dict
    doctor_approval: dict
    decision: str
    status: str
    error: str


def add_event(db: Database, workflow_id: str, job_id: str, agent: str, stage: str, status: str = 'completed') -> None:
    """Record stage transitions once, even if nodes replay after a checkpoint resume."""
    db.execute(
        'INSERT OR IGNORE INTO workflow_events(workflow_id,job_id,agent,stage,status,created_at) VALUES(?,?,?,?,?,?)',
        (workflow_id, job_id, agent, stage, status, utcnow()),
    )


class GraphRuntime:
    """Owns a compiled LangGraph and its on-disk SqliteSaver for one application instance."""

    def __init__(self, db: Database, storage_path: Path):
        # Fail explicitly if optional graph dependencies were not installed.
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import StateGraph, START, END
        from langgraph.types import interrupt

        self.db = db
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.storage_path / 'langgraph_checkpoints.sqlite3'
        self.connection = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False, timeout=30)
        self.checkpointer = SqliteSaver(self.connection)
        self._invoke_lock = threading.RLock()  # Serializes demo-only synchronous execution.
        db.init()

        def route_request(state: VaidyaState):
            kind = state.get('workflow_type')
            if kind not in ('generate', 'analyze', 'learning_review'):
                raise ValueError('Unsupported workflow type')
            if state.get('specialty', 'pathology') != 'pathology':
                raise ValueError('Only pathology is enabled in this pilot')
            if kind == 'generate':
                doctor = db.query('SELECT id,role,hospital_id FROM users WHERE id=?', (state.get('doctor_id'),), one=True)
                if not doctor or doctor['role'] != 'doctor' or doctor['hospital_id'] != state.get('hospital_id'):
                    raise PermissionError('Doctor or hospital is not authorized')
                if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true':
                    if state.get('patient_id') is not None:
                        raise PermissionError('Audio-only mode does not accept a preselected patient')
                else:
                    patient = db.query('SELECT id,hospital_id FROM patients WHERE id=?',(state.get('patient_id'),),one=True)
                    if not patient or doctor['hospital_id'] != patient['hospital_id']:
                        raise PermissionError('Doctor/hospital/patient isolation check failed')
                if not state.get('job_id'):
                    raise ValueError('Job ID required')
                if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true':
                    if state.get('transcript','').strip() or not state.get('audio_refs'):
                        raise ValueError('Audio-only mode requires uploaded audio and disallows typed/source sample transcripts')
                elif not (str(state.get('transcript','')).strip() or state.get('audio_refs')):
                    raise ValueError('Transcript or audio required')
            if kind == 'analyze':
                job = db.query('SELECT id,status FROM jobs WHERE id=?',(state.get('job_id'),),one=True)
                if not job or job['status'] != 'approved':
                    raise PermissionError('Learner requires an approved doctor report')
            if kind == 'learning_review':
                suggestion = db.query('SELECT id,status,supporting_jobs FROM learnings WHERE id=?',
                                      (state.get('learning_id'),),one=True)
                if not suggestion or suggestion['status'] != 'suggested' or suggestion['supporting_jobs'] < 5:
                    raise PermissionError('Learning is not eligible for human approval')
            add_event(db, state['workflow_id'], str(state.get('job_id') or state.get('learning_id')), 'orchestrator', 'authorization_and_routing')
            return {'stage':'authorized'}

        # --- Pathology specialist, invoked as a true LangGraph subgraph. ---
        def intake(state: VaidyaState):
            transcript = state.get('transcript','').strip()
            if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true' and transcript:
                raise ValueError('Typed dictation is disabled for audio-only mode')
            if len(transcript)>16000 or (not transcript and not state.get('audio_refs')):
                raise ValueError('A synthetic transcript or voice note is required (max 16000 chars)')
            if state.get('language_config','ta-en') not in ('ta-en','en','ta'):
                raise ValueError('Unsupported language configuration')
            audio=[]
            for ref in state.get('audio_refs',[]):
                path=Path(ref).resolve()
                allowed=(self.storage_path/'audio').resolve()
                if allowed not in path.parents or not path.is_file():
                    raise PermissionError('Unrecognized private audio reference')
                audio.append(str(path))
            if len(audio)>5:raise ValueError('Too many audio notes')
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','validate_intake')
            return {'stage':'intake_validated','transcript':transcript,'audio_refs':audio}

        def transcribe_node(state: VaidyaState):
            audio=state.get('audio_refs',[])
            text=state.get('transcript','').strip()
            if not audio:
                if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true':
                    raise ValueError('No uploaded audio: transcription cannot proceed')
                add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','transcribe_voice_notes','skipped')
                return {'original_transcript':text,'transcript_segments':[],
                        'detected_languages':[],'asr_model':'typed-transcript',
                        'stage':'transcribed'}
            source_language={'ta':'ta','en':'en'}.get(state.get('language_config', 'ta-en'))
            answer=transcriber().transcribe(audio, language=source_language)
            if not answer.text.strip():
                raise ValueError('ASR produced no words; no placeholder or typed fallback allowed')
            if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true' and text:
                raise ValueError('Cannot combine typed text with audio transcription')
            combined = answer.text.strip() if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true' else ' '.join(filter(None,[text,answer.text])).strip()
            if len(combined)>16000:raise ValueError('Combined transcript too long')
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','transcribe_voice_notes')
            return {'original_transcript':combined,'transcript_segments':answer.segments,
                    'detected_languages':answer.detected_languages,'asr_model':answer.model,
                    'asr_provider':answer.provider,'asr_mode':answer.mode,'asr_job_ids':answer.job_ids,
                    'audio_sha256':answer.audio_sha256,'transcript_sha256':hashlib.sha256(combined.encode('utf-8')).hexdigest(),
                    'review_flags':state.get('review_flags', []) + [
                      'Audio ASR is unverified. Compare source recording with names, dates, numeric findings, clinical negations and Tamil instructions before approval.'
                    ], 'stage':'transcribed'}

        def resolve_patient_from_audio(state: VaidyaState):
            """Link a per-report *unverified* ASR identity, only after successful STT.

            Technical AUDIO-UUID is an internal tracking key, NOT a dictated biopsy ID.
            Missing demographics remain null or empty; never seed fictitious values.
            """
            if os.getenv('AUDIO_ONLY_MODE','').lower() != 'true':
                return {'stage':'patient_context_retained'}
            transcript = str(state.get('original_transcript') or '').strip()
            if not transcript or not state.get('audio_sha256'):
                raise ValueError('Cannot create an audio-derived patient without a real ASR result')
            patient_id = attach_patient_candidate(
                db, job_id=state['job_id'], hospital_id=state['hospital_id'],
                transcript=transcript, audio_hashes=state['audio_sha256'])
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','attach_audio_patient_candidate')
            return {'patient_id':patient_id,'stage':'patient_candidate_from_asr'}

        def translate_node(state: VaidyaState):
            result=translator().translate(state['original_transcript'],state.get('language_config','ta-en'))
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','translate_voice_notes',
                      'skipped' if result.provider=='passthrough' else 'completed')
            # Translation and source evidence are retained separately; use the
            # translated text for extraction but never overwrite the original.
            return {'translated_transcript':result.text,'transcript':result.text,
                    'translation_provider':result.provider,'translation_model':result.model,
                    'review_flags':state.get('review_flags', []) + result.warnings,'stage':'translated'}

        def extract(state: VaidyaState):
            active=db.query('SELECT version,content FROM skills ORDER BY version DESC LIMIT 1',one=True)
            approved_skills=active['content'] if active else ''
            skills_version=active['version'] if active else 1
            response = get_provider().extract(state['translated_transcript'],approved_skills=approved_skills)
            # Persist only safe invocation metadata; never log transcripts or tokens.
            if response.provider == 'aws-bedrock':
                usage = response.usage or {}
                db.execute('''INSERT OR IGNORE INTO llm_calls(
                    workflow_id,job_id,provider,model,latency_ms,input_tokens,
                    output_tokens,total_tokens,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (state['workflow_id'],state['job_id'],response.provider,response.model,
                     response.latency_ms,usage.get('inputTokens'),usage.get('outputTokens'),
                     usage.get('totalTokens'),utcnow()))
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','extract_structured_fields')
            return {'findings':response.findings,'instructions':response.instructions,
                    'review_flags':state.get('review_flags',[])+response.review_flags,'provider':response.provider,
                    'model':response.model,'skills_version':skills_version,
                    'approved_skills':approved_skills,'stage':'extracted'}

        def validate(state: VaidyaState):
            findings=state.get('findings')
            instructions=state.get('instructions')
            review_flags=state.get('review_flags')
            if not isinstance(findings,list) or not isinstance(instructions,list) or not isinstance(review_flags,list):
                raise ValueError('Provider response does not match expected extraction schema')
            if len(findings)>80 or len(instructions)>30 or not all(isinstance(x,dict) and isinstance(x.get('text'),str) for x in findings):
                raise ValueError('Invalid clinical findings')
            fidelity=clinical_fidelity_warnings(state['original_transcript'],findings,state['translated_transcript'])
            review_flags=list(review_flags)+fidelity
            patient=db.query('SELECT * FROM patients WHERE id=? AND hospital_id=?',
                             (state['patient_id'],state['hospital_id']),one=True)
            if not patient:
                raise PermissionError('Patient context changed before assessment')
            assessment=assess_report(patient,state['original_transcript'],findings,instructions,
                                     audio_present=bool(state.get('audio_refs')))
            review_flags=list(dict.fromkeys(review_flags + assessment['review_warnings'] + assessment['blocking_issues']))
            draft_text=report_text(findings,instructions,review_flags,assessment=assessment)
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','validate_source_and_schema')
            return {'draft_text':draft_text,'review_flags':review_flags,'assessment':assessment,'stage':'validated'}

        def render_and_persist(state: VaidyaState):
            job_id=state['job_id']
            existing=db.query('SELECT id,status FROM jobs WHERE id=?',(job_id,),one=True)
            if existing:
                if existing['status'] in ('draft_ready','approved'):
                    add_event(db,state['workflow_id'],job_id,'pathology_agent','render_and_persist')
                    return {'draft_filename':f'{job_id}.docx','status':existing['status'],'stage':'persisted'}
                raise RuntimeError('A conflicting report job already exists')
            patient=db.query('SELECT * FROM patients WHERE id=? AND hospital_id=?',
                             (state['patient_id'],state['hospital_id']),one=True)
            hospital=db.query('SELECT * FROM hospitals WHERE id=?',(state['hospital_id'],),one=True)
            if not patient or not hospital:
                raise PermissionError('Report context changed during execution')
            name=f'{job_id}.docx'
            output=self.storage_path/'reports'/name
            image_refs=[]
            for ref in state.get('image_refs',[]):
                path=Path(ref).resolve()
                allowed=(self.storage_path/'uploads').resolve()
                if allowed not in path.parents or not path.is_file():
                    raise PermissionError('Unrecognized private image reference')
                image_refs.append(str(path))
            render_docx({'id':job_id},patient,hospital,state['findings'],state['instructions'],
                        state['review_flags'],image_refs,output,approved_skills=state.get('approved_skills',''),
                        assessment=state.get('assessment'))
            try:
                db.execute('''INSERT INTO jobs(id,patient_id,doctor_id,hospital_id,report_type,
                  original_transcript,translated_transcript,findings_json,instruction_json,draft_text,
                  draft_filename,image_json,provider,model,status,created_at,skills_version,validation_json)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (job_id,state['patient_id'],state['doctor_id'],state['hospital_id'],'histopathology',
                   state['original_transcript'],state['translated_transcript'],json.dumps(state['findings']),
                   json.dumps(state['instructions']),state['draft_text'],name,json.dumps(image_refs),
                   state['provider'],state['model'],'draft_ready',utcnow(),state.get('skills_version',1),
                   json.dumps(state.get('assessment',{}),ensure_ascii=False)))
            except sqlite3.IntegrityError:
                if not db.query('SELECT id FROM jobs WHERE id=?',(job_id,),one=True):raise
            # Preserve original ordered note metadata, without embedding audio
            # binary content in LangGraph checkpoints or database records.
            with db.connect() as conn:
                for index, filename in enumerate(state.get('audio_refs',[])):
                    conn.execute('INSERT OR IGNORE INTO job_inputs(job_id,seq,kind,private_ref,metadata_json) '
                                 'VALUES(?,?,?,?,?)',
                                 (job_id,index,'audio',filename,json.dumps({'asr_model':state.get('asr_model'),
                                      'asr_provider':state.get('asr_provider'),
                                      'asr_mode':state.get('asr_mode'),
                                      'audio_sha256':state.get('audio_sha256',[])[index] if index < len(state.get('audio_sha256',[])) else None,
                                      'transcript_sha256':state.get('transcript_sha256'),
                                      'sarvam_job_id':state.get('asr_job_ids',[])[index] if index<len(state.get('asr_job_ids',[])) else None,
                                      'language':state.get('detected_languages',[])[index] if index<len(state.get('detected_languages',[])) else None})))
                for index, filename in enumerate(image_refs):
                    conn.execute('INSERT OR IGNORE INTO job_inputs(job_id,seq,kind,private_ref,metadata_json) '
                                 'VALUES(?,?,?,?,?)',(job_id,index,'image',filename,'{}'))
                conn.execute('INSERT OR IGNORE INTO job_inputs(job_id,seq,kind,private_ref,metadata_json) '
                             'VALUES(?,?,?,?,?)',(job_id,0,'translation',None,
                                json.dumps({'provider':state.get('translation_provider'),
                                            'model':state.get('translation_model'),
                                            'language_config':state.get('language_config')})))
            add_event(db,state['workflow_id'],job_id,'pathology_agent','render_and_persist')
            return {'draft_filename':name,'status':'draft_ready','stage':'awaiting_doctor_review'}

        def await_doctor(state: VaidyaState):
            # Processing is checkpointed and paused; do not automatically approve a report.
            reply=interrupt({'type':'doctor_report_review','job_id':state['job_id'],
                             'message':'Doctor must inspect and attest to the final report.'})
            if not isinstance(reply,dict) or reply.get('approved') is not True:
                raise PermissionError('Doctor approval required')
            return {'doctor_approval':reply,'stage':'doctor_approval_received'}

        def verify_doctor_approval(state: VaidyaState):
            reply=state['doctor_approval']
            j=db.query('SELECT id,status,doctor_id,approved_by,final_text FROM jobs WHERE id=?',
                       (state['job_id'],),one=True)
            if not j or j['status']!='approved' or j['doctor_id']!=reply.get('doctor_id') or j['approved_by']!=reply.get('doctor_id') or not j['final_text']:
                raise PermissionError('Doctor approval record not verified')
            add_event(db,state['workflow_id'],state['job_id'],'pathology_agent','verify_doctor_approval')
            return {'status':'approved','stage':'doctor_review_completed'}

        # Register doctor-review nodes only after their callbacks exist.
        pathology=StateGraph(VaidyaState)
        pathology.add_node('validate_intake',intake)
        pathology.add_node('transcribe_voice_notes',transcribe_node)
        pathology.add_node('attach_audio_patient_candidate',resolve_patient_from_audio)
        pathology.add_node('translate_voice_notes',translate_node)
        pathology.add_node('extract_structured_fields',extract)
        pathology.add_node('validate_output',validate)
        pathology.add_node('render_and_persist',render_and_persist)
        pathology.add_node('doctor_review_interrupt',await_doctor)
        pathology.add_node('verify_doctor_approval',verify_doctor_approval)
        pathology.add_edge(START,'validate_intake')
        pathology.add_edge('validate_intake','transcribe_voice_notes')
        pathology.add_edge('transcribe_voice_notes','attach_audio_patient_candidate')
        pathology.add_edge('attach_audio_patient_candidate','translate_voice_notes')
        pathology.add_edge('translate_voice_notes','extract_structured_fields')
        pathology.add_edge('extract_structured_fields','validate_output')
        pathology.add_edge('validate_output','render_and_persist')
        pathology.add_edge('render_and_persist','doctor_review_interrupt')
        pathology.add_edge('doctor_review_interrupt','verify_doctor_approval')
        pathology.add_edge('verify_doctor_approval',END)
        self.pathology_graph=pathology.compile()

        # --- Learner specialist: approved report evidence OR human review. ---
        def load_final(state: VaidyaState):
            j=db.query('SELECT id,status,draft_text,final_text FROM jobs WHERE id=?',(state['job_id'],),one=True)
            if not j or j['status']!='approved' or not j['final_text']:
                raise PermissionError('No authenticated doctor-approved final report exists')
            add_event(db,state['workflow_id'],state['job_id'],'learner_agent','load_approved_report')
            return {'stage':'approved_evidence_loaded'}

        def compare_and_aggregate(state: VaidyaState):
            job=db.query('SELECT * FROM jobs WHERE id=?',(state['job_id'],),one=True)
            evidence=record_learning(db,job['id'],job['draft_text'],job['final_text'])
            add_event(db,state['workflow_id'],state['job_id'],'learner_agent','compare_and_aggregate')
            return {'learning_outcome':evidence or {},'stage':'learning_analyzed','status':'analyzed'}

        def await_human(state: VaidyaState):
            # No writes before interrupt(). The node is intentionally replay-safe.
            answer=interrupt({'type':'administrator_skill_approval','learning_id':state['learning_id'],
                              'message':'Review documented evidence before any skill promotion.'})
            if not isinstance(answer,dict) or answer.get('decision') not in ('approved','rejected','deferred'):
                raise ValueError('Invalid administrator decision')
            return {'approval_response':answer,'stage':'approval_received'}

        def apply_decision(state: VaidyaState):
            answer=state['approval_response']
            actor_id=answer.get('actor_id')
            actor=db.query('SELECT id,role FROM users WHERE id=?',(actor_id,),one=True)
            if not actor or actor['role']!='admin':
                raise PermissionError('Only an authorized administrator may approve learning')
            learning_id=state['learning_id']
            decision=answer['decision']
            with db.connect() as conn:
                item=conn.execute('SELECT * FROM learnings WHERE id=?',(learning_id,)).fetchone()
                if not item or item['status']!='suggested':
                    raise ValueError('Learning candidate was already decided or is not approvable')
                if decision=='approved':
                    count=conn.execute('SELECT COUNT(DISTINCT job_id) FROM job_diffs WHERE pattern_key=?',(item['pattern_key'],)).fetchone()[0]
                    if count<5 or item['supporting_jobs']<5:
                        raise PermissionError('Five independent verified jobs are required')
                updated=conn.execute('UPDATE learnings SET status=?,decided_at=?,decided_by=? WHERE id=? AND status=?',
                         (decision,utcnow(),actor_id,learning_id,'suggested')).rowcount
                if updated!=1:raise ValueError('Learning candidate changed during review')
                if decision=='approved':
                    previous=conn.execute('SELECT version,content FROM skills ORDER BY version DESC LIMIT 1').fetchone()
                    conn.execute('INSERT INTO skills(version,content,learning_id,approved_by,created_at) VALUES(?,?,?,?,?)',
                      (previous['version']+1,previous['content']+'\nAPPROVED: '+item['description'],learning_id,actor_id,utcnow()))
            add_event(db,state['workflow_id'],str(learning_id),'learner_agent','apply_administrator_decision')
            db.audit(actor_id,'learning_'+decision,'learning',learning_id)
            return {'decision':decision,'status':'decision_recorded','stage':'skills_governed'}

        learner=StateGraph(VaidyaState)
        learner.add_node('load_approved_report',load_final)
        learner.add_node('compare_and_aggregate',compare_and_aggregate)
        learner.add_node('administrator_interrupt',await_human)
        learner.add_node('apply_administrator_decision',apply_decision)
        def select_learning_action(state: VaidyaState):
            return 'administrator_interrupt' if state['workflow_type']=='learning_review' else 'load_approved_report'
        learner.add_node('learner_dispatch',lambda state: {'stage':'learner_dispatched'})
        learner.add_edge(START,'learner_dispatch')
        learner.add_conditional_edges('learner_dispatch',select_learning_action,{
            'administrator_interrupt':'administrator_interrupt',
            'load_approved_report':'load_approved_report'})
        learner.add_edge('load_approved_report','compare_and_aggregate')
        learner.add_edge('compare_and_aggregate',END)
        learner.add_edge('administrator_interrupt','apply_administrator_decision')
        learner.add_edge('apply_administrator_decision',END)
        self.learner_graph=learner.compile()

        orchestrator=StateGraph(VaidyaState)
        orchestrator.add_node('authorize_and_route',route_request)
        orchestrator.add_node('pathology_agent',self.pathology_graph)
        orchestrator.add_node('learner_agent',self.learner_graph)
        orchestrator.add_edge(START,'authorize_and_route')
        orchestrator.add_conditional_edges('authorize_and_route',
            lambda s:'pathology_agent' if s['workflow_type']=='generate' else 'learner_agent',
            {'pathology_agent':'pathology_agent','learner_agent':'learner_agent'})
        orchestrator.add_edge('pathology_agent',END)
        orchestrator.add_edge('learner_agent',END)
        self.graph=orchestrator.compile(checkpointer=self.checkpointer)

    @staticmethod
    def config(thread_id: str):
        return {'configurable':{'thread_id':thread_id},'recursion_limit':30}

    def generate(self, *, job_id: str, doctor_id: int, patient_id: int | None, hospital_id: int,
                 transcript: str='', images: list[str]|None=None, audio: list[str]|None=None, language_config: str='ta-en') -> dict:
        thread=f'vaidya:report:{job_id}'
        with self._invoke_lock:
            result=self.graph.invoke({'workflow_type':'generate','workflow_id':thread,
              'specialty':'pathology','job_id':job_id,'doctor_id':doctor_id,'actor_id':doctor_id,
              'patient_id':patient_id,'hospital_id':hospital_id,'transcript':transcript,
              'image_refs':images or [],'audio_refs':audio or [],'language_config':language_config},config=self.config(thread))
        job=self.db.query('SELECT status FROM jobs WHERE id=?',(job_id,),one=True)
        if not job or job['status'] not in ('draft_ready','approved'):
            raise RuntimeError('Report graph did not produce a reviewable draft')
        snapshot=self.graph.get_state(self.config(thread))
        if not snapshot or not snapshot.next:
            raise RuntimeError('Report graph did not checkpoint its doctor review interruption')
        add_event(self.db,thread,job_id,'pathology_agent','doctor_review_interrupt','waiting')
        return {'status':'draft_ready','stage':'awaiting_doctor_review','job_id':job_id}

    def complete_doctor_review(self, job_id: str, doctor_id: int) -> dict:
        """Resume the durable Pathology subgraph only after verified Flask approval."""
        from langgraph.types import Command
        job=self.db.query('SELECT status,doctor_id,approved_by FROM jobs WHERE id=?',(job_id,),one=True)
        if not job or job['status']!='approved' or job['approved_by']!=doctor_id or job['doctor_id']!=doctor_id:
            raise PermissionError('Doctor report approval must be recorded before graph resumption')
        thread=f'vaidya:report:{job_id}'
        with self._invoke_lock:
            snapshot=self.graph.get_state(self.config(thread))
            if snapshot and not snapshot.next and snapshot.values.get('stage')=='doctor_review_completed':
                return snapshot.values
            if not snapshot or not snapshot.next:
                raise RuntimeError('Missing persisted doctor review checkpoint')
            result=self.graph.invoke(Command(resume={'approved':True,'doctor_id':doctor_id}),
                                     config=self.config(thread))
        if result.get('status')!='approved':
            raise RuntimeError('Doctor approval graph did not complete')
        return result

    def analyze(self, job_id: str) -> dict:
        thread=f'vaidya:learning:{job_id}'
        with self._invoke_lock:
            return self.graph.invoke({'workflow_type':'analyze','specialty':'pathology',
                        'workflow_id':thread,'job_id':job_id},config=self.config(thread))

    def prepare_learning_review(self, learning_id: int):
        """Create or reuse a persisted, human-interrupted approval thread."""
        thread=f'vaidya:approval:{learning_id}'
        config=self.config(thread)
        with self._invoke_lock:
            snapshot=self.graph.get_state(config)
            if snapshot and snapshot.next:
                return snapshot
            if snapshot and snapshot.values and snapshot.values.get('status')=='decision_recorded':
                return snapshot
            self.graph.invoke({'workflow_type':'learning_review','specialty':'pathology',
                               'workflow_id':thread,'learning_id':learning_id},config=config)
            snapshot=self.graph.get_state(config)
            if not snapshot or not snapshot.next:
                raise RuntimeError('Admin review graph did not reach durable interrupt')
            add_event(self.db,thread,str(learning_id),'learner_agent','administrator_interrupt','waiting')
            return snapshot

    def decide_learning(self, learning_id: int, actor_id: int, decision: str) -> dict:
        from langgraph.types import Command
        if decision not in ('approved','rejected','deferred'):raise ValueError('Unknown decision')
        admin=self.db.query('SELECT role FROM users WHERE id=?',(actor_id,),one=True)
        if not admin or admin['role']!='admin':raise PermissionError('Admin permission required')
        thread=f'vaidya:approval:{learning_id}'
        self.prepare_learning_review(learning_id)
        with self._invoke_lock:
            result=self.graph.invoke(Command(resume={'actor_id':actor_id,'decision':decision}),
                                     config=self.config(thread))
        if result.get('status')!='decision_recorded':
            raise RuntimeError('Administrator approval was not completed')
        return result

    def trace(self, job_id: str) -> list[dict]:
        return self.db.query('SELECT workflow_id,agent,stage,status,created_at FROM workflow_events '
                             'WHERE job_id=? ORDER BY id ASC',(job_id,))

    def checkpoint_summary(self, thread_id: str) -> dict:
        with self._invoke_lock:
            snapshot=self.graph.get_state(self.config(thread_id))
        if not snapshot or not snapshot.values:return {'exists':False,'thread_id':thread_id}
        values=snapshot.values or {}
        return {'exists':True,'thread_id':thread_id,'stage':values.get('stage'),
                'status':values.get('status'),'pending_nodes':list(snapshot.next),
                'checkpoint_id':(snapshot.config or {}).get('configurable',{}).get('checkpoint_id')}

    def close(self):
        self.connection.close()
