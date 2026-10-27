"""Checkpointed Orchestrator + Pathology and Learner LangGraph subgraphs.

State keeps references and non-PHI metadata; clinical text resides only in protected
S3 and transient local node memory. This graph handles long workflows in workers.
"""
from __future__ import annotations
from typing import TypedDict
import os
from io import BytesIO
import json
import hashlib
import tempfile
from pathlib import Path
from sqlalchemy import select,insert,update,func
from .tables import jobs,patients,users,assets,learnings,skills,ai_events
from .repository import now,ident
from .documents import render_draft,extract_text
from .model_router import get_clinical_extractor
from vaidya.fidelity import clinical_fidelity_warnings

class FlowState(TypedDict,total=False):
    mode: str
    job_id: str
    learning_id: str
    thread_id: str
    actor_id: str
    hospital_id: str
    status: str
    stage: str
    original_ref: str
    translated_ref: str
    structured_ref: str
    draft_ref: str
    review_response: dict


def key_for(job,filename):
    return f"hospital/{job['hospital_id']}/jobs/{job['id']}/{filename}"

class ProductionGraph:
    def __init__(self,repo,storage,db_url):
        self.repo=repo
        self.storage=storage
        # PostgresSaver is only opened inside a graph operation.
        if not repo.postgres:
            raise RuntimeError('Production graphs require PostgreSQL checkpoints')
        self.db_url=db_url.replace('postgresql+psycopg://','postgresql://')

    def builder(self):
        from langgraph.graph import StateGraph,START,END
        from langgraph.types import interrupt
        repo=self.repo;storage=self.storage

        def validate(state):
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().first()
            if not job or job['status'] not in ('queued','draft_ready'):
                raise RuntimeError('Job not in a processable state')
            return {'stage':'validated','hospital_id':job['hospital_id']}

        def transcribe(state):
            from vaidya.audio import transcriber
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().one()
                audios=c.execute(select(assets).where(assets.c.job_id==job['id'],assets.c.kind=='audio',
                              assets.c.uploaded==True).order_by(assets.c.sequence)).mappings().all()
            if not audios:
                raise ValueError('Audio upload missing: no transcript or report generated')
            if storage.get(job['input_key']).strip():
                raise ValueError('Unexpected typed transcript in audio-only workflow')
            provider=os.getenv('ASR_PROVIDER','sarvam').strip().lower()
            if provider not in ('sarvam','faster-whisper'):
                raise ValueError('Unsupported production ASR provider')
            if provider=='sarvam':
                required=('VAIDYA_CLINICAL_INPUTS_APPROVED','VAIDYA_CLOUD_OPERATIONS_APPROVED',
                          'VAIDYA_SARVAM_CLINICAL_APPROVED')
                if any(os.getenv(key,'').lower() != 'true' for key in required):
                    raise PermissionError('Sarvam processing requires documented clinical/vendor/privacy release approval')
                if not os.getenv('SARVAM_API_KEY','').strip():
                    raise RuntimeError('SARVAM_API_KEY missing: do not substitute a simulated transcript')
            if provider=='faster-whisper':
                model_path=os.getenv('WHISPER_MODEL_PATH','')
                if not model_path or not Path(model_path).is_dir():
                    raise RuntimeError('Approved local WHISPER_MODEL_PATH required')
            with tempfile.TemporaryDirectory(prefix='vaidya-asr-') as td:
                paths=[]
                for i,asset in enumerate(audios):
                    suffix={'audio/wav':'.wav','audio/mpeg':'.mp3','audio/mp4':'.m4a',
                            'audio/webm':'.webm','audio/ogg':'.ogg'}[asset['content_type']]
                    path=Path(td)/f'note-{i}{suffix}'
                    path.write_bytes(storage.get(asset['object_key']))
                    paths.append(str(path))
                answer=transcriber().transcribe(paths)
            original=answer.text.strip()
            if not original:
                raise RuntimeError('ASR returned empty transcript. No fabricated fallback allowed')
            original_ref=key_for(job,'original.txt')
            storage.put(original_ref,original.encode('utf-8'),'text/plain')
            provenance={
                'provider':answer.provider,'model':answer.model,'mode':answer.mode,
                'languages':answer.detected_languages,'job_ids':answer.job_ids,
                'audio_sha256':answer.audio_sha256,
                'transcript_sha256':hashlib.sha256(original.encode('utf-8')).hexdigest(),
                'note_count':len(audios),
            }
            storage.put(key_for(job,'asr_provenance.json'),
                        json.dumps(provenance,ensure_ascii=False).encode('utf-8'),
                        'application/json')
            return {'original_ref':original_ref,'stage':'transcribed'}

        def translate(state):
            from vaidya.translation import BedrockTranslationProvider
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().one()
            raw=storage.get(state['original_ref']).decode('utf-8')
            # Explicit doctor-selected language configuration, not Unicode heuristics.
            lang=job['language_config']
            if lang=='en':text=raw
            else:
                text=BedrockTranslationProvider().translate(raw,lang,clinical_processing_approved=True).text
            ref=key_for(job,'translated.txt');storage.put(ref,text.encode(),'text/plain')
            return {'translated_ref':ref,'stage':'translated'}

        def extract(state):
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().one()
                skill=c.execute(select(skills.c.content).where(skills.c.hospital_id==job['hospital_id'],
                              skills.c.specialty=='pathology',skills.c.version==job['skill_version'])).scalar_one()
            source=storage.get(state['translated_ref']).decode('utf-8')
            result=get_clinical_extractor().extract(source,skill,clinical_processing_approved=True)
            with repo.engine.begin() as c:
                c.execute(insert(ai_events).values(id=ident(),job_id=job['id'],stage='clinical_extraction',
                    provider=result.provider,model=result.model,latency_ms=result.latency_ms,
                    input_tokens=result.usage.get('inputTokens'),output_tokens=result.usage.get('outputTokens')))
            # Even with structured JSON these are not independently verified diagnoses.
            original=storage.get(state['original_ref']).decode('utf-8')
            review_flags=list(result.review_flags)+clinical_fidelity_warnings(original,result.findings,source)
            obj={'findings':result.findings,'instructions':result.instructions,'review_flags':review_flags,
                 'model':result.model,'provider':result.provider,'usage':result.usage}
            ref=key_for(job,'structured.json')
            storage.put(ref,json.dumps(obj,ensure_ascii=False).encode('utf-8'),'application/json')
            return {'structured_ref':ref,'stage':'extracted'}

        def render(state):
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().one()
                patient=c.execute(select(patients).where(patients.c.id==job['patient_id'])).mappings().one()
                doctor=c.execute(select(users).where(users.c.id==job['doctor_id'])).mappings().one()
                images=c.execute(select(assets).where(assets.c.job_id==job['id'],assets.c.kind=='image',
                             assets.c.uploaded==True)).mappings().all()
                skill=c.execute(select(skills.c.content).where(skills.c.hospital_id==job['hospital_id'],
                           skills.c.specialty=='pathology',skills.c.version==job['skill_version'])).scalar_one()
            structured=json.loads(storage.get(state['structured_ref']).decode('utf-8'))
            raw_images=[storage.get(a['object_key']) for a in images[:5]]
            result=render_draft(patient['reference'],doctor['name'],structured['findings'],
                                structured['instructions'],raw_images,
                                approved_signature_block='add signature placeholder' in skill.lower(),
                                review_flags=structured.get('review_flags',[]))
            key=key_for(job,'draft.docx');storage.put(key,result,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            repo.set_draft(job['id'],key,structured['model'],hashlib.sha256(result).hexdigest())
            return {'draft_ref':key,'stage':'draft_ready'}

        def wait_doctor(state):
            response=interrupt({'kind':'doctor_review','job_id':state['job_id'],
                                'message':'Approved final artifact required'})
            if not isinstance(response,dict) or response.get('approved') is not True:
                raise PermissionError('Doctor approval required')
            with repo.engine.connect() as c:
                job=c.execute(select(jobs.c.status,jobs.c.doctor_id).where(jobs.c.id==state['job_id'])).first()
            if not job or job[0]!='approved' or job[1]!=response.get('doctor_id'):
                raise PermissionError('No matching approved clinical final')
            return {'stage':'doctor_approved','status':'approved'}

        def learn(state):
            with repo.engine.connect() as c:
                job=c.execute(select(jobs).where(jobs.c.id==state['job_id'])).mappings().one()
                if job['status']!='approved':raise RuntimeError('Only approved reports may be learned from')
                accepted=c.execute(select(jobs).where(jobs.c.hospital_id==job['hospital_id'],
                  jobs.c.status=='approved')).mappings().all()
            final=extract_text(storage.get(job['final_key']))
            draft=extract_text(storage.get(job['draft_key']))
            # Scope narrowly: detect only structural signature-block preference;
            # never infer clinical conclusions from changes.
            if 'signature:' in final.lower() and 'signature:' not in draft.lower():
                support=0
                for accepted_job in accepted:
                    if not accepted_job['final_key'] or not accepted_job['draft_key']:continue
                    text=extract_text(storage.get(accepted_job['final_key']))
                    orig=extract_text(storage.get(accepted_job['draft_key']))
                    if 'signature:' in text.lower() and 'signature:' not in orig.lower():support+=1
                if support>=5:
                    with repo.engine.begin() as c:
                        existing=c.execute(select(learnings).where(learnings.c.hospital_id==job['hospital_id'],
                           learnings.c.specialty=='pathology',learnings.c.pattern=='signature_block')).mappings().first()
                        if not existing:
                            c.execute(insert(learnings).values(id=ident(),hospital_id=job['hospital_id'],
                               specialty='pathology',pattern='signature_block',support=support,
                               description='Add signature placeholder to approved Histopathology template',status='suggested'))
                        elif existing['status']=='suggested':
                            c.execute(update(learnings).where(learnings.c.id==existing['id']).values(support=support))
            return {'stage':'learning_complete','status':'review_candidates_recorded'}

        def await_admin(state):
            response=interrupt({'kind':'administrator_review','learning_id':state['learning_id']})
            if not isinstance(response,dict) or response.get('decision') not in ('approved','rejected','deferred'):
                raise PermissionError('Authorized decision required')
            repo.approve_learning(response.get('actor_id'),state['learning_id'],response['decision'])
            return {'stage':'learning_decided','status':response['decision']}

        pathology=StateGraph(FlowState)
        for key,fn in [('validate',validate),('transcribe',transcribe),('translate',translate),
                       ('extract',extract),('render',render),('wait_doctor',wait_doctor)]:pathology.add_node(key,fn)
        pathology.add_edge(START,'validate')
        for a,b in [('validate','transcribe'),('transcribe','translate'),('translate','extract'),
                    ('extract','render'),('render','wait_doctor')]:pathology.add_edge(a,b)
        pathology.add_edge('wait_doctor',END)
        learner=StateGraph(FlowState)
        learner.add_node('analyze_corrections',learn)
        learner.add_node('admin_approval',await_admin)
        learner.add_conditional_edges(START,lambda s:'admin_approval' if s['mode']=='review' else 'analyze_corrections',
                                      {'admin_approval':'admin_approval','analyze_corrections':'analyze_corrections'})
        learner.add_edge('analyze_corrections',END);learner.add_edge('admin_approval',END)
        parent=StateGraph(FlowState)
        parent.add_node('authorize_and_route',lambda s:{'stage':'routed'})
        parent.add_node('pathology_agent',pathology.compile())
        parent.add_node('learner_agent',learner.compile())
        parent.add_edge(START,'authorize_and_route')
        parent.add_conditional_edges('authorize_and_route',lambda s:'pathology_agent' if s['mode']=='generate' else 'learner_agent',
                {'pathology_agent':'pathology_agent','learner_agent':'learner_agent'})
        parent.add_edge('pathology_agent',END);parent.add_edge('learner_agent',END)
        return parent

    def _invoke(self,mode,thread,payload,resume=None):
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.types import Command
        # New saver context per worker/API action; persists across process restarts.
        with PostgresSaver.from_conn_string(self.db_url) as checkpointer:
            graph=self.builder().compile(checkpointer=checkpointer)
            config={'configurable':{'thread_id':thread},'recursion_limit':30}
            if resume is not None:return graph.invoke(Command(resume=resume),config)
            return graph.invoke({'mode':mode,'thread_id':thread,**payload},config)
    def process(self,job_id):return self._invoke('generate','clinical:report:'+job_id,{'job_id':job_id})
    def resume(self,job_id,doctor_id):return self._invoke('generate','clinical:report:'+job_id,{},
                                    {'approved':True,'doctor_id':doctor_id})
    def analyze(self,job_id):return self._invoke('learn','clinical:learning:'+job_id,{'job_id':job_id})
    def start_review(self,learning_id):return self._invoke('review','clinical:approval:'+learning_id,{'learning_id':learning_id})
    def decide(self,learning_id,actor_id,decision):return self._invoke('review','clinical:approval:'+learning_id,{},
                                    {'actor_id':actor_id,'decision':decision})
    def checkpoint(self,thread):
        from langgraph.checkpoint.postgres import PostgresSaver
        with PostgresSaver.from_conn_string(self.db_url) as saver:
            graph=self.builder().compile(checkpointer=saver)
            snap=graph.get_state({'configurable':{'thread_id':thread}})
            return {'pending_nodes':list(snap.next),'checkpoint_id':(snap.config or {}).get('configurable',{}).get('checkpoint_id')}
